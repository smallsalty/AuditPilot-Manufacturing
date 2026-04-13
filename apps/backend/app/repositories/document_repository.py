from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta, ReviewOverride


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_document(self, document_id: int) -> DocumentMeta | None:
        return self.db.get(DocumentMeta, document_id)

    def list_extracts(self, document_id: int) -> list[DocumentExtractResult]:
        stmt = (
            select(DocumentExtractResult)
            .where(DocumentExtractResult.document_id == document_id)
            .where(DocumentExtractResult.is_current.is_(True))
            .order_by(DocumentExtractResult.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_all_extracts(self, document_id: int) -> list[DocumentExtractResult]:
        stmt = (
            select(DocumentExtractResult)
            .where(DocumentExtractResult.document_id == document_id)
            .order_by(DocumentExtractResult.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_event_features(self, document_id: int) -> list[DocumentEventFeature]:
        stmt = (
            select(DocumentEventFeature)
            .where(DocumentEventFeature.document_id == document_id)
            .where(DocumentEventFeature.is_current.is_(True))
            .order_by(DocumentEventFeature.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_documents(self, enterprise_id: int) -> list[DocumentMeta]:
        stmt = (
            select(DocumentMeta)
            .where(DocumentMeta.enterprise_id == enterprise_id)
            .order_by(DocumentMeta.created_at.desc(), DocumentMeta.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_overrides(self, *, document_id: int | None = None, enterprise_id: int | None = None, scope: str | None = None) -> list[ReviewOverride]:
        stmt = select(ReviewOverride).where(ReviewOverride.is_active.is_(True))
        if document_id is not None:
            stmt = stmt.where(ReviewOverride.document_id == document_id)
        if enterprise_id is not None:
            stmt = stmt.where(ReviewOverride.enterprise_id == enterprise_id)
        if scope is not None:
            stmt = stmt.where(ReviewOverride.scope == scope)
        stmt = stmt.order_by(ReviewOverride.id.desc())
        return list(self.db.scalars(stmt).all())
