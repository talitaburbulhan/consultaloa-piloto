import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR
from sqlalchemy import select

from loa_api.chunking import EMBEDDING_MODEL, dumps_embedding, embed, normalize, split_chunks
from loa_api.config import get_settings
from loa_api.database import SessionLocal
from loa_api.ingestion import printed_label
from loa_api.models import Chunk, DocumentVersion, Page


_engine = None


def initialize() -> None:
    global _engine
    _engine = RapidOCR()


def recognize(task: tuple[str, int]) -> dict:
    filename, page_number = task
    settings = get_settings()
    document = pdfium.PdfDocument(settings.source_dir / filename)
    page = document[page_number - 1]
    image = page.render(scale=1.25).to_pil()
    result, _ = _engine(np.asarray(image))
    lines = []
    confidence = []
    if result:
        for row in result:
            lines.append(row[1])
            confidence.append(float(row[2]))
    return {
        "filename": filename,
        "page": page_number,
        "text": "\n".join(lines),
        "confidence": sum(confidence) / len(confidence) if confidence else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--include-review", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    inventory_path = settings.storage_dir / "homologation" / "pending-pages.jsonl"
    allowed = {"ocr-required"}
    if args.include_review:
        allowed.update({"visual-review", "vector-or-blank-review"})
    inventory = [
        json.loads(line)
        for line in inventory_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["classification"] in allowed
    ]
    selected = inventory[args.offset : args.offset + args.limit]
    initialize()
    results = []
    log = settings.storage_dir / "homologation" / "ocr-results.jsonl"
    with SessionLocal() as db, log.open("a", encoding="utf-8") as stream:
        for position, row in enumerate(selected, start=1):
            version = db.scalar(
                select(DocumentVersion).where(DocumentVersion.filename == row["document"])
            )
            current = db.scalar(
                select(Page).where(
                    Page.version_id == version.id,
                    Page.pdf_page_number == row["pdf_page"],
                )
            )
            if current.extraction_method != "ocr-pending":
                continue
            result = recognize((row["document"], row["pdf_page"]))
            results.append(result)
            version = db.scalar(
                select(DocumentVersion).where(DocumentVersion.filename == result["filename"])
            )
            page = db.scalar(
                select(Page).where(
                    Page.version_id == version.id,
                    Page.pdf_page_number == result["page"],
                )
            )
            text = result["text"]
            if text.strip():
                page.original_text = text
                page.page_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                page.extraction_method = "ocr"
                label, method, confidence = printed_label(text)
                page.printed_page_label = label
                page.printed_page_method = f"ocr-{method}" if method else None
                page.printed_page_confidence = confidence
                page.chunks.clear()
                pieces = split_chunks(text)
                for order, piece in enumerate(pieces):
                    page.chunks.append(
                        Chunk(
                            order_index=order,
                            original_text=piece,
                            normalized_text=normalize(piece),
                            context_before=pieces[order - 1][-400:] if order else "",
                            context_after=(
                                pieces[order + 1][:400] if order + 1 < len(pieces) else ""
                            ),
                            embedding_json=dumps_embedding(embed(piece)),
                            embedding_model=EMBEDDING_MODEL,
                        )
                    )
            else:
                page.extraction_method = "ocr-empty"
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            stream.flush()
            db.commit()
            if position % 10 == 0:
                print(f"{position}/{len(selected)}", flush=True)
    print(
        json.dumps(
            {
                "processed": len(results),
                "with_text": sum(bool(item["text"].strip()) for item in results),
            }
        )
    )


if __name__ == "__main__":
    main()
