from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BudgetRecord, Document, DocumentVersion, Page
from .schemas import ComparisonItem, ComparisonRequest, ComparisonResponse, Evidence


FIELD_MAP = {
    "organization": BudgetRecord.organization_code,
    "program": BudgetRecord.program_code,
    "action": BudgetRecord.action_code,
    "function": BudgetRecord.function_code,
    "subfunction": BudgetRecord.subfunction_code,
}


def compare_budget_records(db: Session, request: ComparisonRequest) -> ComparisonResponse:
    field = FIELD_MAP[request.entity_type]
    rows = db.execute(
        select(BudgetRecord, Page, DocumentVersion, Document)
        .join(Page, BudgetRecord.page_id == Page.id)
        .join(DocumentVersion, BudgetRecord.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(field == request.code, BudgetRecord.year.in_(request.years))
        .order_by(BudgetRecord.year)
    ).all()
    items = [
        ComparisonItem(
            year=record.year,
            original_value=record.original_value,
            numeric_value=str(record.numeric_value),
            unit=record.unit,
            evidence=Evidence(
                document=document.title,
                year=document.year,
                pdf_page=page.pdf_page_number,
                printed_page=page.printed_page_label,
                original_text=record.source_text,
                filename=version.filename,
                page_url=f"/documents/{version.id}/pages/{page.pdf_page_number}",
            ),
        )
        for record, page, version, document in rows
    ]
    found_years = {item.year for item in items}
    missing = sorted(set(request.years) - found_years)
    units = {item.unit for item in items}
    if missing:
        return ComparisonResponse(
            comparable=False,
            reason=f"Não há registro estruturado validado para: {', '.join(map(str, missing))}.",
            items=items,
        )
    if len(units) > 1:
        return ComparisonResponse(
            comparable=False,
            reason="Os registros usam unidades incompatíveis.",
            items=items,
        )
    return ComparisonResponse(comparable=True, reason=None, items=items)
