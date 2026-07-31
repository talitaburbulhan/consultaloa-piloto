import argparse
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR


_engine = None
_pdf_path = None
_target_code = None


def initialize(pdf_path: str, target_code: str) -> None:
    global _engine, _pdf_path, _target_code
    _engine = RapidOCR()
    _pdf_path = pdf_path
    _target_code = target_code


def inspect_page(pdf_page: int) -> dict | None:
    document = pdfium.PdfDocument(_pdf_path)
    image = document[pdf_page - 1].render(scale=0.9).to_pil()
    result, _ = _engine(np.asarray(image))
    rows = []
    for row in result or []:
        y = sum(point[1] for point in row[0]) / 4
        x = sum(point[0] for point in row[0]) / 4
        rows.append((y, x, row[1], float(row[2])))
    for y, _, text, confidence in rows:
        compact = text.replace(" ", "")
        if not re.match(rf"^{re.escape(_target_code)}(?:-|$)", compact):
            continue
        same_line = sorted(
            (
                (x, candidate.replace(" ", ""), candidate_confidence)
                for candidate_y, x, candidate, candidate_confidence in rows
                if abs(candidate_y - y) <= 4
            ),
            key=lambda item: item[0],
        )
        return {
            "pdf_page": pdf_page,
            "label": text,
            "line": [candidate for _, candidate, _ in same_line],
            "confidence": min(
                [confidence, *(item[2] for item in same_line)]
            ),
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("target_code")
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    args = parser.parse_args()
    pdf_path = str(Path(args.pdf).resolve())
    with ProcessPoolExecutor(
        max_workers=4,
        initializer=initialize,
        initargs=(pdf_path, args.target_code),
    ) as executor:
        for row in executor.map(inspect_page, range(args.first, args.last + 1)):
            if row:
                print(row, flush=True)


if __name__ == "__main__":
    main()
