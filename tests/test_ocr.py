from loa_api.models import Page
from loa_api.ocr import assess_page


def page(text: str) -> Page:
    return Page(
        version_id=1,
        pdf_page_number=1,
        original_text=text,
        page_sha256="0" * 64,
        extraction_method="native",
    )


def test_empty_page_enters_ocr_queue() -> None:
    assert assess_page(page("")).required


def test_native_text_is_preserved() -> None:
    assert not assess_page(page("Texto oficial suficientemente longo para validação.")).required
