from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BudgetRecord, EditorialArea, EditorialRule, HistoricalSegment


@dataclass(frozen=True)
class RecordClassification:
    area_slug: str | None
    record_level: str
    evidence_status: str
    aggregation_policy: str


@dataclass(frozen=True)
class HistoricalComparisonPlan:
    entity_slug: str
    label: str
    segments: tuple[dict, ...]
    requested_years: tuple[int, ...]
    missing_years: tuple[int, ...]
    code_changes: tuple[tuple[int, str, str], ...]
    direct_comparison_allowed: bool
    aggregation_allowed: bool
    warnings: tuple[str, ...]


@lru_cache
def load_editorial_map() -> dict:
    root = Path(__file__).resolve().parents[3]
    path = root / "config" / "mapa_editorial.yml"
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def canonical_area_slug(
    parent_organization_code: str | None,
    organization_code: str | None,
    catalog: dict | None = None,
) -> str | None:
    catalog = catalog or load_editorial_map()
    if organization_code:
        override = catalog.get("protected_code_overrides", {}).get(str(organization_code))
        if override:
            return override
    if not parent_organization_code:
        return None
    return catalog.get("parent_area_map", {}).get(str(parent_organization_code))


def infer_record_level(record: BudgetRecord) -> str:
    category = (record.institution_category or "").casefold()
    code = record.organization_code or ""
    if record.action_code:
        return "valor_acao"
    if record.program_code:
        return "total_programa"
    if "condicionad" in category or "supervisionad" in category or code.startswith("93"):
        return "programacao_supervisionada"
    if (
        record.organization_code
        and record.parent_organization_code
        and record.organization_code == record.parent_organization_code
    ):
        return "total_orgao"
    if record.organization_code:
        return "subtotal_unidade"
    return "nao_classificado"


def aggregation_policy_for(level: str) -> str:
    return {
        "total_orgao": "canonical",
        "subtotal_unidade": "component",
        "total_programa": "detail_only",
        "valor_acao": "detail_only",
        "programacao_supervisionada": "separate",
    }.get(level, "blocked")


def classify_budget_record(
    record: BudgetRecord, catalog: dict | None = None
) -> RecordClassification:
    area_slug = canonical_area_slug(
        record.parent_organization_code,
        record.organization_code,
        catalog,
    )
    level = infer_record_level(record)
    safe = bool(area_slug and level != "nao_classificado")
    return RecordClassification(
        area_slug=area_slug,
        record_level=level,
        evidence_status="homologated" if safe else "unclassified",
        aggregation_policy=aggregation_policy_for(level) if safe else "blocked",
    )


def seed_editorial_map(db: Session, catalog: dict | None = None) -> dict[str, int]:
    catalog = catalog or load_editorial_map()
    counts = {"areas": 0, "rules": 0, "segments": 0}
    for slug, data in catalog["areas"].items():
        area = db.get(EditorialArea, slug)
        if area is None:
            area = EditorialArea(slug=slug, label=data["label"])
            db.add(area)
        area.label = data["label"]
        area.aliases_json = json.dumps(data.get("aliases", []), ensure_ascii=False)
        area.protected = bool(data.get("protected", False))
        area.human_validation_complete = True
        counts["areas"] += 1

    for data in catalog.get("rules", []):
        rule = db.scalar(select(EditorialRule).where(EditorialRule.rule_key == data["rule_key"]))
        if rule is None:
            rule = EditorialRule(rule_key=data["rule_key"])
            db.add(rule)
        rule.subject_slug = data["subject_slug"]
        rule.rule_type = data["rule_type"]
        rule.payload_json = json.dumps(data["payload"], ensure_ascii=False, sort_keys=True)
        rule.source_checkpoint = data.get("source_checkpoint")
        rule.active = True
        counts["rules"] += 1

    for data in catalog.get("historical_segments", []):
        segment = db.scalar(
            select(HistoricalSegment).where(
                HistoricalSegment.entity_slug == data["entity_slug"],
                HistoricalSegment.organization_code == str(data["organization_code"]),
                HistoricalSegment.start_year == int(data["start_year"]),
                HistoricalSegment.end_year == int(data["end_year"]),
            )
        )
        if segment is None:
            segment = HistoricalSegment(
                entity_slug=data["entity_slug"],
                organization_code=str(data["organization_code"]),
                start_year=int(data["start_year"]),
                end_year=int(data["end_year"]),
            )
            db.add(segment)
        segment.area_slug = data["area_slug"]
        segment.comparison_group = data.get("comparison_group")
        segment.aggregation_allowed = bool(data.get("aggregation_allowed", False))
        segment.notes = data.get("notes")
        counts["segments"] += 1
    return counts


def backfill_budget_record_classification(db: Session) -> dict[str, int]:
    counts = {"classified": 0, "unclassified": 0, "changed": 0}
    for record in db.scalars(select(BudgetRecord)).yield_per(500):
        classification = classify_budget_record(record)
        new_values = {
            "area_slug": classification.area_slug,
            "record_level": classification.record_level,
            "evidence_status": classification.evidence_status,
            "aggregation_policy": classification.aggregation_policy,
        }
        if any(getattr(record, key) != value for key, value in new_values.items()):
            for key, value in new_values.items():
                setattr(record, key, value)
            counts["changed"] += 1
        counts[
            "classified" if classification.evidence_status == "homologated" else "unclassified"
        ] += 1
    return counts


def resolve_area_alias(query: str, catalog: dict | None = None) -> tuple[str, str] | None:
    from .chunking import normalize

    catalog = catalog or load_editorial_map()
    normalized_query = normalize(query)
    matches: list[tuple[int, str, str]] = []
    for slug, data in catalog["areas"].items():
        candidates = [data["label"], *data.get("aliases", [])]
        for candidate in candidates:
            normalized_candidate = normalize(str(candidate))
            if normalized_candidate and normalized_candidate in normalized_query:
                matches.append((len(normalized_candidate), slug, data["label"]))
    if not matches:
        return None
    _, slug, label = max(matches)
    return slug, label


def active_rules_for(subject_slug: str, catalog: dict | None = None) -> list[dict]:
    """Return global and subject-specific executable editorial rules."""
    catalog = catalog or load_editorial_map()
    return [
        rule
        for rule in catalog.get("rules", [])
        if rule["subject_slug"] in {"global", subject_slug}
    ]


def resolve_historical_entity_alias(
    query: str, catalog: dict | None = None
) -> tuple[str, str] | None:
    from .chunking import normalize

    catalog = catalog or load_editorial_map()
    normalized_query = normalize(query)
    matches: list[tuple[int, str, str]] = []
    for slug, data in catalog.get("historical_entities", {}).items():
        for candidate in [data["label"], *data.get("aliases", [])]:
            normalized_candidate = normalize(str(candidate))
            if normalized_candidate and normalized_candidate in normalized_query:
                matches.append((len(normalized_candidate), slug, data["label"]))
    if not matches:
        return None
    _, slug, label = max(matches)
    return slug, label


def historical_comparison_plan(
    entity_slug: str,
    years: list[int] | None = None,
    catalog: dict | None = None,
) -> HistoricalComparisonPlan:
    """Build a safe comparison plan without merging documentary segments."""
    catalog = catalog or load_editorial_map()
    entity = catalog.get("historical_entities", {}).get(entity_slug)
    if entity is None:
        raise ValueError(f"Entidade histórica desconhecida: {entity_slug}")
    segments = [
        dict(segment)
        for segment in catalog.get("historical_segments", [])
        if segment.get("comparison_group") == entity_slug
    ]
    segments.sort(key=lambda item: (int(item["start_year"]), int(item["end_year"])))
    if not segments:
        raise ValueError(f"Sem segmentos documentais para: {entity_slug}")

    requested = sorted(set(years or range(2019, 2027)))
    coverage: dict[int, list[dict]] = {year: [] for year in requested}
    for segment in segments:
        for year in requested:
            if int(segment["start_year"]) <= year <= int(segment["end_year"]):
                coverage[year].append(segment)
    overlaps = [year for year, matched in coverage.items() if len(matched) > 1]
    if overlaps:
        raise ValueError(
            "Segmentos documentais sobrepostos nos exercícios: "
            + ", ".join(str(year) for year in overlaps)
        )
    missing = tuple(year for year, matched in coverage.items() if not matched)
    changes: list[tuple[int, str, str]] = []
    previous: dict | None = None
    for segment in segments:
        if previous and previous["organization_code"] != segment["organization_code"]:
            changes.append(
                (
                    int(segment["start_year"]),
                    str(previous["organization_code"]),
                    str(segment["organization_code"]),
                )
            )
        previous = segment

    rules = active_rules_for(entity_slug, catalog)
    regime_break = next(
        (rule for rule in rules if rule["rule_type"] == "regime_transition"), None
    )
    warnings = [
        "Os segmentos podem ser apresentados em sequência, mas os códigos originais permanecem distintos.",
        "Não há soma, equivalência automática ou substituição retroativa de códigos.",
    ]
    if missing:
        warnings.append(
            "Ausência documental em: " + ", ".join(str(year) for year in missing) + "."
        )
    if regime_break:
        warnings.append(
            "A mudança de regime orçamentário impede uma série quantitativa contínua e comparação direta."
        )
    return HistoricalComparisonPlan(
        entity_slug=entity_slug,
        label=entity["label"],
        segments=tuple(segments),
        requested_years=tuple(requested),
        missing_years=missing,
        code_changes=tuple(changes),
        direct_comparison_allowed=regime_break is None,
        aggregation_allowed=False,
        warnings=tuple(warnings),
    )


def canonical_area_totals(
    db: Session, area_slug: str, years: list[int] | None = None
) -> tuple[list[BudgetRecord], list[int]]:
    """Return only canonical, homologated organization totals for an area.

    Duplicate canonical totals for the same year are rejected instead of being summed.
    """
    conditions = [
        BudgetRecord.area_slug == area_slug,
        BudgetRecord.record_level == "total_orgao",
        BudgetRecord.evidence_status == "homologated",
        BudgetRecord.aggregation_policy == "canonical",
    ]
    if years:
        conditions.append(BudgetRecord.year.in_(years))
    records = list(
        db.scalars(select(BudgetRecord).where(*conditions).order_by(BudgetRecord.year))
    )
    by_year: dict[int, list[BudgetRecord]] = {}
    for record in records:
        by_year.setdefault(record.year, []).append(record)
    duplicates = [year for year, rows in by_year.items() if len(rows) > 1]
    if duplicates:
        raise ValueError(
            "Totais canônicos duplicados para os exercícios: "
            + ", ".join(str(year) for year in duplicates)
        )
    expected = sorted(set(years or by_year))
    missing = [year for year in expected if year not in by_year]
    return records, missing
