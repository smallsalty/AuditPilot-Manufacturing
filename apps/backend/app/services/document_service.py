from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentExtractResult, DocumentMeta, ExternalEvent, KnowledgeChunk
from app.utils.documents import parse_document_text
from app.utils.embeddings import HashingEmbeddingService


class DocumentService:
    KEYWORD_GROUPS = {
        "mda": ["管理层讨论", "经营情况", "展望"],
        "risk_warning": ["风险", "客户集中", "原材料", "产能", "下游需求"],
        "accounting_policy": ["会计政策", "会计变更", "收入确认"],
        "major_events": ["重大事项", "诉讼", "处罚", "关联交易"],
    }

    def __init__(self) -> None:
        self.embedding_service = HashingEmbeddingService()

    def save_upload(self, db: Session, enterprise_id: int, filename: str, file_bytes: bytes, uploads_dir: Path) -> DocumentMeta:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_path = uploads_dir / filename
        file_path.write_bytes(file_bytes)
        document = DocumentMeta(
            enterprise_id=enterprise_id,
            document_name=filename,
            file_path=str(file_path),
            parse_status="uploaded",
            source="upload",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    def parse_document(self, db: Session, document_id: int) -> DocumentMeta:
        document = db.get(DocumentMeta, document_id)
        if document is None:
            raise ValueError("Document not found")
        return self._parse_document_record(db, document)

    def process_parse_queue(self, db: Session, enterprise_id: int | None = None) -> dict[str, int]:
        document_stmt = select(DocumentMeta).where(DocumentMeta.sync_status == "parse_queued")
        event_stmt = select(ExternalEvent).where(ExternalEvent.sync_status == "parse_queued")
        if enterprise_id is not None:
            document_stmt = document_stmt.where(DocumentMeta.enterprise_id == enterprise_id)
            event_stmt = event_stmt.where(ExternalEvent.enterprise_id == enterprise_id)
        documents = list(db.scalars(document_stmt).all())
        events = list(db.scalars(event_stmt).all())
        parsed_documents = 0
        parsed_events = 0
        for document in documents:
            self._parse_document_record(db, document)
            parsed_documents += 1
        for event in events:
            self._queue_event_knowledge(db, event)
            parsed_events += 1
        return {"documents": parsed_documents, "events": parsed_events}

    def list_extracts(self, db: Session, document_id: int) -> list[DocumentExtractResult]:
        stmt = select(DocumentExtractResult).where(DocumentExtractResult.document_id == document_id)
        return list(db.scalars(stmt).all())

    def _parse_document_record(self, db: Session, document: DocumentMeta) -> DocumentMeta:
        if not document.file_path and not document.content_text:
            raise ValueError("Document file path and content_text are both missing")
        document.parse_status = "parsing"
        db.commit()
        try:
            text = document.content_text or parse_document_text(document.file_path or "")
            document.content_text = text
            document.parse_status = "parsed"
            document.parser_version = document.parser_version or "document-service:v1"
            if document.sync_status == "parse_queued":
                document.sync_status = "stored"
            db.execute(delete(DocumentExtractResult).where(DocumentExtractResult.document_id == document.id))
            paragraphs = [item.strip() for item in text.split("\n") if item.strip()]
            knowledge_rows: list[tuple[str, str, list[str]]] = []
            for index, paragraph in enumerate(paragraphs[:120], start=1):
                lower_content = paragraph.lower()
                matched_types = []
                for extract_type, keywords in self.KEYWORD_GROUPS.items():
                    if any(keyword.lower() in lower_content for keyword in keywords):
                        matched_types.append(extract_type)
                if not matched_types and index <= 5:
                    matched_types.append("mda")
                for extract_type in matched_types:
                    keywords = self.KEYWORD_GROUPS.get(extract_type, [])
                    embedding = self.embedding_service.encode([paragraph])[0]
                    db.add(
                        DocumentExtractResult(
                            document_id=document.id,
                            extract_type=extract_type,
                            title=f"{extract_type}-{index}",
                            content=paragraph,
                            page_number=None,
                            keywords=keywords,
                            embedding=embedding,
                        )
                    )
                    knowledge_rows.append((extract_type, paragraph, keywords))
            db.commit()
            db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.source_type == "document",
                    KnowledgeChunk.source_id == document.id,
                )
            )
            for extract_type, paragraph, keywords in knowledge_rows:
                db.add(
                    KnowledgeChunk(
                        enterprise_id=document.enterprise_id,
                        source_type="document",
                        source_id=document.id,
                        title=f"{document.document_name}-{extract_type}",
                        content=paragraph,
                        tags=keywords,
                        embedding=self.embedding_service.encode([paragraph])[0],
                    )
                )
            db.commit()
            db.refresh(document)
            return document
        except Exception:
            db.rollback()
            document = db.get(DocumentMeta, document.id)
            if document is not None:
                document.parse_status = "failed"
                document.sync_status = "failed"
                db.commit()
            raise

    def _queue_event_knowledge(self, db: Session, event: ExternalEvent) -> None:
        content = event.summary or event.title
        db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.source_type == "external_event",
                KnowledgeChunk.source_id == event.id,
            )
        )
        db.add(
            KnowledgeChunk(
                enterprise_id=event.enterprise_id,
                source_type="external_event",
                source_id=event.id,
                title=event.title,
                content=content,
                tags=[event.event_type, event.severity, event.regulator or event.source],
                embedding=self.embedding_service.encode([content])[0],
            )
        )
        event.parser_version = event.parser_version or "document-service:v1"
        event.sync_status = "stored"
        db.commit()
