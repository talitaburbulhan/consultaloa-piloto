import csv
import io
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .comparison import compare_budget_records
from .database import Base, engine, get_db
from .feedback_database import create_feedback_schema, get_feedback_db
from .exports import search_pdf
from .models import (
    AuditLog,
    BudgetRecord,
    Chunk,
    Document,
    DocumentVersion,
    Feedback,
    Page,
    SavedQuery,
)
from .schemas import (
    DocumentSummary,
    ComparisonRequest,
    ComparisonResponse,
    CorpusStatus,
    CurrentUserResponse,
    SavedQueryResponse,
    SaveQueryRequest,
    SearchRequest,
    SearchResponse,
    FeedbackCreateRequest,
    FeedbackResponse,
)
from .security import CurrentUser, current_user
from .search import (
    education_pilot_out_of_scope,
    education_pilot_query_allowed,
    search_documents,
)


settings = get_settings()
logger = logging.getLogger("loa_api.requests")
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def operational_safeguards(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.on_event("startup")
def create_local_schema() -> None:
    if settings.database_url.startswith("sqlite"):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(engine)
    create_feedback_schema()


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    documents = db.scalar(select(func.count(Document.id))) or 0
    pages = db.scalar(select(func.count(Page.id))) or 0
    return {"status": "ok", "documents": documents, "pages": pages}


def _run_pilot_search(db: Session, request: SearchRequest) -> SearchResponse:
    if settings.pilot_education_only and not education_pilot_query_allowed(
        db, request.query
    ):
        return education_pilot_out_of_scope(request)
    return search_documents(db, request)


@app.get("/me", response_model=CurrentUserResponse)
def me(user: CurrentUser = Depends(current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(email=user.email, is_reviewer=user.is_reviewer)


@app.get("/documents", response_model=list[DocumentSummary])
def documents(
    db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)
) -> list[DocumentSummary]:
    rows = db.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion)
        .order_by(Document.year.desc(), Document.title)
    ).all()
    return [
        DocumentSummary(
            id=version.id,
            year=document.year,
            title=document.title,
            kind=document.kind.value,
            filename=version.filename,
            page_count=version.page_count,
        )
        for document, version in rows
    ]


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> SearchResponse:
    return _run_pilot_search(db, request)


@app.get("/corpus/status", response_model=CorpusStatus)
def corpus_status(
    db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)
) -> CorpusStatus:
    def count_pages(method: str) -> int:
        return db.scalar(select(func.count(Page.id)).where(Page.extraction_method == method)) or 0

    pending = count_pages("ocr-pending")
    return CorpusStatus(
        documents=db.scalar(select(func.count(Document.id))) or 0,
        pages=db.scalar(select(func.count(Page.id))) or 0,
        chunks=db.scalar(select(func.count(Chunk.id))) or 0,
        native_pages=count_pages("native"),
        ocr_pages=count_pages("ocr"),
        blank_verified_pages=count_pages("blank-verified"),
        pending_review_pages=pending,
        homologation_complete=pending == 0,
    )


@app.post("/saved-queries", response_model=SavedQueryResponse)
def save_query(
    request: SaveQueryRequest,
    db: Session = Depends(get_db),
    feedback_db: Session = Depends(get_feedback_db),
    user: CurrentUser = Depends(current_user),
) -> SavedQueryResponse:
    result = _run_pilot_search(db, request.search)
    saved = SavedQuery(
        query_text=request.search.query,
        filters_json=json.dumps({"years": request.search.years}),
        response_json=result.model_dump_json(),
    )
    feedback_db.add(saved)
    feedback_db.flush()
    feedback_db.add(
        AuditLog(
            user_email=user.email,
            action="saved_query.create",
            object_type="saved_query",
            object_id=saved.public_id,
            details_json=json.dumps({"query": request.search.query}, ensure_ascii=False),
        )
    )
    feedback_db.commit()
    feedback_db.refresh(saved)
    return SavedQueryResponse(public_id=saved.public_id, search=result)


@app.get("/saved-queries/{public_id}", response_model=SavedQueryResponse)
def get_saved_query(
    public_id: str,
    feedback_db: Session = Depends(get_feedback_db),
    user: CurrentUser = Depends(current_user),
) -> SavedQueryResponse:
    saved = feedback_db.scalar(select(SavedQuery).where(SavedQuery.public_id == public_id))
    if not saved:
        raise HTTPException(404, "Consulta permanente não encontrada")
    return SavedQueryResponse(
        public_id=saved.public_id,
        search=SearchResponse.model_validate_json(saved.response_json),
    )


@app.post("/search/export.pdf")
def export_search(
    request: SearchRequest,
    db: Session = Depends(get_db),
    feedback_db: Session = Depends(get_feedback_db),
    user: CurrentUser = Depends(current_user),
) -> Response:
    result = _run_pilot_search(db, request)
    feedback_db.add(
        AuditLog(
            user_email=user.email,
            action="search.export",
            object_type="search",
            details_json=json.dumps({"query": request.query}, ensure_ascii=False),
        )
    )
    feedback_db.commit()
    return Response(
        search_pdf(result),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="consulta-loa.pdf"'},
    )


@app.post("/comparisons", response_model=ComparisonResponse)
def compare(
    request: ComparisonRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> ComparisonResponse:
    if settings.pilot_education_only and request.entity_type == "organization":
        education_record = db.scalar(
            select(BudgetRecord.id).where(
                BudgetRecord.organization_code == request.code,
                BudgetRecord.parent_organization_code == "26000",
            )
        )
        if not education_record:
            raise HTTPException(403, "Comparação fora do piloto de Educação")
    return compare_budget_records(db, request)


@app.post("/feedback", response_model=FeedbackResponse)
def create_feedback(
    request: FeedbackCreateRequest,
    feedback_db: Session = Depends(get_feedback_db),
    user: CurrentUser = Depends(current_user),
) -> FeedbackResponse:
    feedback = Feedback(
        user_email=user.email,
        query_text=request.query,
        years_json=json.dumps(request.years),
        response_json=request.response.model_dump_json(),
        verdict=request.verdict,
        comment=request.comment.strip(),
    )
    feedback_db.add(feedback)
    feedback_db.flush()
    feedback_db.add(
        AuditLog(
            user_email=user.email,
            action="feedback.create",
            object_type="feedback",
            object_id=feedback.public_id,
            details_json=json.dumps(
                {"verdict": request.verdict, "query": request.query},
                ensure_ascii=False,
            ),
        )
    )
    feedback_db.commit()
    return FeedbackResponse(
        public_id=feedback.public_id,
        message=(
            "Feedback registrado para revisão humana. "
            "Ele não altera a aplicação automaticamente."
        ),
    )


@app.get("/feedback/report.csv")
def feedback_report(
    feedback_db: Session = Depends(get_feedback_db),
    user: CurrentUser = Depends(current_user),
) -> Response:
    if not user.is_reviewer:
        raise HTTPException(403, "Relatório disponível somente para a revisora responsável")
    rows = feedback_db.scalars(select(Feedback).order_by(Feedback.created_at.desc())).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "data",
            "usuario",
            "pergunta",
            "anos",
            "avaliacao",
            "comentario",
            "situacao_da_revisao",
            "resposta_apresentada",
            "identificador",
        ]
    )
    for item in rows:
        response = SearchResponse.model_validate_json(item.response_json)
        writer.writerow(
            [
                item.created_at.isoformat() if item.created_at else "",
                item.user_email,
                item.query_text,
                ", ".join(str(year) for year in json.loads(item.years_json)),
                item.verdict,
                item.comment,
                item.review_status,
                response.summary or "",
                item.public_id,
            ]
        )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="feedback-piloto-educacao.csv"'
        },
    )


@app.get("/documents/{version_id}/pdf")
def document_pdf(
    version_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> FileResponse:
    version = db.get(DocumentVersion, version_id)
    if not version:
        raise HTTPException(404, "Documento não encontrado")
    path = Path(settings.source_dir) / version.filename
    if not path.is_file():
        raise HTTPException(404, "Arquivo original não encontrado")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=version.filename,
        content_disposition_type="inline",
    )


@app.get("/documents/{version_id}/pages/{page_number}")
def document_page(
    version_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> dict:
    row = db.execute(
        select(Page, DocumentVersion, Document)
        .join(DocumentVersion, Page.version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Page.version_id == version_id, Page.pdf_page_number == page_number)
    ).first()
    if not row:
        raise HTTPException(404, "Página não encontrada")
    page, version, document = row
    return {
        "document": document.title,
        "year": document.year,
        "pdf_page": page.pdf_page_number,
        "printed_page": page.printed_page_label,
        "original_text": page.original_text,
        "pdf_url": f"/documents/{version.id}/pdf#page={page.pdf_page_number}",
    }
