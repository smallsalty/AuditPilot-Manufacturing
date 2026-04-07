from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentExtractResult, DocumentMeta, KnowledgeChunk
from app.utils.documents import parse_document_text
from app.utils.embeddings import HashingEmbeddingService


class DocumentService:
    KEYWORD_GROUPS = {
        "mda": ["管理层讨论", "经营情况", "展望"],
        "risk_warning": ["风险", "客户集中", "原材料", "产能", "下游需求"],
        "accounting_policy": ["会计政策", "估计变更", "收入确认"],
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
            raise ValueError("文档不存在")
        if not document.file_path:
            raise ValueError("文档文件路径缺失")
        text = parse_document_text(document.file_path)
        document.content_text = text
        document.parse_status = "parsed"
        db.execute(delete(DocumentExtractResult).where(DocumentExtractResult.document_id == document_id))
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
                        document_id=document_id,
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

    def list_extracts(self, db: Session, document_id: int) -> list[DocumentExtractResult]:
        stmt = select(DocumentExtractResult).where(DocumentExtractResult.document_id == document_id)
        return list(db.scalars(stmt).all())
