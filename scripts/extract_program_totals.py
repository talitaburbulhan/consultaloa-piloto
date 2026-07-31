import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

from loa_api.database import SessionLocal
from loa_api.models import BudgetRecord, Document, DocumentVersion, Page
from inspect_university_2022_ocr import CACHE_PATH, RECOVERED_UNITS
from inspect_university_totals import REVIEW_RANGES, inspect_year


PROGRAM_TOTAL = re.compile(
    r"Programa:\s*(?P<code>\d{4})\s+"
    r"(?P<name>.*?)\s+"
    r"Valor\s+do\s+Programa\s+Constante\s+da\s+LOA:\s*"
    r"(?P<value>\d{1,3}(?:\.\d{3})+|\d+)",
    re.IGNORECASE | re.DOTALL,
)

TARGETED_TOTALS = (
    {
        "entity_type": "organization",
        "year": 2019,
        "filename": "2019_volume5.pdf",
        "page": 200,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b27\.690\.272\.196\b",
        "value_index": 0,
        "canonical_value": "27.690.272.196",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 165,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b29\.933\.456\.570\b",
        "value_index": 0,
        "canonical_value": "29.933.456.570",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2021,
        "filename": "2021_volume1.pdf",
        "page": 155,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b17\.802\.994\.513\b",
        "value_index": 0,
        "canonical_value": "17.802.994.513",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 183,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b42\.872\.726\.102\b",
        "value_index": 0,
        "canonical_value": "42.872.726.102",
        "source_verified": True,
        "visual_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2023,
        "filename": "2023_volume1.pdf",
        "page": 171,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b59\.126\.237\.013\b",
        "value_index": 0,
        "canonical_value": "59.126.237.013",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2024,
        "filename": "2024_volume1.pdf",
        "page": 137,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b73\.081\.269\.932\b",
        "value_index": 0,
        "canonical_value": "73.081.269.932",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2025,
        "filename": "2025_volume1.pdf",
        "page": 152,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b75\.874\.363\.684\b",
        "value_index": 0,
        "canonical_value": "75.874.363.684",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2026,
        "filename": "2026_volume1.pdf",
        "page": 139,
        "code": "26298",
        "name": "Fundo Nacional de Desenvolvimento da Educação",
        "value_pattern": r"\b97\.381\.368\.050\b",
        "value_index": 0,
        "canonical_value": "97.381.368.050",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2019,
        "filename": "2019_volume1.pdf",
        "page": 132,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b122\.951\.191\.257\b",
        "value_index": 0,
        "canonical_value": "122.951.191.257",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2020,
        "filename": "2020_volume5.pdf",
        "page": 6,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b103\.114\.812\.356\b",
        "value_index": 0,
        "canonical_value": "103.114.812.356",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2021,
        "filename": "2021_volume5.pdf",
        "page": 2,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b75\.633\.738\.586\b",
        "value_index": 0,
        "canonical_value": "75.633.738.586",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2022,
        "filename": "2022_volume5.pdf",
        "page": 6,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b137\.910\.699\.453\b",
        "value_index": 0,
        "canonical_value": "137.910.699.453",
        "visual_verified": True,
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2023,
        "filename": "2023_volume5.pdf",
        "page": 6,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b158\.963\.838\.553\b",
        "value_index": 0,
        "canonical_value": "158.963.838.553",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2024,
        "filename": "2024_volume5.pdf",
        "page": 2,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b181\.441\.420\.912\b",
        "value_index": 0,
        "canonical_value": "181.441.420.912",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2025,
        "filename": "2025_volume5.pdf",
        "page": 2,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b197\.752\.076\.395\b",
        "value_index": 0,
        "canonical_value": "197.752.076.395",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2026,
        "filename": "2026_volume5.pdf",
        "page": 2,
        "code": "26000",
        "name": "Ministério da Educação",
        "value_pattern": r"\b233\.713\.665\.576\b",
        "value_index": 0,
        "canonical_value": "233.713.665.576",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2019,
        "filename": "2019_volume1.pdf",
        "page": 175,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b132\.793\.406\.467\b",
        "value_index": 0,
        "canonical_value": "132.793.406.467",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 195,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b134\.719\.499\.112\b",
        "value_index": 0,
        "canonical_value": "134.719.499.112",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2021,
        "filename": "2021_volume1.pdf",
        "page": 186,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b144\.837\.210\.088\b",
        "value_index": 0,
        "canonical_value": "144.837.210.088",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 209,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b160\.495\.420\.749\b",
        "value_index": 0,
        "canonical_value": "160.495.420.749",
        "source_verified": True,
        "visual_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2023,
        "filename": "2023_volume1.pdf",
        "page": 196,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b183\.784\.929\.160\b",
        "value_index": 0,
        "canonical_value": "183.784.929.160",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2024,
        "filename": "2024_volume1.pdf",
        "page": 164,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b232\.054\.842\.894\b",
        "value_index": 0,
        "canonical_value": "232.054.842.894",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2025,
        "filename": "2025_volume1.pdf",
        "page": 179,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b246\.554\.470\.224\b",
        "value_index": 0,
        "canonical_value": "246.554.470.224",
        "source_verified": True,
    },
    {
        "entity_type": "organization",
        "year": 2026,
        "filename": "2026_volume1.pdf",
        "page": 167,
        "code": "36000",
        "name": "Ministério da Saúde",
        "value_pattern": r"\b270\.698\.242\.024\b",
        "value_index": 0,
        "canonical_value": "270.698.242.024",
        "source_verified": True,
    },
    {
        "year": 2019,
        "filename": "2019_volume2.pdf",
        "page": 13,
        "code": "2019",
        "name": "Inclusão social por meio do Bolsa Família, do Cadastro Único e da articulação de políticas sociais",
        "value_pattern": r"\b30\.084\.689\.999\b",
        "value_index": 0,
    },
    {
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 282,
        "code": "5028",
        "name": "Inclusão Social por meio do Bolsa Família e da Articulação de Políticas Públicas",
        "value_pattern": (
            r"5028\s+Inclusão Social por meio do Bolsa Família.*?"
            r"(?P<values>\d{1,3}(?:\.\d{3})+(?:\s+\d{1,3}(?:\.\d{3})+)*)"
        ),
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume4.pdf",
        "page": 508,
        "code": "5028",
        "name": "Inclusão Social por meio do Bolsa Família e da Articulação de Políticas Públicas",
        "value_pattern": (
            r"5028\s+INCLUSAO SOCIAL.*?ARTICULACAODEPOLITICASPUBLICAS\s+"
            r"(?P<values>(?:\d{1,3}[,.]\d{3}[,.]\d{3}[,.]\d{3}\s*){5})"
        ),
        "value_index": 4,
    },
    {
        "year": 2019,
        "filename": "2019_volume2.pdf",
        "page": 20,
        "code": "2027",
        "name": "Cultura: dimensão essencial do Desenvolvimento",
        "value_pattern": r"\b1\.261\.657\.935\b",
        "value_index": 0,
    },
    {
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 282,
        "code": "5025",
        "name": "Cultura",
        "value_pattern": r"5025\s+Cultura\s+(?P<values>1\.328\.802\.945)",
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 268,
        "code": "5025",
        "name": "Cultura",
        "value_pattern": r"5025.*?(?P<values>1\.175\.095\.639)",
        "value_index": 0,
        "decode_glyph_digits": True,
    },
    {
        "year": 2020,
        "filename": "2020_volume2.pdf",
        "page": 148,
        "code": "6012",
        "name": "Defesa Nacional",
        "value_pattern": r"\b11\.660\.962\.406\b",
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 268,
        "code": "6012",
        "name": "Defesa Nacional",
        "value_pattern": r"\b12\.716\.556\.869\b",
        "value_index": 0,
        "decode_glyph_digits": True,
    },
    {
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 282,
        "code": "5013",
        "name": "Educação Superior - Graduação, Pós-Graduação, Ensino, Pesquisa e Extensão",
        "value_pattern": r"5013\s+Educação Superior.*?(?P<values>12\.177\.958\.175)",
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 268,
        "code": "5013",
        "name": "Educação Superior - Graduação, Pós-Graduação, Ensino, Pesquisa e Extensão",
        "value_pattern": r"5013.*?(?P<values>13\.304\.223\.707)",
        "value_index": 0,
        "decode_glyph_digits": True,
    },
    {
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 282,
        "code": "5012",
        "name": "Educação Profissional e Tecnológica",
        "value_pattern": r"5012\s+Educação Profissional e Tecnológica\s+(?P<values>3\.088\.523\.092)",
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 268,
        "code": "5012",
        "name": "Educação Profissional e Tecnológica",
        "value_pattern": r"5012.*?(?P<values>3\.192\.663\.404)",
        "value_index": 0,
        "decode_glyph_digits": True,
    },
    {
        "year": 2020,
        "filename": "2020_volume1.pdf",
        "page": 282,
        "code": "5011",
        "name": "Educação Básica de Qualidade",
        "value_pattern": r"5011\s+Educação Básica de Qualidade.*?(?P<values>13\.360\.235\.066)",
        "value_index": 0,
    },
    {
        "year": 2022,
        "filename": "2022_volume1.pdf",
        "page": 268,
        "code": "5011",
        "name": "Educação Básica de Qualidade",
        "value_pattern": r"5011.*?(?P<values>12\.4\s*72\.346\.629)",
        "value_index": 0,
        "decode_glyph_digits": True,
        "canonical_value": "12.472.346.629",
    },
)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def numeric_value(original: str) -> Decimal:
    return Decimal(original.replace(".", "").replace(",", ""))


def decode_glyph_digits(text: str) -> str:
    replacements = {"\x11": "."}
    replacements.update({chr(0x13 + digit): str(digit) for digit in range(10)})
    return "".join(replacements.get(character, character) for character in text)


def add_targeted_totals(db, seen: set) -> int:
    inserted = 0
    for target in TARGETED_TOTALS:
        row = db.execute(
            select(Page, DocumentVersion, Document)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.year == target["year"],
                DocumentVersion.filename == target["filename"],
                Page.pdf_page_number == target["page"],
            )
        ).one()
        page, version, document = row
        searchable_text = (
            decode_glyph_digits(page.original_text)
            if target.get("decode_glyph_digits")
            else page.original_text
        )
        match = re.search(target["value_pattern"], searchable_text, re.IGNORECASE | re.DOTALL)
        if not match and not target.get("source_verified"):
            continue
        if target.get("canonical_value"):
            original = target["canonical_value"]
        elif "values" in match.groupdict():
            values = re.findall(r"\d{1,3}(?:[,.]\d{3})+", match.group("values"))
            original = values[target["value_index"]]
        else:
            original = match.group(0)
        original = original.replace(",", ".").replace(" ", "")
        entity_type = target.get("entity_type", "program")
        logical_key = (entity_type, document.year, target["code"], original)
        if logical_key in seen:
            continue
        seen.add(logical_key)
        if entity_type == "organization":
            source_text = (
                f"Órgão: {target['code']} {target['name']} "
                f"Total autorizado na LOA: {original}"
            )
        else:
            source_text = (
                f"Programa: {target['code']} {target['name']} "
                f"Valor do Programa Constante da LOA: {original}"
            )
        deduplication_key = hashlib.sha256(
            f"{entity_type}|{document.year}|{target['code']}|{original}".encode("utf-8")
        ).hexdigest()
        db.add(
            BudgetRecord(
                year=document.year,
                document_version_id=version.id,
                page_id=page.id,
                program_code=target["code"] if entity_type == "program" else None,
                organization_code=target["code"] if entity_type == "organization" else None,
                original_value=original,
                numeric_value=numeric_value(original),
                unit="R$ 1,00",
                source_text=source_text,
                deduplication_key=deduplication_key,
            )
        )
        inserted += 1
    return inserted


def university_units() -> list[dict]:
    units = []
    for year in REVIEW_RANGES:
        units.extend(inspect_year(year))
    cached_rows = [
        json.loads(line)
        for line in Path(CACHE_PATH).read_text(encoding="utf-8").splitlines()
    ]
    units_2022 = [
        {**unit, "year": 2022, "pdf_page": row["pdf_page"]}
        for row in cached_rows
        for unit in row["units"]
    ]
    found_codes = {unit["code"] for unit in units_2022}
    units_2022.extend(
        {**unit, "year": 2022}
        for unit in RECOVERED_UNITS
        if unit["code"] not in found_codes
    )
    units.extend(units_2022)
    return units


def add_university_totals(db, seen: set) -> int:
    inserted = 0
    for unit in university_units():
        row = db.execute(
            select(Page, DocumentVersion, Document)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.year == unit["year"],
                DocumentVersion.filename == f"{unit['year']}_volume1.pdf",
                Page.pdf_page_number == unit["pdf_page"],
            )
        ).one()
        page, version, document = row
        original = unit["original_value"]
        logical_key = ("university", document.year, unit["code"], original)
        if logical_key in seen:
            continue
        seen.add(logical_key)
        source_text = (
            f"Unidade universitária federal: {unit['code']} {unit['name']} "
            f"Total autorizado na LOA: {original}"
        )
        deduplication_key = hashlib.sha256(
            f"university|{document.year}|{unit['code']}|{original}".encode("utf-8")
        ).hexdigest()
        db.add(
            BudgetRecord(
                year=document.year,
                document_version_id=version.id,
                page_id=page.id,
                organization_code=unit["code"],
                original_value=original,
                numeric_value=numeric_value(original),
                unit="R$ 1,00",
                source_text=source_text,
                deduplication_key=deduplication_key,
            )
        )
        inserted += 1
    return inserted


def main() -> None:
    inserted = 0
    skipped_duplicates = 0
    with SessionLocal() as db:
        db.execute(delete(BudgetRecord))
        rows = db.execute(
            select(Page, DocumentVersion, Document)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Page.original_text.ilike("%Valor do Programa%"))
            .order_by(Document.year, DocumentVersion.filename, Page.pdf_page_number)
        ).all()
        seen = set()
        for page, version, document in rows:
            for match in PROGRAM_TOTAL.finditer(page.original_text):
                code = match.group("code")
                name = compact(match.group("name"))
                original = match.group("value")
                # Older three-column layouts repeat several program codes before
                # their names and cannot be paired safely by this extractor.
                if re.match(r"^\d{4}\b", name):
                    continue
                normalized_name = name.casefold()
                if (
                    len(name) > 300
                    or "valor do programa" in normalized_name
                    or "programa:" in normalized_name
                    or "órgão:" in normalized_name
                    or "orgao:" in normalized_name
                    or "ação título" in normalized_name
                    or "acao titulo" in normalized_name
                ):
                    continue
                logical_key = (document.year, code, original)
                if logical_key in seen:
                    skipped_duplicates += 1
                    continue
                seen.add(logical_key)
                source_text = compact(match.group(0))
                deduplication_key = hashlib.sha256(
                    f"program|{document.year}|{code}|{original}".encode("utf-8")
                ).hexdigest()
                db.add(
                    BudgetRecord(
                        year=document.year,
                        document_version_id=version.id,
                        page_id=page.id,
                        program_code=code,
                        original_value=original,
                        numeric_value=numeric_value(original),
                        unit="R$ 1,00",
                        source_text=source_text,
                        deduplication_key=deduplication_key,
                    )
                )
                inserted += 1
        inserted += add_targeted_totals(db, seen)
        inserted += add_university_totals(db, seen)
        db.commit()
    print(
        {
            "inserted": inserted,
            "skipped_duplicate_pages": skipped_duplicates,
        }
    )


if __name__ == "__main__":
    main()
