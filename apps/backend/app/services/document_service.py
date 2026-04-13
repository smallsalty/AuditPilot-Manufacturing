from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient
from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta, ExternalEvent
from app.repositories.document_repository import DocumentRepository
from app.services.document_classify_service import DocumentClassifyService
from app.services.document_feature_service import DocumentFeatureService
from app.services.knowledge_index_service import KnowledgeIndexService
from app.utils.documents import parse_document_text
from app.utils.embeddings import HashingEmbeddingService


logger = logging.getLogger(__name__)


class DocumentService:
    EXTRACT_VERSION = "document-extract:v3"
    FINANCIAL_DOCUMENT_TYPES = {"annual_report", "annual_summary", "audit_report", "internal_control_report"}
    RULE_GROUPS = {
        "revenue_recognition": ["营业收入", "收入确认", "合同负债", "四季度"],
        "receivable_recoverability": ["应收账款", "坏账", "信用减值", "回款"],
        "inventory_impairment": ["存货", "跌价", "减值", "库龄"],
        "cashflow_quality": ["经营现金流", "净利润", "现金流量"],
        "related_party_funds_occupation": ["关联交易", "资金占用", "非经营性资金占用"],
        "litigation_compliance": ["诉讼", "处罚", "问询", "仲裁"],
        "internal_control_effectiveness": ["内部控制", "内控", "缺陷整改"],
        "financing_pressure": ["回购", "可转债", "担保", "融资"],
        "governance_instability": ["董事", "监事", "高级管理人员", "辞职", "变动"],
        "going_concern": ["持续经营", "重大不确定性", "保留意见", "无法表示意见"],
    }
    EVENT_TYPES = {
        "回购": "share_repurchase",
        "可转债": "convertible_bond",
        "高管": "executive_change",
        "董事": "executive_change",
        "监事": "executive_change",
        "诉讼": "litigation",
        "仲裁": "litigation",
        "处罚": "penalty_or_inquiry",
        "问询": "penalty_or_inquiry",
        "担保": "guarantee",
        "关联交易": "related_party_transaction",
    }
    OPINION_TYPES = {
        "保留意见": "audit_opinion_issue",
        "否定意见": "audit_opinion_issue",
        "无法表示意见": "audit_opinion_issue",
        "强调事项": "audit_opinion_issue",
        "关键审计事项": "audit_opinion_issue",
        "重大缺陷": "internal_control_issue",
        "重要缺陷": "internal_control_issue",
        "内部控制存在缺陷": "internal_control_issue",
    }
    FINANCIAL_TOPICS = [
        "应收账款",
        "存货",
        "营业收入",
        "营业成本",
        "销售费用",
        "管理费用",
        "研发费用",
        "经营现金流",
        "净利润",
        "毛利率",
        "减值",
    ]
    NOISE_PATTERNS = [
        re.compile(r"^\d+\s*/\s*\d+$"),
        re.compile(r"^第?\s*\d+\s*页.*$"),
        re.compile(r"^目录$"),
        re.compile(r"^[\.\-·•\s\d]{4,}$"),
        re.compile(r"^(公司代码|证券代码|股票代码)[:：].*$"),
    ]
    HEADING_PATTERN = re.compile(r"^(第[一二三四五六七八九十0-9]+[章节部分项]|[一二三四五六七八九十]+、|[0-9]+\.)")
    MONEY_PATTERN = re.compile(r"(?P<value>\d[\d,]*\.?\d*)\s*(?P<unit>亿元|万元|元|%)")
    DATE_PATTERN = re.compile(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)")

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.embedding_service = HashingEmbeddingService()
        self.llm_client = llm_client or LLMClient()
        self.classify_service = DocumentClassifyService()
        self.feature_service = DocumentFeatureService()
        self.knowledge_index_service = KnowledgeIndexService()

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
        parsed_documents = 0
        parsed_events = 0
        for document in list(db.scalars(document_stmt).all()):
            self._parse_document_record(db, document)
            parsed_documents += 1
        for event in list(db.scalars(event_stmt).all()):
            self._queue_event_knowledge(db, event)
            parsed_events += 1
        return {"documents": parsed_documents, "events": parsed_events}

    def list_extracts(self, db: Session, document_id: int) -> list[DocumentExtractResult]:
        return DocumentRepository(db).list_extracts(document_id)

    def _parse_document_record(self, db: Session, document: DocumentMeta) -> DocumentMeta:
        if not document.file_path and not document.content_text:
            raise ValueError("文档缺少文件路径和正文内容。")

        document.parse_status = "parsing"
        db.commit()
        try:
            text = document.content_text or parse_document_text(document.file_path or "")
            document.content_text = text
            override = self._latest_override(db, document_id=document.id, scope="classification")
            classified_type, classification_source = self.classify_service.classify(document, text, override)

            document.classified_type = classified_type
            document.classification_version = self.classify_service.CLASSIFICATION_VERSION
            document.classification_source = classification_source
            document.parse_status = "parsed"
            document.parser_version = self.EXTRACT_VERSION
            if document.sync_status == "parse_queued":
                document.sync_status = "stored"

            self._retire_current_rows(db, document.id)

            cleaned_entries = self._clean_document(text, classified_type)
            extracts = self._build_structured_extracts(document, cleaned_entries, classified_type)
            if not extracts:
                extracts = self._fallback_extracts(document, cleaned_entries, classified_type)
            extracts = self._apply_extract_overrides(db, document.id, extracts)

            features = self.feature_service.build_features(extracts, enterprise_id=document.enterprise_id, document_id=document.id)
            extract_rows = self._persist_extracts(db, document, extracts)
            self._persist_features(db, document, features, extract_rows)
            self.knowledge_index_service.replace_document_chunks(
                db,
                enterprise_id=document.enterprise_id,
                document_id=document.id,
                document_name=document.document_name,
                version=self.EXTRACT_VERSION,
                extracts=extracts,
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

    def _retire_current_rows(self, db: Session, document_id: int) -> None:
        db.execute(
            update(DocumentExtractResult)
            .where(DocumentExtractResult.document_id == document_id)
            .where(DocumentExtractResult.is_current.is_(True))
            .values(is_current=False)
        )
        db.execute(
            update(DocumentEventFeature)
            .where(DocumentEventFeature.document_id == document_id)
            .where(DocumentEventFeature.is_current.is_(True))
            .values(is_current=False)
        )

    def _persist_extracts(self, db: Session, document: DocumentMeta, extracts: list[dict[str, Any]]) -> dict[str, int]:
        rows: dict[str, int] = {}
        for extract in extracts:
            row = DocumentExtractResult(
                document_id=document.id,
                extract_type=extract["extract_type"],
                title=extract["title"],
                content=json.dumps(extract, ensure_ascii=False),
                extract_version=self.EXTRACT_VERSION,
                is_current=True,
                extract_family=extract.get("extract_family"),
                problem_summary=extract.get("problem_summary"),
                applied_rules=extract.get("applied_rules"),
                evidence_excerpt=extract.get("evidence_excerpt"),
                detail_level=extract.get("detail_level"),
                fact_tags=extract.get("fact_tags"),
                page_number=extract.get("page_number"),
                page_start=extract.get("page_start"),
                page_end=extract.get("page_end"),
                section_title=extract.get("section_title"),
                paragraph_hash=extract.get("paragraph_hash"),
                evidence_span_id=extract.get("evidence_span_id"),
                metric_name=extract.get("metric_name"),
                metric_value=extract.get("metric_value"),
                metric_unit=extract.get("metric_unit"),
                compare_target=extract.get("compare_target"),
                compare_value=extract.get("compare_value"),
                period=extract.get("period"),
                fiscal_year=extract.get("fiscal_year"),
                fiscal_quarter=extract.get("fiscal_quarter"),
                event_type=extract.get("event_type"),
                event_date=self.feature_service._coerce_date(extract.get("event_date")),
                subject=extract.get("subject"),
                amount=extract.get("amount"),
                counterparty=extract.get("counterparty"),
                direction=extract.get("direction"),
                severity=extract.get("severity"),
                opinion_type=extract.get("opinion_type"),
                defect_level=extract.get("defect_level"),
                conclusion=extract.get("conclusion"),
                affected_scope=extract.get("affected_scope"),
                auditor_or_board_source=extract.get("auditor_or_board_source"),
                canonical_risk_key=extract.get("canonical_risk_key"),
                keywords=extract.get("keywords"),
                embedding=self.embedding_service.encode([extract.get("problem_summary") or extract["title"]])[0],
            )
            db.add(row)
            db.flush()
            rows[str(extract.get("evidence_span_id"))] = row.id
        return rows

    def _persist_features(self, db: Session, document: DocumentMeta, features: list[dict[str, Any]], extract_rows: dict[str, int]) -> None:
        for feature in features:
            payload = feature.get("payload") or {}
            db.add(
                DocumentEventFeature(
                    enterprise_id=document.enterprise_id,
                    document_id=document.id,
                    extract_id=extract_rows.get(str(payload.get("evidence_span_id"))),
                    feature_version=feature.get("feature_version"),
                    is_current=True,
                    feature_type=feature.get("feature_type") or "event",
                    event_type=feature.get("event_type"),
                    canonical_risk_key=feature.get("canonical_risk_key"),
                    event_date=feature.get("event_date"),
                    subject=feature.get("subject"),
                    amount=feature.get("amount"),
                    counterparty=feature.get("counterparty"),
                    direction=feature.get("direction"),
                    severity=feature.get("severity"),
                    conditions=feature.get("conditions"),
                    opinion_type=feature.get("opinion_type"),
                    defect_level=feature.get("defect_level"),
                    conclusion=feature.get("conclusion"),
                    affected_scope=feature.get("affected_scope"),
                    auditor_or_board_source=feature.get("auditor_or_board_source"),
                    metric_name=feature.get("metric_name"),
                    metric_value=feature.get("metric_value"),
                    metric_unit=feature.get("metric_unit"),
                    period=feature.get("period"),
                    fiscal_year=feature.get("fiscal_year"),
                    fiscal_quarter=feature.get("fiscal_quarter"),
                    payload=payload,
                )
            )

    def _split_entries(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return [item.strip() for item in re.split(r"\n{1,}", normalized) if item.strip()]

    def _clean_document(self, text: str, classified_type: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        section_title = ""
        for raw in self._split_entries(text):
            item = re.sub(r"\s+", " ", raw).strip()
            if not item or any(pattern.match(item) for pattern in self.NOISE_PATTERNS) or len(item) < 6:
                continue
            if self.HEADING_PATTERN.match(item):
                section_title = item[:80]
                continue
            paragraph_hash = hashlib.sha1(item.encode("utf-8")).hexdigest()
            if paragraph_hash in seen_hashes:
                continue
            seen_hashes.add(paragraph_hash)
            entries.append(
                {
                    "text": item,
                    "section_title": section_title or None,
                    "paragraph_hash": paragraph_hash,
                    "page_start": None,
                    "page_end": None,
                }
            )

        if classified_type in {"annual_report", "annual_summary"}:
            entries = [entry for entry in entries if "目录" not in entry["text"][:8] and "......" not in entry["text"]]
        if classified_type == "audit_report":
            entries = [entry for entry in entries if any(token in entry["text"] for token in ("审计", "意见", "关键审计事项", "强调事项", "事务所"))] or entries
        if classified_type == "internal_control_report":
            entries = [entry for entry in entries if any(token in entry["text"] for token in ("内部控制", "缺陷", "整改", "有效性"))] or entries
        if classified_type == "announcement_event":
            entries = [entry for entry in entries if self._detect_event_type(entry["text"]) or self._detect_opinion_type(entry["text"])] or entries
        return entries[:120]

    def _build_structured_extracts(self, document: DocumentMeta, entries: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        candidates = []
        for index, entry in enumerate(entries, start=1):
            candidate = self._build_candidate(document, entry, classified_type, index)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            return []
        try:
            llm_extracts = self._llm_extract(document, candidates, classified_type)
            if llm_extracts:
                return [self._normalize_extract_payload(document, item, index) for index, item in enumerate(llm_extracts, start=1)]
        except Exception as exc:
            logger.warning("document structured extraction failed document_id=%s error=%s", document.id, exc)
        return [self._normalize_extract_payload(document, item, index) for index, item in enumerate(candidates[:16], start=1)]

    def _build_candidate(self, document: DocumentMeta, entry: dict[str, Any], classified_type: str, index: int) -> dict[str, Any] | None:
        text = entry["text"]
        financial_topics = [topic for topic in self.FINANCIAL_TOPICS if topic in text]
        applied_rules = [name for name, keywords in self.RULE_GROUPS.items() if any(keyword in text for keyword in keywords)]
        metric_name, metric_value, metric_unit = self._extract_metric(text)
        event_type = self._detect_event_type(text if classified_type == "announcement_event" else document.document_name)
        opinion_type = self._detect_opinion_type(text)

        if not any([financial_topics, applied_rules, metric_name, event_type, opinion_type]) and index > 8:
            return None

        canonical_risk_key = (
            (applied_rules[0] if applied_rules else None)
            or self._topic_to_risk_key(financial_topics[0] if financial_topics else None)
            or DocumentFeatureService.EVENT_TO_RISK_KEY.get(str(event_type or opinion_type or ""))
        )
        extract_family = "financial_statement" if classified_type in self.FINANCIAL_DOCUMENT_TYPES else "announcement_event" if classified_type == "announcement_event" else "general"
        if opinion_type:
            extract_family = "governance"
        return {
            "title": self._derive_title(text, event_type, opinion_type, financial_topics, applied_rules),
            "extract_type": "event_fact" if event_type else "opinion_fact" if opinion_type else "document_issue",
            "extract_family": extract_family,
            "problem_summary": text[:180],
            "applied_rules": applied_rules,
            "evidence_excerpt": text[:360],
            "detail_level": "financial_deep_dive" if financial_topics else "general",
            "fact_tags": self._dedupe_strings(financial_topics + applied_rules + ([event_type] if event_type else []) + ([opinion_type] if opinion_type else [])),
            "page_number": entry.get("page_start"),
            "page_start": entry.get("page_start"),
            "page_end": entry.get("page_end"),
            "section_title": entry.get("section_title"),
            "paragraph_hash": entry["paragraph_hash"],
            "evidence_span_id": f"{document.id}:{entry['paragraph_hash'][:12]}",
            "keywords": self._dedupe_strings([text[:24]] + financial_topics + applied_rules),
            "financial_topics": self._dedupe_strings(financial_topics),
            "note_refs": self._dedupe_strings(re.findall(r'附注[：:\s]*[一二三四五六七八九十0-9]+', text)),
            "risk_points": self._build_risk_points(text, financial_topics, applied_rules, event_type, opinion_type),
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit,
            "compare_target": None,
            "compare_value": None,
            "period": document.report_period_label,
            "fiscal_year": document.fiscal_year,
            "fiscal_quarter": self._infer_fiscal_quarter(document.report_period_label),
            "event_type": event_type,
            "event_date": self._extract_event_date(text, document),
            "subject": document.document_name,
            "amount": self._extract_amount(text),
            "counterparty": self._extract_counterparty(text),
            "direction": self._infer_direction(text),
            "severity": self._infer_severity(text, event_type, opinion_type),
            "conditions": text[:240] if event_type else None,
            "opinion_type": opinion_type,
            "defect_level": self._infer_defect_level(text, opinion_type),
            "conclusion": text[:200] if opinion_type else None,
            "affected_scope": self._extract_scope(text),
            "auditor_or_board_source": self._extract_auditor_source(text),
            "canonical_risk_key": canonical_risk_key,
        }

    def _llm_extract(self, document: DocumentMeta, candidates: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        if self.llm_client.config_error:
            return []
        lines = []
        for index, item in enumerate(candidates[:12], start=1):
            lines.append(
                f"{index}. title={item['title']}\nfamily={item['extract_family']}\nrisk={item.get('canonical_risk_key') or ''}\n"
                f"event={item.get('event_type') or ''}\nopinion={item.get('opinion_type') or ''}\nevidence={item['evidence_excerpt']}"
            )
        result = self.llm_client.chat_completion(
            "你是上市公司披露文档抽取助手。请返回结构化 JSON，保留有效证据，去掉目录和封面噪声。",
            f"文档名称: {document.document_name}\n分型: {classified_type}\n请从下面候选中挑选 3 到 10 条最重要结果，返回 JSON 数组。\n" + "\n".join(lines),
            json_mode=True,
        )
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict) and isinstance(result.get("extracts"), list):
            return [item for item in result["extracts"] if isinstance(item, dict)]
        return []

    def _normalize_extract_payload(self, document: DocumentMeta, payload: dict[str, Any], index: int) -> dict[str, Any]:
        summary = str(payload.get("problem_summary") or payload.get("evidence_excerpt") or payload.get("title") or document.document_name).strip()
        paragraph_hash = str(payload.get("paragraph_hash") or hashlib.sha1(summary.encode("utf-8")).hexdigest())
        return {
            "title": str(payload.get("title") or f"{document.document_name}-extract-{index}").strip(),
            "extract_type": str(payload.get("extract_type") or "document_issue"),
            "extract_family": str(payload.get("extract_family") or "general"),
            "problem_summary": summary,
            "applied_rules": self._dedupe_strings(list(payload.get("applied_rules") or [])),
            "evidence_excerpt": str(payload.get("evidence_excerpt") or summary)[:360],
            "detail_level": str(payload.get("detail_level") or "general"),
            "fact_tags": self._dedupe_strings(list(payload.get("fact_tags") or [])),
            "page_number": payload.get("page_number"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "section_title": payload.get("section_title"),
            "paragraph_hash": paragraph_hash,
            "evidence_span_id": str(payload.get("evidence_span_id") or f"{document.id}:{paragraph_hash[:12]}"),
            "keywords": self._dedupe_strings(list(payload.get("keywords") or [])),
            "financial_topics": self._dedupe_strings(list(payload.get("financial_topics") or [])),
            "note_refs": self._dedupe_strings(list(payload.get("note_refs") or [])),
            "risk_points": self._dedupe_strings(list(payload.get("risk_points") or [])),
            "metric_name": payload.get("metric_name"),
            "metric_value": self._coerce_float(payload.get("metric_value")),
            "metric_unit": payload.get("metric_unit"),
            "compare_target": payload.get("compare_target"),
            "compare_value": self._coerce_float(payload.get("compare_value")),
            "period": payload.get("period") or document.report_period_label,
            "fiscal_year": payload.get("fiscal_year") or document.fiscal_year,
            "fiscal_quarter": payload.get("fiscal_quarter") or self._infer_fiscal_quarter(document.report_period_label),
            "event_type": payload.get("event_type"),
            "event_date": payload.get("event_date"),
            "subject": payload.get("subject") or document.document_name,
            "amount": self._coerce_float(payload.get("amount")),
            "counterparty": payload.get("counterparty"),
            "direction": payload.get("direction"),
            "severity": payload.get("severity"),
            "conditions": payload.get("conditions"),
            "opinion_type": payload.get("opinion_type"),
            "defect_level": payload.get("defect_level"),
            "conclusion": payload.get("conclusion"),
            "affected_scope": payload.get("affected_scope"),
            "auditor_or_board_source": payload.get("auditor_or_board_source"),
            "canonical_risk_key": payload.get("canonical_risk_key"),
        }

    def _fallback_extracts(self, document: DocumentMeta, entries: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        if entries:
            candidate = self._build_candidate(document, entries[0], classified_type, 1)
            if candidate is not None:
                return [self._normalize_extract_payload(document, candidate, 1)]
        return [
            self._normalize_extract_payload(
                document,
                {
                    "title": document.document_name,
                    "problem_summary": "未命中明确规则，当前仅保留文档摘要。",
                    "evidence_excerpt": document.document_name,
                    "extract_family": "general",
                    "fact_tags": ["fallback"],
                },
                1,
            )
        ]

    def _queue_event_knowledge(self, db: Session, event: ExternalEvent) -> None:
        self.knowledge_index_service.replace_document_chunks(
            db,
            enterprise_id=event.enterprise_id,
            document_id=-event.id,
            document_name=event.title,
            version=self.EXTRACT_VERSION,
            extracts=[
                {
                    "title": event.title,
                    "problem_summary": event.summary or event.title,
                    "evidence_excerpt": event.summary or event.title,
                    "fact_tags": [event.event_type, event.severity, event.regulator or event.source],
                    "keywords": [event.event_type, event.severity],
                }
            ],
        )
        event.parser_version = self.EXTRACT_VERSION
        event.sync_status = "stored"
        db.commit()

    def _latest_override(self, db: Session, *, document_id: int | None = None, enterprise_id: int | None = None, scope: str) -> Any:
        overrides = DocumentRepository(db).list_overrides(document_id=document_id, enterprise_id=enterprise_id, scope=scope)
        return overrides[0] if overrides else None

    def _apply_extract_overrides(self, db: Session, document_id: int, extracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        overrides = {
            override.target_key: override
            for override in DocumentRepository(db).list_overrides(document_id=document_id, scope="event_type")
        }
        for extract in extracts:
            override = overrides.get(str(extract.get("evidence_span_id")))
            if override and override.override_value.get("event_type"):
                extract["event_type"] = str(override.override_value["event_type"])
                if not extract.get("extract_family") or extract.get("extract_family") == "general":
                    extract["extract_family"] = "announcement_event"
        return extracts

    def _extract_metric(self, text: str) -> tuple[str | None, float | None, str | None]:
        metric_name = next((topic for topic in self.FINANCIAL_TOPICS if topic in text), None)
        match = self.MONEY_PATTERN.search(text)
        if not metric_name or not match:
            return None, None, None
        return metric_name, self._coerce_float(match.group("value").replace(",", "")), match.group("unit")

    def _extract_event_date(self, text: str, document: DocumentMeta) -> str | None:
        match = self.DATE_PATTERN.search(text)
        if match:
            return match.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
        return document.announcement_date.isoformat() if document.announcement_date else None

    def _extract_amount(self, text: str) -> float | None:
        match = self.MONEY_PATTERN.search(text)
        return self._coerce_float(match.group("value").replace(",", "")) if match else None

    def _extract_counterparty(self, text: str) -> str | None:
        match = re.search(r"(与|向)(?P<name>[^，。；]{2,30}?)(签署|发生|提供|开展)", text)
        return match.group("name").strip() if match else None

    def _infer_direction(self, text: str) -> str:
        if any(token in text for token in ("回购", "增持", "获批")):
            return "positive"
        if any(token in text for token in ("处罚", "诉讼", "问询", "减值", "缺陷")):
            return "negative"
        return "neutral"

    def _infer_severity(self, text: str, event_type: str | None, opinion_type: str | None) -> str | None:
        if opinion_type:
            return "high" if any(token in text for token in ("重大", "否定意见", "无法表示意见")) else "medium"
        if event_type:
            return "high" if any(token in text for token in ("重大", "处罚", "诉讼", "问询")) else "medium"
        return None

    def _infer_defect_level(self, text: str, opinion_type: str | None) -> str | None:
        if opinion_type != "internal_control_issue":
            return None
        if "重大缺陷" in text:
            return "major"
        if "重要缺陷" in text:
            return "important"
        return "general"

    def _extract_scope(self, text: str) -> str | None:
        if "财务报告内部控制" in text:
            return "financial_reporting_internal_control"
        if "募集资金" in text:
            return "fund_usage"
        return None

    def _extract_auditor_source(self, text: str) -> str | None:
        match = re.search(r"([^\s，。]{2,40}(会计师事务所|董事会|审计委员会))", text)
        return match.group(1) if match else None

    def _detect_event_type(self, text: str) -> str | None:
        for keyword, event_type in self.EVENT_TYPES.items():
            if keyword in text:
                return event_type
        return None

    def _detect_opinion_type(self, text: str) -> str | None:
        for keyword, opinion_type in self.OPINION_TYPES.items():
            if keyword in text:
                return opinion_type
        return None

    def _topic_to_risk_key(self, topic: str | None) -> str | None:
        if topic in {"营业收入", "营业成本", "毛利率"}:
            return "revenue_recognition"
        if topic == "应收账款":
            return "receivable_recoverability"
        if topic in {"存货", "减值"}:
            return "inventory_impairment"
        if topic in {"经营现金流", "净利润", "销售费用", "管理费用", "研发费用"}:
            return "cashflow_quality"
        return None

    def _build_risk_points(self, text: str, financial_topics: list[str], applied_rules: list[str], event_type: str | None, opinion_type: str | None) -> list[str]:
        items = [f"命中风险键：{item}" for item in applied_rules[:2]]
        items.extend([f"关注科目：{item}" for item in financial_topics[:2]])
        if event_type:
            items.append(f"事件类型：{event_type}")
        if opinion_type:
            items.append(f"意见类型：{opinion_type}")
        if any(token in text for token in ("异常", "下降", "减值", "处罚", "诉讼", "缺陷")):
            items.append("披露存在异常或敏感信号")
        return self._dedupe_strings(items)

    def _derive_title(self, text: str, event_type: str | None, opinion_type: str | None, financial_topics: list[str], applied_rules: list[str]) -> str:
        if event_type:
            return event_type
        if opinion_type:
            return opinion_type
        if financial_topics:
            return f"{financial_topics[0]}分析"
        if applied_rules:
            return applied_rules[0]
        return text[:28]

    def _infer_fiscal_quarter(self, period: str | None) -> int | None:
        if not period:
            return None
        if "Q1" in period or "一季" in period:
            return 1
        if "Q2" in period or "半年" in period:
            return 2
        if "Q3" in period or "三季" in period:
            return 3
        if "Q4" in period or "年度" in period:
            return 4
        return None

    def _coerce_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    def _dedupe_strings(self, values: list[str | None]) -> list[str]:
        seen: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.append(text)
        return seen
