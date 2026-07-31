import json

import numpy as np
import pypdfium2 as pdfium
from sqlalchemy import select

from loa_api.config import get_settings
from loa_api.database import SessionLocal
from loa_api.models import DocumentVersion, Page


def main() -> None:
    settings = get_settings()
    inventory_path = settings.storage_dir / "homologation" / "pending-pages.jsonl"
    rows = [
        json.loads(line)
        for line in inventory_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["classification"] != "ocr-required"
    ]
    documents = {}
    results = []
    with SessionLocal() as db:
        for position, row in enumerate(rows, start=1):
            document = documents.setdefault(
                row["document"], pdfium.PdfDocument(settings.source_dir / row["document"])
            )
            image = document[row["pdf_page"] - 1].render(scale=0.5).to_pil().convert("L")
            pixels = np.asarray(image)
            ink_ratio = float(np.mean(pixels < 245))
            classification = "blank-confirmed" if ink_ratio < 0.0005 else "visual-content-review"
            version = db.scalar(
                select(DocumentVersion).where(DocumentVersion.filename == row["document"])
            )
            page = db.scalar(
                select(Page).where(
                    Page.version_id == version.id,
                    Page.pdf_page_number == row["pdf_page"],
                )
            )
            if classification == "blank-confirmed":
                page.extraction_method = "blank-verified"
            results.append({**row, "ink_ratio": ink_ratio, "render_classification": classification})
            if position % 25 == 0:
                db.commit()
        db.commit()
    output = settings.storage_dir / "homologation" / "render-classification.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "total": len(results),
                "blank": sum(row["render_classification"] == "blank-confirmed" for row in results),
                "visual": sum(
                    row["render_classification"] == "visual-content-review" for row in results
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
