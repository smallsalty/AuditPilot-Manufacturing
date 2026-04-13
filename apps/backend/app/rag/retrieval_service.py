from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk
from app.utils.embeddings import HashingEmbeddingService


class RetrievalService:
    def __init__(self) -> None:
        self.embedding_service = HashingEmbeddingService()

    def embed_text(self, text: str) -> list[float]:
        return self.embedding_service.encode([text])[0]

    def retrieve(self, db: Session, query: str, enterprise_id: int | None, top_k: int = 4) -> list[KnowledgeChunk]:
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.is_current.is_(True))
        if enterprise_id is not None:
            stmt = stmt.where(
                (KnowledgeChunk.enterprise_id == enterprise_id) | (KnowledgeChunk.enterprise_id.is_(None))
            )
        chunks = list(db.scalars(stmt).all())
        if not chunks:
            return []
        query_embedding = self.embed_text(query)
        scored = []
        for chunk in chunks:
            score = self.embedding_service.cosine_similarity(query_embedding, chunk.embedding or [])
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for score, chunk in scored[:top_k] if score > 0]
