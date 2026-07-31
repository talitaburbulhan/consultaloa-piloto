from pathlib import Path

from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from loa_api.database import Base
from loa_api.ingestion import classify, ingest_pdf, printed_label
from loa_api.models import DocumentKind


def test_document_classification_prioritizes_amendments() -> None:
    assert classify("2022_LOA-alteracao.pdf") == DocumentKind.AMENDMENT


def test_printed_page_is_read_only_from_header_or_footer() -> None:
    label, method, confidence = printed_label("Título\nConteúdo\nPágina 14")
    assert label == "14"
    assert method == "native-header-footer"
    assert confidence == 0.85


def test_catalogued_document_can_be_completed_later(tmp_path: Path) -> None:
    path = tmp_path / "2026_LOA.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        catalogued = ingest_pdf(db, path, include_text=False)
        assert catalogued.pages == []
        completed = ingest_pdf(db, path, include_text=True)
        assert len(completed.pages) == 1
