from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    document_name: str
    parse_status: str


class DocumentExtractItem(BaseModel):
    id: int
    extract_type: str
    extract_version: str | None = None
    extract_family: str | None = None
    title: str
    problem_summary: str
    applied_rules: list[str]
    evidence_excerpt: str
    page_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    paragraph_hash: str | None = None
    evidence_span_id: str | None = None
    keywords: list[str] | None = None
    detail_level: str = "general"
    financial_topics: list[str] | None = None
    note_refs: list[str] | None = None
    risk_points: list[str] | None = None
    fact_tags: list[str] | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    metric_unit: str | None = None
    compare_target: str | None = None
    compare_value: float | None = None
    period: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    event_type: str | None = None
    event_date: str | None = None
    subject: str | None = None
    amount: float | None = None
    counterparty: str | None = None
    direction: str | None = None
    severity: str | None = None
    conditions: str | None = None
    opinion_type: str | None = None
    defect_level: str | None = None
    conclusion: str | None = None
    affected_scope: str | None = None
    auditor_or_board_source: str | None = None
    canonical_risk_key: str | None = None


class DocumentExtractResponse(BaseModel):
    document_id: int
    extracts: list[DocumentExtractItem]
