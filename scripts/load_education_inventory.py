from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from loa_api.database import SessionLocal
from loa_api.models import BudgetRecord, Document, DocumentVersion, Page


def numeric_value(original: str) -> Decimal:
    return Decimal(original.replace(".", "").replace(",", "."))


def load_inventory(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["records"]
    counters = {"inserted": 0, "updated": 0, "unchanged": 0}

    with SessionLocal() as db:
        page_rows = db.execute(
            select(Page, DocumentVersion, Document)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.year.in_(range(2019, 2027)),
                DocumentVersion.filename.in_(
                    [f"{year}_volume1.pdf" for year in range(2019, 2027)]
                ),
            )
        ).all()
        pages = {
            (document.year, page.pdf_page_number): (page, version, document)
            for page, version, document in page_rows
        }

        for item in records:
            year = int(item["year"])
            code = str(item["code"])
            original = item["original_value"]
            value = numeric_value(original)
            name = item["name"].strip()
            category = item["category"]
            page_number = int(item["pdf_page"])
            page_row = pages.get((year, page_number))
            if page_row is None:
                raise RuntimeError(
                    f"Página de origem não encontrada: {year}, PDF {page_number}, código {code}"
                )
            page, version, document = page_row

            existing = db.execute(
                select(BudgetRecord).where(
                    BudgetRecord.year == year,
                    BudgetRecord.organization_code == code,
                    BudgetRecord.numeric_value == value,
                )
            ).scalars().all()
            if existing:
                changed = False
                for record in existing:
                    if record.organization_name != name:
                        record.organization_name = name
                        changed = True
                    if record.institution_category != category:
                        record.institution_category = category
                        changed = True
                    if record.parent_organization_code != "26000":
                        record.parent_organization_code = "26000"
                        changed = True
                counters["updated" if changed else "unchanged"] += 1
                continue

            source_text = (
                f"Unidade vinculada ao MEC: {code} {name}. "
                f"Categoria institucional: {category}. "
                f"Total autorizado na LOA: {original}"
            )
            deduplication_key = hashlib.sha256(
                f"education-unit|{year}|{code}|{original}".encode("utf-8")
            ).hexdigest()
            db.add(
                BudgetRecord(
                    year=year,
                    document_version_id=version.id,
                    page_id=page.id,
                    organization_code=code,
                    organization_name=name,
                    institution_category=category,
                    parent_organization_code="26000",
                    original_value=original,
                    numeric_value=value,
                    unit="R$ 1,00",
                    source_text=source_text,
                    deduplication_key=deduplication_key,
                )
            )
            counters["inserted"] += 1

        db.commit()
    counters["expected"] = len(records)
    return counters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(load_inventory(args.inventory), ensure_ascii=False))


if __name__ == "__main__":
    main()
