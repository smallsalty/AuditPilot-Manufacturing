from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentExtractResult, DocumentMeta


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_document(self, document_id: int) -> DocumentMeta | None:
        return self.db.get(DocumentMeta, document_id)

    def list_extracts(self, document_id: int) -> list[DocumentExtractResult]:
        stmt = (
            select(DocumentExtractResult)
            .where(DocumentExtractResult.document_id == document_id)
            .order_by(DocumentExtractResult.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_documents(self, enterprise_id: int) -> list[DocumentMeta]:
        stmt = (
            select(DocumentMeta)
            .where(DocumentMeta.enterprise_id == enterprise_id)
            .order_by(DocumentMeta.created_at.desc(), DocumentMeta.id.desc())
        )
        return list(self.db.scalars(stmt).all())
