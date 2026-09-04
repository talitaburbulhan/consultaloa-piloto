from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    id: int
    year: int
    title: str
    kind: str
    filename: str
    page_count: int


class Evidence(BaseModel):
    document: str
    year: int
    pdf_page: int
    printed_page: str | None
    original_text: str
    filename: str
    page_url: str


class SourceReference(BaseModel):
    id: int
    document: str
    year: int
    pdf_page: int
    printed_page: str | None
    excerpt: str
    filename: str
    pdf_url: str
    official_url: str | None = None


class ListedUnit(BaseModel):
    name: str
    code: str
    category: str
    years: list[int]
    source_id: int
    year: int | None = None
    original_value: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    years: list[int] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    interpretation_confirmed: bool = False


class QueryInterpretation(BaseModel):
    intent: str
    intent_label: str
    technical_concept: str
    entity: str | None
    entity_label: str | None
    normalized_query: str
    requires_confirmation: bool
    confirmation_reason: str | None
    confirmed: bool


class SearchResponse(BaseModel):
    query: str
    summary: str | None
    insufficient_evidence: bool
    evidence: list[Evidence]
    sources: list[SourceReference] = Field(default_factory=list)
    listed_units: list[ListedUnit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    interpretation: QueryInterpretation | None = None


class SaveQueryRequest(BaseModel):
    search: SearchRequest


class SavedQueryResponse(BaseModel):
    public_id: str
    search: SearchResponse


class ComparisonRequest(BaseModel):
    entity_type: str = Field(pattern="^(organization|program|action|function|subfunction)$")
    code: str = Field(min_length=1, max_length=30)
    years: list[int] = Field(min_length=2, max_length=8)


class ComparisonItem(BaseModel):
    year: int
    original_value: str
    numeric_value: str
    unit: str | None
    evidence: Evidence


class ComparisonResponse(BaseModel):
    comparable: bool
    reason: str | None
    items: list[ComparisonItem]


class CorpusStatus(BaseModel):
    documents: int
    pages: int
    chunks: int
    native_pages: int
    ocr_pages: int
    blank_verified_pages: int
    pending_review_pages: int
    homologation_complete: bool


class CurrentUserResponse(BaseModel):
    email: str
    is_reviewer: bool


class CatalogUnit(BaseModel):
    code: str
    name: str
    years: list[int]
    record_type: str


class CatalogArea(BaseModel):
    slug: str
    label: str
    units: list[CatalogUnit]


class FeedbackCreateRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    years: list[int] = Field(default_factory=list)
    response: SearchResponse
    verdict: str = Field(pattern="^(correct|incomplete|incorrect)$")
    comment: str = Field(default="", max_length=4000)


class FeedbackResponse(BaseModel):
    public_id: str
    message: str
