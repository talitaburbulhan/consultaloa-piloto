import re
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select

from loa_api.database import SessionLocal
from loa_api.models import Document, DocumentVersion, Page


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT.parent / "dados"

REVIEW_RANGES = {
    2019: range(132, 176),
    2020: range(142, 190),
    2021: range(132, 180),
    2023: range(156, 205),
    2024: range(122, 172),
    2025: range(136, 186),
    2026: range(123, 173),
}

VALUE = r"\d{1,3}(?:\.\d{3})+"
UNIT_TOTAL = re.compile(
    rf"^\s*(?P<code>\d{{5}})\s*-\s*(?P<name>.*?)\s+"
    rf"(?P<fiscal>{VALUE})\s+(?P<social>{VALUE})"
    rf"(?:\s+(?P<total>{VALUE}))?\s*$"
)
UNIT_TOTAL_WITH_DASH = re.compile(
    rf"^\s*(?P<code>\d{{5}})\s+(?P<name>.*?)\s+"
    rf"(?P<total>{VALUE})-\s+(?P<fiscal>{VALUE})"
    rf"(?:\s+(?P<social>{VALUE}))?\s*$"
)
UNIT_TOTAL_INLINE = re.compile(
    rf"(?P<code>26\d{{3}})\s+"
    rf"(?P<name>(?:Fundação Universidade|Universidade Federal|"
    rf"Universidade Tecnológica Federal|Universidade da Integração Internacional).*?)\s+"
    rf"(?P<total>{VALUE})-\s+(?P<fiscal>{VALUE})\s+(?P<social>{VALUE})"
)


def is_federal_university(name: str) -> bool:
    normalized = name.casefold()
    if "hospital" in normalized or "complexo hospitalar" in normalized:
        return False
    return (
        "universidade federal" in normalized
        or "universidade tecnológica federal" in normalized
        or normalized.startswith("fundação universidade")
        or normalized.startswith("universidade da integração internacional")
    )


def inspect_year(year: int) -> list[dict]:
    reader = PdfReader(DATA_ROOT / f"{year}_volume1.pdf")
    records = []
    seen_codes = set()
    for pdf_page in REVIEW_RANGES[year]:
        text = reader.pages[pdf_page - 1].extract_text(extraction_mode="layout") or ""
        for line in text.splitlines():
            match = UNIT_TOTAL.match(line) or UNIT_TOTAL_WITH_DASH.match(line)
            if not match or not is_federal_university(match.group("name")):
                continue
            code = match.group("code")
            if code in seen_codes:
                continue
            seen_codes.add(code)
            original_value = match.group("total") or match.group("social")
            records.append(
                {
                    "year": year,
                    "code": code,
                    "name": match.group("name").strip(),
                    "original_value": original_value,
                    "pdf_page": pdf_page,
                }
            )
    if records or year not in {2024, 2025}:
        return records

    with SessionLocal() as db:
        rows = db.execute(
            select(Page)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.year == year,
                DocumentVersion.filename == f"{year}_volume1.pdf",
                Page.pdf_page_number.in_(REVIEW_RANGES[year]),
            )
        ).scalars()
        for page in rows:
            text = re.sub(r"\s+", " ", page.original_text)
            for match in UNIT_TOTAL_INLINE.finditer(text):
                name = match.group("name").strip()
                code = match.group("code")
                if not is_federal_university(name) or code in seen_codes:
                    continue
                seen_codes.add(code)
                records.append(
                    {
                        "year": year,
                        "code": code,
                        "name": name,
                        "original_value": match.group("total"),
                        "pdf_page": page.pdf_page_number,
                    }
                )
    return records


def main() -> None:
    for year in REVIEW_RANGES:
        records = inspect_year(year)
        total = sum(
            int(record["original_value"].replace(".", "")) for record in records
        )
        formatted_total = f"{total:,}".replace(",", ".")
        print({"year": year, "units": len(records), "total": formatted_total})


if __name__ == "__main__":
    main()
