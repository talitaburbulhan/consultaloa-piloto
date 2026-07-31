import json
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = PROJECT_ROOT.parent / "dados" / "2022_volume1.pdf"
CACHE_PATH = (
    PROJECT_ROOT / "storage" / "homologation" / "universidades-2022-ocr.jsonl"
)
PAGES = range(165, 211)
NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+")
RECOVERED_UNITS = [
    {"code": "26230", "name": "Fundação Universidade Federal do Vale do São Francisco", "original_value": "209.929.145", "pdf_page": 167, "confidence": 1.0},
    {"code": "26249", "name": "Universidade Federal Rural do Rio de Janeiro", "original_value": "719.829.081", "pdf_page": 172, "confidence": 0.9806},
    {"code": "26251", "name": "Fundação Universidade Federal do Tocantins", "original_value": "311.895.313", "pdf_page": 172, "confidence": 0.9800},
    {"code": "26269", "name": "Fundação Universidade do Rio de Janeiro", "original_value": "517.517.730", "pdf_page": 177, "confidence": 0.9764},
    {"code": "26271", "name": "Fundação Universidade de Brasília", "original_value": "1.941.091.115", "pdf_page": 177, "confidence": 0.9923},
    {"code": "26273", "name": "Fundação Universidade Federal do Rio Grande", "original_value": "540.978.264", "pdf_page": 178, "confidence": 0.9592},
    {"code": "26275", "name": "Fundação Universidade Federal do Acre", "original_value": "389.872.403", "pdf_page": 178, "confidence": 0.9772},
    {"code": "26277", "name": "Fundação Universidade Federal de Ouro Preto", "original_value": "486.463.437", "pdf_page": 179, "confidence": 0.9835},
    {"code": "26279", "name": "Fundação Universidade Federal do Piauí", "original_value": "821.111.498", "pdf_page": 179, "confidence": 0.9798},
    {"code": "26282", "name": "Fundação Universidade Federal de Viçosa", "original_value": "981.487.813", "pdf_page": 180, "confidence": 0.9803},
    {"code": "26283", "name": "Fundação Universidade Federal de Mato Grosso do Sul", "original_value": "952.815.324", "pdf_page": 180, "confidence": 0.9847},
    {"code": "26352", "name": "Fundação Universidade Federal do ABC", "original_value": "336.368.999", "pdf_page": 184, "confidence": 0.9815},
]

_engine = None


def initialize() -> None:
    global _engine
    _engine = RapidOCR()


def inspect_page(pdf_page: int) -> dict:
    document = pdfium.PdfDocument(PDF_PATH)
    image = document[pdf_page - 1].render(scale=1.25).to_pil()
    result, _ = _engine(np.asarray(image))
    rows = []
    for row in result or []:
        y = sum(point[1] for point in row[0]) / 4
        x = sum(point[0] for point in row[0]) / 4
        rows.append((y, x, row[1], float(row[2])))
    units = []
    for y, _, text, confidence in rows:
        compact = text.replace(" ", "")
        normalized = compact.casefold()
        if not re.match(r"^26\d{3}-", compact):
            continue
        if (
            "hospital" in normalized
            or "complexohospitalar" in normalized
            or not (
                "universidadefederal" in normalized
                or "universidadetecnologicafederal" in normalized
                or "fundacaouniversidade" in normalized
                or "universidadedaintegracaointernacional" in normalized
            )
        ):
            continue
        values = [
            (x, candidate.replace(" ", ""), candidate_confidence)
            for candidate_y, x, candidate, candidate_confidence in rows
            if abs(candidate_y - y) <= 4 and NUMBER.fullmatch(candidate.replace(" ", ""))
        ]
        if not values:
            continue
        _, total, total_confidence = max(values, key=lambda item: item[0])
        units.append(
            {
                "code": compact[:5],
                "name": text,
                "original_value": total,
                "confidence": min(confidence, total_confidence),
            }
        )
    return {"pdf_page": pdf_page, "units": units}


def main() -> None:
    completed = {}
    if CACHE_PATH.exists():
        for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            completed[row["pdf_page"]] = row
    pending = [page for page in PAGES if page not in completed]
    with ProcessPoolExecutor(max_workers=4, initializer=initialize) as executor:
        for row in executor.map(inspect_page, pending):
            completed[row["pdf_page"]] = row
            with CACHE_PATH.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    units = [
        {**unit, "pdf_page": page}
        for page, row in sorted(completed.items())
        for unit in row["units"]
    ]
    found_codes = {unit["code"] for unit in units}
    units.extend(unit for unit in RECOVERED_UNITS if unit["code"] not in found_codes)
    print(
        {
            "pages": len(completed),
            "units": len(units),
            "total": f"{sum(int(unit['original_value'].replace('.', '')) for unit in units):,}".replace(
                ",", "."
            ),
            "minimum_confidence": min(
                (unit["confidence"] for unit in units), default=0
            ),
        }
    )


if __name__ == "__main__":
    main()
