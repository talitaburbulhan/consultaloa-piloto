import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class DocumentKind(str, enum.Enum):
    LOA = "loa"
    ANNEX = "anexo"
    VOLUME = "volume"
    AMENDMENT = "alteracao"
    VETO = "veto"
    OTHER = "outro"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(500))
    kind: Mapped[DocumentKind] = mapped_column(Enum(DocumentKind), index=True)
    official_url: Mapped[str | None] = mapped_column(String(1500))
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("year", "title", "kind"),)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    byte_size: Mapped[int]
    page_count: Mapped[int]
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[Document] = relationship(back_populates="versions")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    pdf_page_number: Mapped[int]
    printed_page_label: Mapped[str | None] = mapped_column(String(50))
    printed_page_method: Mapped[str | None] = mapped_column(String(50))
    printed_page_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    original_text: Mapped[str] = mapped_column(Text, default="")
    page_sha256: Mapped[str] = mapped_column(String(64))
    extraction_method: Mapped[str] = mapped_column(String(30), default="native")
    version: Mapped[DocumentVersion] = relationship(back_populates="pages")
    blocks: Mapped[list["ContentBlock"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("version_id", "pdf_page_number"),
        Index("ix_pages_version_printed", "version_id", "printed_page_label"),
    )


class ContentBlock(Base):
    __tablename__ = "content_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), index=True)
    order_index: Mapped[int]
    block_type: Mapped[str] = mapped_column(String(30), default="paragraph")
    original_text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int | None]
    char_end: Mapped[int | None]
    bbox_json: Mapped[str | None] = mapped_column(Text)
    page: Mapped[Page] = relationship(back_populates="blocks")

    __table_args__ = (UniqueConstraint("page_id", "order_index"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), index=True)
    order_index: Mapped[int]
    original_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    context_before: Mapped[str] = mapped_column(Text, default="")
    context_after: Mapped[str] = mapped_column(Text, default="")
    embedding_json: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    page: Mapped[Page] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("page_id", "order_index"),)


class BudgetRecord(Base):
    __tablename__ = "budget_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(index=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    organization_code: Mapped[str | None] = mapped_column(String(30), index=True)
    organization_name: Mapped[str | None] = mapped_column(String(500), index=True)
    institution_category: Mapped[str | None] = mapped_column(String(80), index=True)
    parent_organization_code: Mapped[str | None] = mapped_column(String(30), index=True)
    program_code: Mapped[str | None] = mapped_column(String(30), index=True)
    action_code: Mapped[str | None] = mapped_column(String(30), index=True)
    function_code: Mapped[str | None] = mapped_column(String(30), index=True)
    subfunction_code: Mapped[str | None] = mapped_column(String(30), index=True)
    original_value: Mapped[str] = mapped_column(String(100))
    numeric_value: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    unit: Mapped[str | None] = mapped_column(String(80))
    source_text: Mapped[str] = mapped_column(Text)
    deduplication_key: Mapped[str] = mapped_column(String(64), unique=True)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    query_text: Mapped[str] = mapped_column(Text)
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="running")
    processed_documents: Mapped[int] = mapped_column(default=0)
    processed_pages: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    configuration_json: Mapped[str] = mapped_column(Text, default="{}")


class IngestionError(Base):
    __tablename__ = "ingestion_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    pdf_page_number: Mapped[int | None]
    error_type: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    object_type: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[str | None] = mapped_column(String(200))
    details_json: Mapped[str] = mapped_column(Text, default="{}")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    query_text: Mapped[str] = mapped_column(Text)
    years_json: Mapped[str] = mapped_column(Text, default="[]")
    response_json: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(30), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
