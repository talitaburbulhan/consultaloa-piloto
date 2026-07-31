import json
import argparse
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select

from loa_api.config import get_settings
from loa_api.database import SessionLocal
from loa_api.models import Document, DocumentVersion, Page
from loa_api.ocr import assess_page


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    output = settings.storage_dir / "homologation"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with SessionLocal() as db:
        pending = db.execute(
            select(Page, DocumentVersion, Document)
            .join(DocumentVersion, Page.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Page.extraction_method == "ocr-pending")
            .order_by(Document.year, DocumentVersion.filename, Page.pdf_page_number)
        ).all()[args.offset : args.offset + args.limit]

    readers: dict[str, PdfReader] = {}
    for page, version, document in pending:
        path = settings.source_dir / version.filename
        reader = readers.setdefault(version.filename, PdfReader(path, strict=False))
        pdf_page = reader.pages[page.pdf_page_number - 1]
        resources = pdf_page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        content = pdf_page.get_contents()
        images = 0
        for reference in xobjects.values():
            try:
                if reference.get_object().get("/Subtype") == "/Image":
                    images += 1
            except Exception:
                pass
        has_content = content is not None
        decision = assess_page(page)
        if images:
            classification = "ocr-required"
        elif not has_content:
            classification = "blank-confirmed"
        elif xobjects:
            classification = "visual-review"
        else:
            classification = "vector-or-blank-review"
        rows.append(
            {
                "document": version.filename,
                "year": document.year,
                "pdf_page": page.pdf_page_number,
                "printed_page": page.printed_page_label,
                "classification": classification,
                "reason": decision.reason,
                "image_count": images,
                "has_content_stream": has_content,
            }
        )

    jsonl = output / "pending-pages.jsonl"
    if args.reset and jsonl.exists():
        jsonl.unlink()
    with jsonl.open("a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = Counter(row["classification"] for row in rows)
    print(json.dumps({"total": len(rows), "summary": dict(summary)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
