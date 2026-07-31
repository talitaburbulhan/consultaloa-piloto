from dataclasses import dataclass

from .models import Page


@dataclass(frozen=True)
class OcrDecision:
    required: bool
    reason: str


def assess_page(page: Page) -> OcrDecision:
    text = page.original_text.strip()
    if not text:
        return OcrDecision(True, "sem-texto-extraivel")
    if len(text) < 30:
        return OcrDecision(True, "texto-insuficiente")
    replacement_ratio = text.count("\ufffd") / max(len(text), 1)
    if replacement_ratio > 0.02:
        return OcrDecision(True, "texto-corrompido")
    return OcrDecision(False, "texto-nativo-suficiente")


def ocr_is_advisory_until_review(page: Page) -> bool:
    """OCR nunca substitui silenciosamente o texto nativo."""
    return assess_page(page).required
