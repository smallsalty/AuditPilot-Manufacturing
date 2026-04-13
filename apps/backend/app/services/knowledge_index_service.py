from __future__ import annotations

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk
from app.utils.embeddings import HashingEmbeddingService


class KnowledgeIndexService:
    def __init__(self) -> None:
        self.embedding_service = HashingEmbeddingService()

    def replace_document_chunks(
        self,
        db: Session,
        *,
        enterprise_id: int,
        document_id: int,
        document_name: str,
        version: str,
        extracts: list[dict[str, Any]],
    ) -> None:
        db.execute(
            update(KnowledgeChunk)
            .where(KnowledgeChunk.source_type == "document")
            .where(KnowledgeChunk.source_id == document_id)
            .values(is_current=False)
        )

        for index, extract in enumerate(extracts, start=1):
            content = f"{extract.get('problem_summary') or extract.get('title') or document_name} {extract.get('evidence_excerpt') or ''}".strip()
            db.add(
                KnowledgeChunk(
                    enterprise_id=enterprise_id,
                    source_type="document",
                    source_id=document_id,
                    source_version=version,
                    is_current=True,
                    title=f"{document_name}-{index}",
                    content=content,
                    tags=list(extract.get("fact_tags") or extract.get("keywords") or []),
                    embedding=self.embedding_service.encode([content])[0],
                )
            )
