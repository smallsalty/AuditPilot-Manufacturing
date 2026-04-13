from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient
from app.models import DocumentExtractResult, DocumentMeta, ExternalEvent, KnowledgeChunk
from app.utils.documents import parse_document_text
from app.utils.embeddings import HashingEmbeddingService


logger = logging.getLogger(__name__)


class DocumentService:
    RULE_GROUPS = {
        "经营与持续经营风险": [
            "管理层讨论与分析",
            "经营情况",
            "未来展望",
            "持续经营",
            "主要业务",
        ],
        "客户与收入确认风险": [
            "客户集中",
            "收入确认",
            "销售政策",
            "合同负债",
            "应收账款",
        ],
        "存货与产能风险": [
            "存货",
            "产能",
            "在产品",
            "减值",
            "库龄",
        ],
        "治理与合规风险": [
            "重大事项",
            "诉讼",
            "处罚",
            "关联交易",
            "内部控制",
        ],
        "会计政策与估计风险": [
            "会计政策",
            "会计估计",
            "会计变更",
            "资产减值",
            "信用减值",
        ],
    }
    FINANCIAL_DOCUMENT_TYPES = {"annual_report", "interim_report", "quarter_report", "audit_report"}

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.embedding_service = HashingEmbeddingService()
        self.llm_client = llm_client or LLMClient()

    def save_upload(self, db: Session, enterprise_id: int, filename: str, file_bytes: bytes, uploads_dir: Path) -> DocumentMeta:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_path = uploads_dir / filename
        file_path.write_bytes(file_bytes)
        document = DocumentMeta(
            enterprise_id=enterprise_id,
            document_name=filename,
            file_name=filename,
            file_path=str(file_path),
            mime_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
            file_size=len(file_bytes),
            download_status="uploaded",
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
            raise ValueError("文档不存在。")
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
        stmt = select(DocumentExtractResult).where(DocumentExtractResult.document_id == document_id).order_by(DocumentExtractResult.id)
        return list(db.scalars(stmt).all())

    def _parse_document_record(self, db: Session, document: DocumentMeta) -> DocumentMeta:
        if not document.file_path and not document.content_text:
            raise ValueError("文档缺少文件路径和正文内容。")
        document.parse_status = "parsing"
        db.commit()
        try:
            text = document.content_text or parse_document_text(document.file_path or "")
            document.content_text = text
            document.parse_status = "parsed"
            document.parser_version = document.parser_version or "document-service:v2"
            if document.sync_status == "parse_queued":
                document.sync_status = "stored"

            db.execute(delete(DocumentExtractResult).where(DocumentExtractResult.document_id == document.id))
            db.execute(
                delete(KnowledgeChunk).where(
                    KnowledgeChunk.source_type == "document",
                    KnowledgeChunk.source_id == document.id,
                )
            )

            extracts = self._build_structured_extracts(document, text)
            if not extracts:
                extracts = self._fallback_extracts(document, text)

            for index, extract in enumerate(extracts, start=1):
                payload_text = json.dumps(extract, ensure_ascii=False)
                db.add(
                    DocumentExtractResult(
                        document_id=document.id,
                        extract_type=extract["extract_type"],
                        title=extract["title"],
                        content=payload_text,
                        page_number=extract.get("page_number"),
                        keywords=extract.get("keywords"),
                        embedding=self.embedding_service.encode([extract.get("problem_summary") or extract.get("evidence_excerpt") or extract["title"]])[0],
                    )
                )
                chunk_tags = self._dedupe_strings(
                    list(extract.get("keywords") or [])
                    + list(extract.get("applied_rules") or [])
                    + list(extract.get("financial_topics") or [])
                )
                db.add(
                    KnowledgeChunk(
                        enterprise_id=document.enterprise_id,
                        source_type="document",
                        source_id=document.id,
                        title=f"{document.document_name}-{index}",
                        content=f"{extract.get('problem_summary') or extract['title']} {extract.get('evidence_excerpt') or ''}".strip(),
                        tags=chunk_tags,
                        embedding=self.embedding_service.encode(
                            [f"{extract.get('problem_summary') or extract['title']} {extract.get('evidence_excerpt') or ''}".strip()]
                        )[0],
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
                document.sync_status = "parse_failed"
                db.commit()
            raise

    def _build_structured_extracts(self, document: DocumentMeta, text: str) -> list[dict[str, Any]]:
        paragraphs = [item.strip() for item in re.split(r"\n+", text) if item.strip()]
        candidates = self._collect_candidates(document, paragraphs)
        if not candidates:
            return []
        try:
            llm_extracts = self._llm_extract(document, candidates)
            if llm_extracts:
                return [self._normalize_extract_payload(item, candidate_index=index, document=document) for index, item in enumerate(llm_extracts, start=1)]
        except Exception as exc:
            logger.warning("document structured extraction failed document_id=%s error=%s", document.id, exc)
        return [self._normalize_extract_payload(item, candidate_index=index, document=document) for index, item in enumerate(candidates, start=1)]

    def _collect_candidates(self, document: DocumentMeta, paragraphs: list[str]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for index, paragraph in enumerate(paragraphs[:80], start=1):
            matched_rules = [name for name, keywords in self.RULE_GROUPS.items() if any(keyword in paragraph for keyword in keywords)]
            financial_topics = self._extract_financial_topics(paragraph) if document.document_type in self.FINANCIAL_DOCUMENT_TYPES else []
            if not matched_rules and not financial_topics and index > 8:
                continue
            detail_level = "financial_deep_dive" if financial_topics else "general"
            title = self._derive_title(paragraph, matched_rules, financial_topics)
            candidates.append(
                {
                    "title": title,
                    "extract_type": "financial_deep_dive" if detail_level == "financial_deep_dive" else "risk_issue",
                    "problem_summary": paragraph[:160],
                    "applied_rules": matched_rules,
                    "evidence_excerpt": paragraph[:280],
                    "page_number": None,
                    "keywords": self._dedupe_strings([title] + matched_rules + financial_topics),
                    "detail_level": detail_level,
                    "financial_topics": financial_topics,
                    "note_refs": self._extract_note_refs(paragraph),
                    "risk_points": self._build_risk_points(paragraph, matched_rules, financial_topics),
                }
            )
        return candidates[:12]

    def _llm_extract(self, document: DocumentMeta, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidate_lines = []
        for index, item in enumerate(candidates, start=1):
            candidate_lines.append(
                f"{index}. 标题: {item['title']}\n"
                f"规则候选: {', '.join(item.get('applied_rules') or []) or '无'}\n"
                f"财报主题: {', '.join(item.get('financial_topics') or []) or '无'}\n"
                f"证据片段: {item['evidence_excerpt']}"
            )

        system_prompt = (
            "你是审计文档抽取助手。请基于给定规则候选和证据片段，"
            "输出结构化审计问题，不要编造文档中不存在的信息。"
        )
        user_prompt = (
            f"文档名称: {document.document_name}\n"
            f"文档类型: {document.document_type}\n"
            "请从下列候选中提炼 3 到 8 条最重要的审计问题，并返回 JSON 数组。"
            "每个元素必须包含 title, extract_type, problem_summary, applied_rules, evidence_excerpt, "
            "detail_level, financial_topics, note_refs, risk_points。\n"
            f"候选内容:\n{chr(10).join(candidate_lines)}"
        )
        result = self.llm_client.chat_completion(system_prompt, user_prompt, json_mode=True)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            items = result.get("extracts")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def _normalize_extract_payload(
        self,
        payload: dict[str, Any],
        *,
        candidate_index: int,
        document: DocumentMeta,
    ) -> dict[str, Any]:
        detail_level = str(payload.get("detail_level") or "general")
        financial_topics = self._dedupe_strings(list(payload.get("financial_topics") or []))
        note_refs = self._dedupe_strings(list(payload.get("note_refs") or []))
        applied_rules = self._dedupe_strings(list(payload.get("applied_rules") or []))
        risk_points = self._dedupe_strings(list(payload.get("risk_points") or []))
        evidence_excerpt = str(payload.get("evidence_excerpt") or payload.get("content") or "").strip()
        title = str(payload.get("title") or f"{document.document_name}-extract-{candidate_index}").strip()
        summary = str(payload.get("problem_summary") or evidence_excerpt or title).strip()
        return {
            "extract_type": str(payload.get("extract_type") or ("financial_deep_dive" if detail_level == "financial_deep_dive" else "risk_issue")),
            "title": title,
            "problem_summary": summary,
            "applied_rules": applied_rules,
            "evidence_excerpt": evidence_excerpt[:320],
            "page_number": payload.get("page_number"),
            "keywords": self._dedupe_strings(list(payload.get("keywords") or []) + applied_rules + financial_topics),
            "detail_level": detail_level,
            "financial_topics": financial_topics,
            "note_refs": note_refs,
            "risk_points": risk_points,
        }

    def _fallback_extracts(self, document: DocumentMeta, text: str) -> list[dict[str, Any]]:
        paragraphs = [item.strip() for item in re.split(r"\n+", text) if item.strip()]
        extracts = self._collect_candidates(document, paragraphs)
        if extracts:
            return [self._normalize_extract_payload(item, candidate_index=index, document=document) for index, item in enumerate(extracts, start=1)]
        summary = paragraphs[0][:220] if paragraphs else document.document_name
        return [
            {
                "extract_type": "fallback_excerpt",
                "title": document.document_name,
                "problem_summary": "未命中明确规则，当前仅保留候选证据片段。",
                "applied_rules": [],
                "evidence_excerpt": summary,
                "page_number": None,
                "keywords": [],
                "detail_level": "general",
                "financial_topics": [],
                "note_refs": [],
                "risk_points": ["规则未命中"],
            }
        ]

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
        event.parser_version = event.parser_version or "document-service:v2"
        event.sync_status = "stored"
        db.commit()

    def _derive_title(self, paragraph: str, matched_rules: list[str], financial_topics: list[str]) -> str:
        if financial_topics:
            return f"{financial_topics[0]}分析"
        if matched_rules:
            return matched_rules[0]
        return paragraph[:28]

    def _extract_financial_topics(self, paragraph: str) -> list[str]:
        topics = []
        for item in ["收入", "应收账款", "存货", "毛利率", "现金流", "商誉", "减值", "合同负债", "研发费用", "固定资产"]:
            if item in paragraph:
                topics.append(item)
        return self._dedupe_strings(topics)

    def _extract_note_refs(self, paragraph: str) -> list[str]:
        refs = re.findall(r"附注[（(]?[一二三四五六七八九十0-9]+[)）]?", paragraph)
        return self._dedupe_strings(refs)

    def _build_risk_points(self, paragraph: str, matched_rules: list[str], financial_topics: list[str]) -> list[str]:
        points = []
        if matched_rules:
            points.extend([f"命中规则：{item}" for item in matched_rules[:2]])
        if financial_topics:
            points.extend([f"需复核科目：{item}" for item in financial_topics[:2]])
        if any(keyword in paragraph for keyword in ["下降", "波动", "异常", "减值", "处罚", "诉讼"]):
            points.append("披露存在异常或敏感表述")
        return self._dedupe_strings(points)[:4]

    def _dedupe_strings(self, values: list[str | None]) -> list[str]:
        items: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            if text not in items:
                items.append(text)
        return items
