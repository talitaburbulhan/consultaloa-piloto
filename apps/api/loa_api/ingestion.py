import hashlib
import re
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chunking import EMBEDDING_MODEL, dumps_embedding, embed, normalize, split_chunks
from .models import Chunk, Document, DocumentKind, DocumentVersion, Page


YEAR_PATTERN = re.compile(r"^(20\d{2})")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(filename: str) -> DocumentKind:
    name = filename.casefold()
    if "alteracao" in name:
        return DocumentKind.AMENDMENT
    if "veto" in name:
        return DocumentKind.VETO
    if "volume" in name:
        return DocumentKind.VOLUME
    if "anexo" in name:
        return DocumentKind.ANNEX
    if "loa" in name or "orçamentos fiscal" in name:
        return DocumentKind.LOA
    return DocumentKind.OTHER


def printed_label(text: str) -> tuple[str | None, str | None, float | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = lines[:4] + lines[-4:]
    for line in candidates:
        match = re.fullmatch(r"(?:p[aá]g(?:ina)?\.?\s*)?(\d{1,5})", line, re.I)
        if match:
            return match.group(1), "native-header-footer", 0.85
    return None, None, None


def ingest_pdf(db: Session, path: Path, include_text: bool = True) -> DocumentVersion:
    match = YEAR_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Ano não identificado no nome: {path.name}")
    year = int(match.group(1))
    digest = sha256_file(path)
    existing = db.scalar(select(DocumentVersion).where(DocumentVersion.sha256 == digest))
    if existing:
        if include_text and not existing.pages:
            reader = PdfReader(path, strict=False)
            _append_pages(existing, reader)
            db.commit()
            db.refresh(existing)
        elif include_text:
            changed = False
            for page in existing.pages:
                if not page.chunks and page.original_text.strip():
                    _append_chunks(page, page.original_text)
                    changed = True
            if changed:
                db.commit()
                db.refresh(existing)
        return existing

    reader = PdfReader(path, strict=False)
    kind = classify(path.name)
    document = Document(year=year, title=path.stem, kind=kind)
    version = DocumentVersion(
        document=document,
        filename=path.name,
        sha256=digest,
        byte_size=path.stat().st_size,
        page_count=len(reader.pages),
    )
    db.add(version)
    db.flush()

    if include_text:
        _append_pages(version, reader)
    db.commit()
    db.refresh(version)
    return version


def _append_pages(version: DocumentVersion, reader: PdfReader) -> None:
    for index, pdf_page in enumerate(reader.pages, start=1):
        text = pdf_page.extract_text() or ""
        label, method, confidence = printed_label(text)
        page = Page(
                pdf_page_number=index,
                printed_page_label=label,
                printed_page_method=method,
                printed_page_confidence=confidence,
                original_text=text,
                page_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                extraction_method="native" if text.strip() else "ocr-pending",
            )
        _append_chunks(page, text)
        version.pages.append(page)


def _append_chunks(page: Page, text: str) -> None:
    pieces = split_chunks(text)
    for order, piece in enumerate(pieces):
        page.chunks.append(
            Chunk(
                order_index=order,
                original_text=piece,
                normalized_text=normalize(piece),
                context_before=pieces[order - 1][-400:] if order else "",
                context_after=pieces[order + 1][:400] if order + 1 < len(pieces) else "",
                embedding_json=dumps_embedding(embed(piece)),
                embedding_model=EMBEDDING_MODEL,
            )
        )


def ingest_directory(db: Session, source_dir: Path, include_text: bool = True) -> list[DocumentVersion]:
    return [
        ingest_pdf(db, path, include_text=include_text)
        for path in sorted(source_dir.glob("*.pdf"))
    ]
