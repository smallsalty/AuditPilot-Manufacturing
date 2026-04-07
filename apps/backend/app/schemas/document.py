from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    document_name: str
    parse_status: str


class DocumentExtractItem(BaseModel):
    id: int
    extract_type: str
    title: str
    content: str
    page_number: int | None = None
    keywords: list[str] | None = None


class DocumentExtractResponse(BaseModel):
    document_id: int
    extracts: list[DocumentExtractItem]

