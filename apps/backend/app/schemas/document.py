from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    document_name: str
    parse_status: str


class DocumentExtractItem(BaseModel):
    id: int
    extract_type: str
    title: str
    problem_summary: str
    applied_rules: list[str]
    evidence_excerpt: str
    page_number: int | None = None
    keywords: list[str] | None = None
    detail_level: str = "general"
    financial_topics: list[str] | None = None
    note_refs: list[str] | None = None
    risk_points: list[str] | None = None


class DocumentExtractResponse(BaseModel):
    document_id: int
    extracts: list[DocumentExtractItem]
