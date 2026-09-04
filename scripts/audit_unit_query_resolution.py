"""Audit exact-name budget queries against every homologated LOA unit."""

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from loa_api.chunking import normalize
from loa_api.models import BudgetRecord
from loa_api.search import (
    _alias_spans,
    _drop_nested_institution_matches,
    _institution_aliases,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    engine = create_engine(f"sqlite:///{(ROOT / 'storage' / 'loa.db').as_posix()}")
    with Session(engine) as db:
        candidates = db.execute(
            select(
                BudgetRecord.organization_code,
                BudgetRecord.organization_name,
                BudgetRecord.year,
            )
            .where(
                BudgetRecord.organization_code.is_not(None),
                BudgetRecord.organization_name.is_not(None),
                BudgetRecord.numeric_value.is_not(None),
                BudgetRecord.evidence_status == "homologated",
            )
            .distinct()
            .order_by(BudgetRecord.year, BudgetRecord.organization_code)
        ).all()

        failures = []
        requires_code = set()
        units: dict[tuple[str, str], set[int]] = {}
        for code, name, year in candidates:
            units.setdefault((code, name), set()).add(year)

        units_by_year: dict[int, list[tuple[str, str, set[str]]]] = {}
        for candidate_code, candidate_name, candidate_year in candidates:
            item = (
                candidate_code,
                candidate_name,
                _institution_aliases(candidate_name, candidate_code),
            )
            if item not in units_by_year.setdefault(candidate_year, []):
                units_by_year[candidate_year].append(item)

        for code, name, year in candidates:
            normalized_query = normalize(
                f"Qual foi o orçamento de {name} em {year}?"
            )
            matched = {}
            spans_by_code = {}
            for candidate_code, candidate_name, aliases in units_by_year[year]:
                spans = {
                    span
                    for alias in aliases
                    for span in _alias_spans(alias, normalized_query)
                }
                if spans:
                    matched[candidate_code] = (candidate_name, [])
                    spans_by_code[candidate_code] = spans
            _drop_nested_institution_matches(matched, spans_by_code)
            matched_codes = set(matched)
            matched_names = {normalize(item[0]) for item in matched.values()}
            if len(matched_codes) > 1 and len(matched_names) == 1:
                requires_code.add((year, name))
                continue
            if matched_codes != {code}:
                failures.append(
                    {
                        "year": year,
                        "code": code,
                        "name": name,
                        "matched_codes": sorted(matched_codes),
                    }
                )

    print(f"Unidades verificadas: {len(units)}")
    print(f"Combinações unidade/exercício cobertas: {len(candidates)}")
    print(f"Nomes idênticos que exigem código: {len(requires_code)}")
    print(f"Falhas: {len(failures)}")
    for failure in failures[:50]:
        print(
            f"{failure['year']} | {failure['code']} | {failure['name']} | "
            f"códigos reconhecidos={failure['matched_codes']}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
