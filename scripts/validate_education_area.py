from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from loa_api.database import SessionLocal
from loa_api.models import BudgetRecord, Document, DocumentVersion, Page


EXPECTED_COUNTS = {
    2019: 153,
    2020: 154,
    2021: 154,
    2022: 154,
    2023: 151,
    2024: 151,
    2025: 151,
    2026: 151,
}


def parse_original(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def validate() -> dict:
    checks = {}
    with SessionLocal() as db:
        rows = db.execute(
            select(BudgetRecord, Page, DocumentVersion, Document)
            .join(Page, BudgetRecord.page_id == Page.id)
            .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(BudgetRecord.parent_organization_code == "26000")
            .order_by(BudgetRecord.year, BudgetRecord.organization_code)
        ).all()
        annual_counts = {}
        for year in EXPECTED_COUNTS:
            annual_counts[year] = len(
                {record.organization_code for record, _, _, _ in rows if record.year == year}
            )
        checks["annual_counts"] = {
            "passed": annual_counts == EXPECTED_COUNTS,
            "actual": annual_counts,
            "expected": EXPECTED_COUNTS,
        }
        checks["record_count"] = {"passed": len(rows) == 1219, "actual": len(rows)}
        distinct_codes = {record.organization_code for record, _, _, _ in rows}
        checks["distinct_codes"] = {
            "passed": len(distinct_codes) == 154,
            "actual": len(distinct_codes),
        }
        duplicate_count = db.execute(
            select(func.count())
            .select_from(
                select(
                    BudgetRecord.year,
                    BudgetRecord.organization_code,
                )
                .where(BudgetRecord.parent_organization_code == "26000")
                .group_by(BudgetRecord.year, BudgetRecord.organization_code)
                .having(func.count() > 1)
                .subquery()
            )
        ).scalar_one()
        checks["duplicates_by_code_and_year"] = {
            "passed": duplicate_count == 0,
            "actual": duplicate_count,
        }
        metadata_errors = [
            record.id
            for record, page, version, document in rows
            if not record.organization_name
            or not record.institution_category
            or record.unit != "R$ 1,00"
            or record.year != document.year
            or not version.filename.startswith(f"{record.year}_")
            or page.pdf_page_number < 1
            or parse_original(record.original_value) != record.numeric_value
            or record.original_value not in record.source_text
        ]
        checks["metadata_and_traceability"] = {
            "passed": not metadata_errors,
            "error_record_ids": metadata_errors,
        }
        name_variants = {}
        for code in distinct_codes:
            names = {
                record.organization_name
                for record, _, _, _ in rows
                if record.organization_code == code
            }
            if len(names) > 1:
                name_variants[code] = sorted(names)
        checks["unexplained_name_variants"] = {
            "passed": not name_variants,
            "actual": name_variants,
        }
        subordinate_sums = {
            year: total
            for year, total in db.execute(
                select(BudgetRecord.year, func.sum(BudgetRecord.numeric_value))
                .where(BudgetRecord.parent_organization_code == "26000")
                .group_by(BudgetRecord.year)
            )
        }
        aggregate_values = {
            year: value
            for year, value in db.execute(
                select(BudgetRecord.year, BudgetRecord.numeric_value).where(
                    BudgetRecord.organization_code == "26000"
                )
            )
        }
        checks["subordinate_sum_matches_mec_aggregate"] = {
            "passed": subordinate_sums == aggregate_values,
            "subordinate_sums": {year: str(value) for year, value in subordinate_sums.items()},
            "aggregate_values": {year: str(value) for year, value in aggregate_values.items()},
        }
        transitions = {}
        for code in sorted(distinct_codes):
            years = sorted(
                record.year for record, _, _, _ in rows if record.organization_code == code
            )
            if len(years) != 8:
                transitions[code] = years
        checks["documented_code_transitions"] = {
            "passed": transitions
            == {
                "26401": [2019, 2020, 2021, 2022],
                "26444": [2019, 2020, 2021, 2022],
                "26451": [2019, 2020, 2021, 2022],
                "26457": [2020, 2021, 2022, 2023, 2024, 2025, 2026],
            },
            "actual": transitions,
        }
    return {
        "area": "Educação",
        "validation_type": "automated",
        "human_editorial_validation": "pending",
        "passed": all(item["passed"] for item in checks.values()),
        "checks": checks,
    }


def main() -> None:
    result = validate()
    output = Path("storage/homologation/education-validation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
