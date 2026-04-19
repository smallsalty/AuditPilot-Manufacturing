from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.evidence_summary_service import EvidenceSummaryService
from app.ai.llm_client import LLMClient, LLMRequestError
from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta, ExternalEvent
from app.repositories.document_repository import DocumentRepository
from app.services.announcement_event_analysis_service import AnnouncementEventAnalysisService
from app.services.document_analysis_pipeline import DocumentAnalysisPipeline
from app.services.document_classify_service import DocumentClassifyService
from app.services.document_feature_service import DocumentFeatureService
from app.services.knowledge_index_service import KnowledgeIndexService
from app.utils.display_text import clean_document_title
from app.utils.documents import parse_document_text
from app.utils.embeddings import HashingEmbeddingService


logger = logging.getLogger(__name__)


class DocumentService:
    EXTRACT_VERSION = "document-extract:v4"
    ANALYSIS_GROUPS = (
        "financial_analysis",
        "announcement_events",
        "governance",
        "audit_opinion",
        "internal_control",
    )
    FINANCIAL_DOCUMENT_TYPES = {"annual_report", "annual_summary", "audit_report", "internal_control_report"}
    CANDIDATE_LIMITS = {
        "announcement_event": 6,
        "audit_report": 6,
        "internal_control_report": 6,
        "annual_report": 10,
        "annual_summary": 8,
        "general": 4,
    }
    FALLBACK_LIMITS = {
        "announcement_event": 3,
        "audit_report": 4,
        "internal_control_report": 4,
        "annual_report": 5,
        "annual_summary": 4,
        "general": 2,
    }
    MAX_LLM_CANDIDATES = 10
    LLM_EXTRACT_CANDIDATE_LIMIT = 5
    MAX_EVIDENCE_CHARS = 220
    EXTRACT_FAMILY_BY_EVENT_TYPE = {
        "financial_anomaly": "financial_statement",
        "audit_opinion_issue": "opinion_conclusion",
        "internal_control_issue": "internal_control_conclusion",
        "executive_change": "announcement_event",
        "major_contract": "announcement_event",
        "related_party_transaction": "announcement_event",
        "share_repurchase": "announcement_event",
        "equity_pledge": "announcement_event",
        "penalty_or_inquiry": "announcement_event",
        "litigation": "announcement_event",
        "litigation_arbitration": "announcement_event",
        "guarantee": "announcement_event",
        "convertible_bond": "announcement_event",
    }
    RULE_GROUPS = {
        "revenue_recognition": ["营业收入", "收入确认", "合同负债", "四季度"],
        "receivable_recoverability": ["应收账款", "坏账", "信用减值", "回款"],
        "inventory_impairment": ["存货", "跌价", "减值", "库龄"],
        "cashflow_quality": ["经营现金流", "净利润", "现金流量"],
        "related_party_transaction": ["关联交易", "资金占用", "非经营性资金占用"],
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
    POSITION_PATTERN = re.compile(r"(董事长|总经理|副总经理|财务总监|财务负责人|CFO|董事|监事)")
    PERSON_PATTERN = re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)")

    HIGH_VALUE_SECTION_KEYWORDS = (
        "审计意见",
        "关键审计事项",
        "强调事项",
        "内部控制审计意见",
        "重大缺陷",
        "重要缺陷",
        "整改",
        "关联交易",
        "重大诉讼",
        "处罚",
        "问询",
        "担保",
        "回购",
        "可转债",
    )
    RESPONSIBILITY_ONLY_PATTERNS = (
        "董事会的责任",
        "管理层的责任",
        "我们的责任",
        "审计机构的责任",
        "注册会计师的责任",
        "董事会声明",
    )
    RESPONSIBILITY_PREFIXES = (
        "董事会的责任",
        "管理层的责任",
        "我们的责任",
        "注册会计师的责任",
        "审计机构的责任",
        "董事会声明",
        "致全体股东",
        "致股东",
    )
    FIRM_TAILNOTE_KEYWORDS = (
        "会计师事务所",
        "注册会计师",
        "中国注册会计师",
        "签字注册会计师",
        "报告日期",
        "中国·北京",
    )
    ENGLISH_FOOTER_KEYWORDS = (
        "a member firm",
        "global limited",
        "certified public accountants",
        "ernst & young",
    )
    TYPE_NOISE_PATTERNS = {
        "annual_report": (
            re.compile(r"^(目录|释义)$"),
            re.compile(r"^(公司代码|股票代码|证券代码|证券简称)[:：].*$"),
            re.compile(r"^\d{4}年(?:年度)?报告(?:摘要)?$"),
        ),
        "annual_summary": (
            re.compile(r"^(目录|释义)$"),
            re.compile(r"^(公司代码|股票代码|证券代码|证券简称)[:：].*$"),
            re.compile(r"^\d{4}年(?:年度)?报告(?:摘要)?$"),
        ),
        "audit_report": (
            re.compile(r"^[^，。；]{2,40}（\d{4}）[^，。；]{0,20}号$"),
            re.compile(r"^致[^，。；]{2,40}(股东|董事会).*$"),
            re.compile(r"^[^，。；]{2,40}(会计师事务所|分所).*$"),
            re.compile(r"^(董事会的责任|管理层的责任|我们的责任|注册会计师的责任|董事会声明)[。．]?$"),
        ),
        "internal_control_report": (
            re.compile(r"^[^，。；]{2,40}（\d{4}）[^，。；]{0,20}号$"),
            re.compile(r"^致[^，。；]{2,40}(股东|董事会).*$"),
            re.compile(r"^[^，。；]{2,40}(内部控制审计报告|内部控制评价报告)$"),
            re.compile(r"^(董事会的责任|管理层的责任|我们的责任|注册会计师的责任|董事会声明)[。．]?$"),
        ),
        "announcement_event": (
            re.compile(r"^(联系方式|联系人|联系电话|电子邮箱)[:：].*$"),
            re.compile(r"^特此公告[。.]?$"),
            re.compile(r"^公告编号[:：].*$"),
        ),
        "general": (),
    }

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.embedding_service = HashingEmbeddingService()
        self.llm_client = llm_client or LLMClient()
        self.evidence_summary_service = EvidenceSummaryService(self.llm_client)
        self.announcement_event_analysis_service = AnnouncementEventAnalysisService(self.llm_client)
        self.classify_service = DocumentClassifyService()
        self.feature_service = DocumentFeatureService()
        self.knowledge_index_service = KnowledgeIndexService()
        self._last_extraction_trace: dict[str, Any] | None = None

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
            self._parse_event_record(db, event)
            parsed_events += 1
        return {"documents": parsed_documents, "events": parsed_events}

    def list_extracts(self, db: Session, document_id: int) -> list[DocumentExtractResult]:
        return DocumentRepository(db).list_extracts(document_id)

    def _set_extraction_trace(
        self,
        *,
        analysis_mode: str,
        candidate_count_before_trim: int,
        candidate_count_after_trim: int,
        llm_attempted: bool,
        llm_error: dict[str, Any] | None = None,
        extract_count: int = 0,
    ) -> None:
        self._last_extraction_trace = {
            "analysis_mode": analysis_mode,
            "candidate_count_before_trim": candidate_count_before_trim,
            "candidate_count_after_trim": candidate_count_after_trim,
            "llm_attempted": llm_attempted,
            "llm_error": llm_error,
            "extract_count": extract_count,
        }

    def _analysis_error_payload(self, error: Any) -> dict[str, Any] | None:
        if error is None:
            return None
        if isinstance(error, LLMRequestError):
            return {
                **error.to_dict(),
                "last_error_at": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "message": str(error),
            "status_code": None,
            "error_type": error.__class__.__name__,
            "provider_response_text": None,
            "last_error_at": datetime.now(timezone.utc).isoformat(),
        }

    def _config_error_payload(self) -> dict[str, Any] | None:
        if not self.llm_client.config_error:
            return None
        return {
            "message": self.llm_client.config_error,
            "status_code": None,
            "error_type": "config_error",
            "provider_response_text": None,
            "last_error_at": datetime.now(timezone.utc).isoformat(),
        }

    def _build_analysis_meta(
        self,
        document: DocumentMeta,
        *,
        analysis_status: str,
        analysis_mode: str | None,
        candidate_count: int = 0,
        extract_count: int = 0,
        analysis_groups: list[str] | None = None,
        analyzed_at: str | None = None,
        last_error: dict[str, Any] | None = None,
        classification_meta: dict[str, Any] | None = None,
        cleaning_meta: dict[str, Any] | None = None,
        llm_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        metadata = dict(document.metadata_json or {})
        metadata["analysis_status"] = analysis_status
        analysis_meta = dict(metadata.get("analysis_meta") or {})
        analysis_meta.update(
            {
            "analysis_version": self.EXTRACT_VERSION,
            "analyzed_at": analyzed_at,
            "analysis_mode": analysis_mode,
            "llm_provider": self.llm_client.provider,
            "llm_model": self.llm_client.model,
            "candidate_count": candidate_count,
            "extract_count": extract_count,
            "analysis_groups": analysis_groups or [],
            }
        )
        if llm_diagnostics is not None:
            analysis_meta["llm_diagnostics"] = llm_diagnostics
        metadata["analysis_meta"] = analysis_meta
        if classification_meta is not None:
            metadata["classification_meta"] = classification_meta
        if cleaning_meta is not None:
            metadata["cleaning_meta"] = cleaning_meta
        metadata["last_error"] = last_error
        document.metadata_json = metadata

    def _is_financial_analysis_extract(self, document_type: str | None, extract: dict[str, Any]) -> bool:
        return (
            document_type in self.FINANCIAL_DOCUMENT_TYPES
            and extract.get("extract_family") == "financial_statement"
            and extract.get("detail_level") == "financial_deep_dive"
        )

    def _derive_analysis_groups(self, document: DocumentMeta, extracts: list[dict[str, Any]]) -> list[str]:
        classified_type = document.classified_type or document.document_type or "general"
        groups: list[str] = []
        if any(self._is_financial_analysis_extract(classified_type, extract) for extract in extracts):
            groups.append("financial_analysis")
        if classified_type == "announcement_event" or any(extract.get("extract_family") == "announcement_event" for extract in extracts):
            groups.append("announcement_events")
        if classified_type == "audit_report" or any(
            extract.get("event_type") == "audit_opinion_issue" or extract.get("opinion_type")
            for extract in extracts
        ):
            groups.append("audit_opinion")
        if classified_type == "internal_control_report" or any(
            extract.get("event_type") == "internal_control_issue" or extract.get("defect_level")
            for extract in extracts
        ):
            groups.append("internal_control")
        if any(
            extract.get("event_type") == "executive_change"
            or extract.get("canonical_risk_key") == "governance_instability"
            for extract in extracts
        ):
            groups.append("governance")
        return [group for group in self.ANALYSIS_GROUPS if group in groups]

    def _parse_document_record(self, db: Session, document: DocumentMeta) -> DocumentMeta:
        if not document.file_path and not document.content_text:
            raise ValueError("文档缺少文件路径和正文内容。")

        document.parse_status = "parsing"
        self._build_analysis_meta(
            document,
            analysis_status="running",
            analysis_mode=None,
            candidate_count=0,
            extract_count=0,
            analysis_groups=[],
            analyzed_at=None,
            last_error=None,
        )
        db.commit()
        classification_meta: dict[str, Any] = {}
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

            self._last_extraction_trace = None
            cleaned_entries = self._clean_document(text, classified_type)
            extracts = self._build_structured_extracts(document, cleaned_entries, classified_type)
            if not extracts:
                extracts = self._fallback_extracts(document, cleaned_entries, classified_type)
            extracts = self._apply_extract_overrides(db, document.id, extracts)
            trace = self._last_extraction_trace or {
                "analysis_mode": "rule_only",
                "candidate_count_before_trim": 0,
                "candidate_count_after_trim": 0,
                "llm_attempted": False,
                "llm_error": self._config_error_payload(),
                "extract_count": len(extracts),
            }

            features = self.feature_service.build_features(extracts, enterprise_id=document.enterprise_id, document_id=document.id)
            extract_rows = self._persist_extracts(db, document, extracts)
            self._persist_features(db, document, features, extract_rows)
            self.knowledge_index_service.replace_document_chunks(
                db,
                enterprise_id=document.enterprise_id,
                document_id=document.id,
                document_name=clean_document_title(document.document_name) or document.document_name,
                version=self.EXTRACT_VERSION,
                extracts=extracts,
            )

            self._build_analysis_meta(
                document,
                analysis_status="partial_fallback" if trace.get("analysis_mode") == "hybrid_fallback" else "succeeded",
                analysis_mode=str(trace.get("analysis_mode") or "rule_only"),
                candidate_count=int(trace.get("candidate_count_after_trim") or 0),
                extract_count=len(extracts),
                analysis_groups=self._derive_analysis_groups(document, extracts),
                analyzed_at=datetime.now(timezone.utc).isoformat(),
                last_error=trace.get("llm_error"),
            )

            db.commit()
            db.refresh(document)
            return document
        except Exception as exc:
            db.rollback()
            document = db.get(DocumentMeta, document.id)
            if document is not None:
                document.parse_status = "failed"
                document.sync_status = "parse_failed"
                self._build_analysis_meta(
                    document,
                    analysis_status="failed",
                    analysis_mode=None,
                    candidate_count=0,
                    extract_count=0,
                    analysis_groups=[],
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                    last_error=self._analysis_error_payload(exc),
                )
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
                parameters=extract.get("parameters"),
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
        return self._clean_document_v2(text, classified_type)

    def _clean_document_v2(self, text: str, classified_type: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        section_title = ""
        for raw in self._split_entries(text):
            item = self._normalize_entry_text(raw)
            if not item or self._is_common_noise(item) or len(item) < 6:
                continue
            if self.HEADING_PATTERN.match(item):
                section_title = item[:80]
                continue
            if self._should_skip_by_type(item, classified_type, section_title):
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
        filtered = [entry for entry in entries if self._passes_type_signal(entry, classified_type)]
        return (filtered or entries)[:120]

        if classified_type in {"annual_report", "annual_summary"}:
            entries = [entry for entry in entries if "目录" not in entry["text"][:8] and "......" not in entry["text"]]
        if classified_type == "audit_report":
            entries = [entry for entry in entries if any(token in entry["text"] for token in ("审计", "意见", "关键审计事项", "强调事项", "事务所"))] or entries
        if classified_type == "internal_control_report":
            entries = [entry for entry in entries if any(token in entry["text"] for token in ("内部控制", "缺陷", "整改", "有效性"))] or entries
        if classified_type == "announcement_event":
            entries = [entry for entry in entries if self._detect_event_type(entry["text"]) or self._detect_opinion_type(entry["text"])] or entries
        return entries[:120]

    def _normalize_entry_text(self, raw: str) -> str:
        text = html.unescape(raw or "")
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = self._collapse_repeated_title(text)
        return text

    def _collapse_repeated_title(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) < 8:
            return cleaned
        repeated_with_suffix = re.match(r"^(.{4,60}?报告)(\1(?:摘要)?)$", cleaned)
        if repeated_with_suffix:
            return repeated_with_suffix.group(2)
        for size in range(min(len(cleaned) // 2, 40), 5, -1):
            prefix = cleaned[:size]
            if prefix and cleaned == prefix * (len(cleaned) // len(prefix)) and len(cleaned) % len(prefix) == 0:
                return prefix
        duplicate = re.match(r"^(.{4,60}?)(?:\1){1,}$", cleaned)
        if duplicate:
            return duplicate.group(1)
        return cleaned

    def _is_common_noise(self, text: str) -> bool:
        return any(pattern.match(text) for pattern in self.NOISE_PATTERNS)

    def _should_skip_by_type(self, text: str, classified_type: str, section_title: str) -> bool:
        for pattern in self.TYPE_NOISE_PATTERNS.get(classified_type, ()):
            if pattern.match(text):
                return True
        if classified_type in {"annual_report", "annual_summary"}:
            if "目录" in text[:10] or "......" in text or "………" in text:
                return True
            if re.fullmatch(r"[A-Za-z0-9（）()\- ]{4,}", text):
                return True
        if classified_type in {"audit_report", "internal_control_report"}:
            if self._is_responsibility_noise(text) or self._is_signature_tailnote(text) or self._is_english_footer_noise(text):
                return True
        if classified_type == "announcement_event":
            if text.startswith("公司董事会") or text.startswith("本公司董事会"):
                return True
        return self._is_cover_like_noise(text)

    def _passes_type_signal(self, entry: dict[str, Any], classified_type: str) -> bool:
        text = entry["text"]
        section_title = entry.get("section_title") or ""
        if classified_type in {"annual_report", "annual_summary"}:
            return bool(
                self._detect_event_type(text)
                or self._detect_opinion_type(text)
                or any(topic in text for topic in self.FINANCIAL_TOPICS)
                or any(keyword in text for keyword in ("附注", "减值", "坏账", "跌价", "现金流"))
                or self._contains_high_value_section(section_title)
            )
        if classified_type == "audit_report":
            if self._is_responsibility_noise(text) or self._is_signature_tailnote(text) or self._is_english_footer_noise(text):
                return False
            return bool(
                any(keyword in text for keyword in ("审计意见", "关键审计事项", "强调事项", "保留意见", "否定意见", "无法表示意见", "持续经营"))
                or self._detect_opinion_type(text)
                or self._contains_high_value_section(section_title)
            )
        if classified_type == "internal_control_report":
            if self._is_responsibility_noise(text) or self._is_signature_tailnote(text) or self._is_english_footer_noise(text):
                return False
            return bool(
                any(keyword in text for keyword in ("重大缺陷", "重要缺陷", "整改", "有效性", "内部控制有效", "内部控制无效", "审计意见", "缺陷"))
                or self._detect_opinion_type(text)
                or self._contains_high_value_section(section_title)
            )
        if classified_type == "announcement_event":
            return bool(
                self._detect_event_type(text)
                or self._detect_opinion_type(text)
                or any(keyword in text for keyword in ("金额", "比例", "对象", "价格", "问询", "处罚", "诉讼"))
                or self._contains_high_value_section(section_title)
            )
        return True

    def _is_cover_like_noise(self, text: str) -> bool:
        stripped = text.strip("：:。.;； ")
        if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", stripped):
            return True
        if re.fullmatch(r"[\u4e00-\u9fa5·]{1,8}\s+[\u4e00-\u9fa5·]{1,8}\s+\d{4}年\d{1,2}月\d{1,2}日", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,30}股份有限公司", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,30}股份有限公司全体股东", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,40}（\d{4}）[^，。；]{0,20}号", stripped):
            return True
        return False

    def _contains_high_value_section(self, section_title: str | None) -> bool:
        if not section_title:
            return False
        return any(keyword in section_title for keyword in self.HIGH_VALUE_SECTION_KEYWORDS)

    def _is_responsibility_noise(self, text: str) -> bool:
        normalized = text.strip("：:。．.;； ")
        if normalized in self.RESPONSIBILITY_ONLY_PATTERNS:
            return True
        return any(normalized.startswith(prefix) for prefix in self.RESPONSIBILITY_PREFIXES)

    def _is_signature_tailnote(self, text: str) -> bool:
        normalized = text.strip()
        if re.fullmatch(r"[\u4e00-\u9fa5·]{1,8}\s+[\u4e00-\u9fa5·]{1,8}\s+\d{4}年\d{1,2}月\d{1,2}日", normalized):
            return True
        if any(keyword in normalized for keyword in self.FIRM_TAILNOTE_KEYWORDS):
            return not any(token in normalized for token in ("保留意见", "否定意见", "无法表示意见", "强调事项", "关键审计事项", "重大缺陷", "重要缺陷", "整改", "有效性"))
        return False

    def _is_english_footer_noise(self, text: str) -> bool:
        lowered = text.lower().strip()
        if not lowered or not re.search(r"[a-z]", lowered):
            return False
        if any(keyword in lowered for keyword in self.ENGLISH_FOOTER_KEYWORDS):
            return not any(token in lowered for token in ("opinion", "material weakness", "internal control", "qualified", "adverse", "disclaimer"))
        return False

    def _build_structured_extracts(self, document: DocumentMeta, entries: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        candidates = []
        for index, entry in enumerate(entries, start=1):
            candidate = self._build_candidate(document, entry, classified_type, index)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=0,
                candidate_count_after_trim=0,
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return []
        trimmed_candidates = self._trim_candidates(candidates, classified_type)
        if not trimmed_candidates:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=0,
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return self._fallback_extracts(document, [], classified_type)
        llm_input_chars = sum(len(str(item.get("evidence_excerpt") or "")) for item in trimmed_candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT])
        if self.llm_client.config_error:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return self._fallback_extracts(document, trimmed_candidates, classified_type)
        try:
            llm_extracts = self._llm_extract(document, trimmed_candidates, classified_type)
            if llm_extracts:
                normalized = [self._normalize_extract_payload(document, item, index) for index, item in enumerate(llm_extracts, start=1)]
                filtered = [item for item in normalized if not self._is_low_quality_extract(item)]
                if filtered:
                    self._set_extraction_trace(
                        analysis_mode="llm_primary",
                        candidate_count_before_trim=len(candidates),
                        candidate_count_after_trim=len(trimmed_candidates),
                        llm_attempted=True,
                        llm_error=None,
                        extract_count=len(filtered),
                    )
                    return filtered
            self._set_extraction_trace(
                analysis_mode="hybrid_fallback",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=True,
                llm_error=self._analysis_error_payload(
                    LLMRequestError(
                        "模型未返回有效的结构化抽取结果。",
                        error_type="empty_result",
                        retryable=False,
                    )
                ),
                extract_count=0,
            )
        except Exception as exc:
            self._set_extraction_trace(
                analysis_mode="hybrid_fallback",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=True,
                llm_error=self._analysis_error_payload(exc),
                extract_count=0,
            )
            logger.warning(
                "document structured extraction failed document_id=%s classified_type=%s candidate_count_before_trim=%s candidate_count_after_trim=%s llm_input_chars=%s fallback_used=true error=%s",
                document.id,
                classified_type,
                len(candidates),
                len(trimmed_candidates),
                llm_input_chars,
                exc,
            )
        return self._fallback_extracts(document, trimmed_candidates, classified_type)

    def _build_candidate(self, document: DocumentMeta, entry: dict[str, Any], classified_type: str, index: int) -> dict[str, Any] | None:
        text = entry["text"]
        financial_topics = [topic for topic in self.FINANCIAL_TOPICS if topic in text]
        applied_rules = [name for name, keywords in self.RULE_GROUPS.items() if any(keyword in text for keyword in keywords)]
        metric_name, metric_value, metric_unit = self._extract_metric(text)
        event_type = self._detect_event_type(text if classified_type in {"announcement_event", "annual_report", "annual_summary"} else f"{document.document_name} {text}")
        opinion_type = self._detect_opinion_type(text)
        if not event_type and opinion_type:
            event_type = opinion_type
        if not event_type and classified_type in {"annual_report", "annual_summary"} and (metric_name or financial_topics):
            event_type = "financial_anomaly"

        if not any([financial_topics, applied_rules, metric_name, event_type, opinion_type]) and index > 8:
            return None

        canonical_risk_key = (
            (applied_rules[0] if applied_rules else None)
            or self._topic_to_risk_key(financial_topics[0] if financial_topics else None)
            or DocumentFeatureService.EVENT_TO_RISK_KEY.get(str(event_type or opinion_type or ""))
        )
        extract_family = "financial_statement" if classified_type in self.FINANCIAL_DOCUMENT_TYPES else "announcement_event" if classified_type == "announcement_event" else "general"
        if opinion_type:
            extract_family = "opinion_conclusion"
        parameters = self._extract_parameters(
            text=text,
            document=document,
            classified_type=classified_type,
            event_type=event_type,
            opinion_type=opinion_type,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
        )
        summary = self._build_summary(
            text=text,
            event_type=event_type,
            opinion_type=opinion_type,
            parameters=parameters,
            metric_name=metric_name,
            metric_value=metric_value,
            metric_unit=metric_unit,
            canonical_risk_key=canonical_risk_key,
        )
        evidence_excerpt = self._trim_evidence_safe(text)
        return {
            "title": self._derive_title(text, event_type, opinion_type, financial_topics, applied_rules),
            "extract_type": "event_fact" if event_type else "document_issue",
            "extract_family": extract_family,
            "summary": summary,
            "problem_summary": summary,
            "parameters": parameters,
            "applied_rules": applied_rules,
            "evidence_excerpt": evidence_excerpt,
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
            "_candidate_score": self._score_candidate(
                text=text,
                section_title=entry.get("section_title"),
                classified_type=classified_type,
                event_type=event_type,
                opinion_type=opinion_type,
                applied_rules=applied_rules,
                financial_topics=financial_topics,
                metric_name=metric_name,
            ),
        }

    def _trim_candidates(self, candidates: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        limit = self.CANDIDATE_LIMITS.get(classified_type, self.CANDIDATE_LIMITS["general"])
        ordered = sorted(candidates, key=lambda item: (float(item.get("_candidate_score") or 0.0), len(str(item.get("evidence_excerpt") or ""))), reverse=True)
        trimmed: list[dict[str, Any]] = []
        seen_titles: set[tuple[str, str]] = set()
        for candidate in ordered:
            if self._is_low_quality_extract(candidate):
                continue
            key = (str(candidate.get("title") or ""), str(candidate.get("summary") or ""))
            if key in seen_titles:
                continue
            seen_titles.add(key)
            trimmed.append(candidate)
            if len(trimmed) >= limit:
                break
        return trimmed

    def _score_candidate(
        self,
        *,
        text: str,
        section_title: str | None,
        classified_type: str,
        event_type: str | None,
        opinion_type: str | None,
        applied_rules: list[str],
        financial_topics: list[str],
        metric_name: str | None,
    ) -> float:
        score = 0.0
        if event_type:
            score += 10.0
        if opinion_type:
            score += 10.0
        if applied_rules:
            score += 6.0 + min(len(applied_rules), 2) * 2.0
        if financial_topics:
            score += 4.0 + min(len(financial_topics), 2)
        if metric_name:
            score += 4.0
        if section_title and self._contains_high_value_section(section_title):
            score += 5.0
        if classified_type == "audit_report" and any(token in text for token in ("保留意见", "否定意见", "无法表示意见", "关键审计事项", "强调事项", "持续经营")):
            score += 6.0
        if classified_type == "internal_control_report" and any(token in text for token in ("重大缺陷", "重要缺陷", "整改", "有效性", "无效")):
            score += 6.0
        if classified_type == "announcement_event" and any(token in text for token in ("金额", "比例", "对象", "价格", "期限", "日期")):
            score += 4.0
        if self._is_responsibility_noise(text) or self._is_signature_tailnote(text) or self._is_english_footer_noise(text):
            score -= 20.0
        if self._is_cover_like_noise(text):
            score -= 12.0
        if len(text) < 10:
            score -= 6.0
        return score

    def _trim_evidence_safe(self, text: str, limit: int | None = None) -> str:
        max_chars = limit or self.MAX_EVIDENCE_CHARS
        evidence = text.strip()
        if len(evidence) <= max_chars:
            return evidence
        trimmed = evidence[:max_chars].rstrip("，,；; ")
        return f"{trimmed}…"

    def _trim_evidence(self, text: str) -> str:
        evidence = text.strip()
        if len(evidence) <= self.MAX_EVIDENCE_CHARS:
            return evidence
        return evidence[: self.MAX_EVIDENCE_CHARS].rstrip("，,；; ") + "…"

    def _is_low_quality_extract(self, payload: dict[str, Any]) -> bool:
        summary = str(payload.get("summary") or payload.get("problem_summary") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not summary:
            return True
        if self._is_responsibility_noise(summary) or self._is_signature_tailnote(summary) or self._is_english_footer_noise(summary):
            return True
        if self._is_responsibility_noise(title) or self._is_signature_tailnote(title) or self._is_english_footer_noise(title):
            return True
        if self._is_cover_like_noise(summary) or self._is_cover_like_noise(title):
            return True
        if summary == title and self._is_cover_like_noise(summary):
            return True
        if len(summary) <= 8 and not any([payload.get("event_type"), payload.get("opinion_type"), payload.get("metric_name"), payload.get("applied_rules"), payload.get("fact_tags")]):
            return True
        if not any([payload.get("event_type"), payload.get("opinion_type"), payload.get("metric_name"), payload.get("applied_rules"), payload.get("fact_tags"), payload.get("canonical_risk_key")]):
            if re.fullmatch(r"[^，。；]{2,30}(股份有限公司|内部控制审计报告|审计报告)", summary):
                return True
        return False

    def _build_llm_extract_prompts(
        self,
        document: DocumentMeta,
        candidates: list[dict[str, Any]],
        classified_type: str,
    ) -> tuple[str, str]:
        if self.llm_client.config_error:
            return "", ""
        lines = []
        for index, item in enumerate(candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT], start=1):
            evidence = self._trim_evidence_safe(str(item.get("evidence_excerpt") or ""), limit=120)
            summary = self._trim_evidence_safe(str(item.get("summary") or ""), limit=120)
            parameters = item.get("parameters") or {}
            metric_name = item.get("metric_name") or parameters.get("metric_name") or ""
            lines.append(
                f"{index}. id={index}; event={item.get('event_type') or ''}; "
                f"risk={item.get('canonical_risk_key') or ''}; metric={metric_name}; "
                f"summary={summary}; evidence={evidence}"
            )
        system_prompt = "你是上市公司披露文档抽取助手。请仅对候选段做结构化归纳，返回 JSON 数组。每项必须包含 summary、parameters、event_type、extract_family、evidence_excerpt，不要回显整段原文，不要新增枚举外事件类型。"
        user_prompt = f"文档名称: {document.document_name}\n分型: {classified_type}\n请从下面候选中挑选 3 到 10 条最重要结果，保留固定枚举 event_type，并让 parameters 为扁平 JSON 对象。\n" + "\n".join(lines)
        system_prompt = (
            "You extract audit-risk signals from listed-company disclosures. "
            "Return JSON array only. Each item must contain only: "
            "summary, parameters, event_type, evidence_excerpt. "
            "Do not add markdown, prose, or extra raw text."
        )
        user_prompt = (
            f"document: {clean_document_title(document.document_name) or document.document_name}\n"
            f"type: {classified_type}\n"
            "Pick 1 to 5 important items from candidates. Keep event_type stable. "
            "parameters must be a flat JSON object.\n"
            + "\n".join(lines)
        )
        user_prompt = user_prompt.replace(str(document.document_name), clean_document_title(document.document_name) or str(document.document_name), 1)
        return system_prompt, user_prompt

    def _llm_extract(self, document: DocumentMeta, candidates: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        system_prompt, user_prompt = self._build_llm_extract_prompts(document, candidates, classified_type)
        if not system_prompt:
            return []
        result = self.llm_client.chat_completion(
            system_prompt,
            user_prompt,
            json_mode=True,
            request_kind="document_extract",
            metadata={
                "document_id": document.id,
                "enterprise_id": document.enterprise_id,
                "classified_type": classified_type,
                "candidate_count": min(len(candidates), self.LLM_EXTRACT_CANDIDATE_LIMIT),
                "llm_input_chars": sum(len(str(item.get("evidence_excerpt") or "")) for item in candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT]),
            },
            max_tokens=1024,
            max_attempts=1,
            timeout=30.0,
            strict_json_instruction=False,
        )
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict) and isinstance(result.get("extracts"), list):
            return [item for item in result["extracts"] if isinstance(item, dict)]
        return []

    def _normalize_extract_payload(self, document: DocumentMeta, payload: dict[str, Any], index: int) -> dict[str, Any]:
        summary = str(payload.get("summary") or payload.get("problem_summary") or payload.get("evidence_excerpt") or payload.get("title") or document.document_name).strip()
        paragraph_hash = str(payload.get("paragraph_hash") or hashlib.sha1(summary.encode("utf-8")).hexdigest())
        return {
            "title": str(payload.get("title") or f"{document.document_name}-extract-{index}").strip(),
            "extract_type": str(payload.get("extract_type") or "document_issue"),
            "extract_family": str(payload.get("extract_family") or "general"),
            "summary": summary,
            "problem_summary": summary,
            "parameters": self._normalize_parameters(payload.get("parameters")),
            "applied_rules": self._dedupe_strings(list(payload.get("applied_rules") or [])),
            "evidence_excerpt": self._trim_evidence_safe(str(payload.get("evidence_excerpt") or summary)),
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
        fallback_limit = self.FALLBACK_LIMITS.get(classified_type, self.FALLBACK_LIMITS["general"])
        normalized: list[dict[str, Any]] = []
        for index, entry in enumerate(entries[:fallback_limit], start=1):
            candidate = entry if isinstance(entry, dict) and entry.get("extract_type") else self._build_candidate(document, entry, classified_type, index)
            if candidate is None:
                continue
            payload = self._normalize_extract_payload(document, candidate, index)
            if self._is_low_quality_extract(payload):
                continue
            normalized.append(payload)
        if normalized:
            return normalized
        fallback_summary = "当前未命中高价值候选，已保留最小结构化摘要等待进一步核查。"
        if classified_type in {"audit_report", "internal_control_report"}:
            fallback_summary = "当前未命中有效意见或缺陷候选，已保留最小结构化摘要等待进一步核查。"
        return [
            self._normalize_extract_payload(
                document,
                {
                    "title": clean_document_title(document.document_name) or document.document_name,
                    "summary": fallback_summary,
                    "problem_summary": fallback_summary,
                    "evidence_excerpt": fallback_summary,
                    "extract_family": "general",
                    "parameters": {},
                    "fact_tags": ["fallback"],
                },
                1,
            )
        ]

        if entries:
            candidate = self._build_candidate(document, entries[0], classified_type, 1)
            if candidate is not None:
                return [self._normalize_extract_payload(document, candidate, 1)]
        return [
            self._normalize_extract_payload(
                document,
                {
                    "title": clean_document_title(document.document_name) or document.document_name,
                    "summary": "未命中明确规则，当前仅保留文档摘要。",
                    "problem_summary": "未命中明确规则，当前仅保留文档摘要。",
                    "evidence_excerpt": clean_document_title(document.document_name) or document.document_name,
                    "extract_family": "general",
                    "parameters": {},
                    "fact_tags": ["fallback"],
                },
                1,
            )
        ]

    def _parse_event_record(self, db: Session, event: ExternalEvent) -> None:
        payload = dict(event.payload) if isinstance(event.payload, dict) else {}
        analysis_result = self.announcement_event_analysis_service.analyze_event(event)
        analysis = analysis_result.get("analysis") if isinstance(analysis_result, dict) else None
        meta = analysis_result.get("meta") if isinstance(analysis_result, dict) else None
        analysis_payload = analysis if isinstance(analysis, dict) else {}
        payload["event_analysis"] = analysis_payload
        payload["event_analysis_meta"] = meta if isinstance(meta, dict) else {}
        event.payload = payload
        summary = str(analysis_payload.get("summary") or event.summary or event.title).strip()
        if summary:
            event.summary = summary
        severity = str(analysis_payload.get("severity") or event.severity or "").strip().lower()
        if severity in {"low", "medium", "high"}:
            event.severity = severity
        self._queue_event_knowledge(db, event, analysis_payload)

    def _queue_event_knowledge(self, db: Session, event: ExternalEvent, analysis: dict[str, Any] | None = None) -> None:
        analysis = analysis if isinstance(analysis, dict) else {}
        summary = str(analysis.get("summary") or event.summary or event.title).strip()
        evidence_excerpt = str(analysis.get("evidence_excerpt") or summary).strip()
        fact_tags = [event.event_type, event.severity, event.regulator or event.source]
        fact_tags.extend(str(item) for item in analysis.get("key_facts") or [])
        keywords = [event.event_type, event.severity]
        keywords.extend(str(item) for item in analysis.get("risk_points") or [])
        keywords.extend(str(item) for item in analysis.get("audit_focus") or [])
        self.knowledge_index_service.replace_document_chunks(
            db,
            enterprise_id=event.enterprise_id,
            document_id=-event.id,
            document_name=event.title,
            version=self.EXTRACT_VERSION,
            extracts=[
                {
                    "title": event.title,
                    "summary": summary,
                    "problem_summary": summary,
                    "parameters": event.payload or {},
                    "evidence_excerpt": evidence_excerpt,
                    "fact_tags": [item for item in fact_tags if item],
                    "keywords": [item for item in keywords if item],
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

    def _extract_parameters(
        self,
        *,
        text: str,
        document: DocumentMeta,
        classified_type: str,
        event_type: str | None,
        opinion_type: str | None,
        metric_name: str | None,
        metric_value: float | None,
        metric_unit: str | None,
    ) -> dict[str, Any]:
        parameters: dict[str, Any] = {}
        event_date = self._extract_event_date(text, document)
        amount = self._extract_amount(text)
        counterparty = self._extract_counterparty(text)
        person_name = self._extract_person_name(text)
        position = self._extract_position(text)
        direction = self._infer_direction(text)
        severity = self._infer_severity(text, event_type, opinion_type)

        if event_date:
            parameters["event_date"] = event_date
        if amount is not None:
            parameters["amount"] = amount
        if counterparty:
            parameters["counterparty"] = counterparty
        if person_name:
            parameters["person_name"] = person_name
        if position:
            parameters["position"] = position
        if event_type:
            parameters["direction"] = direction
        if severity:
            parameters["severity"] = severity

        if event_type == "share_repurchase":
            parameters["repurchase_amount_upper"] = amount
            repurchase_price = self._extract_named_amount(text, ("回购价格上限", "回购价格不超过", "回购价格"))
            if repurchase_price is not None:
                parameters["repurchase_price_upper"] = repurchase_price
            ratio_to_cash = self._extract_named_ratio(text, ("占货币资金", "占现金"))
            if ratio_to_cash is not None:
                parameters["ratio_to_cash"] = ratio_to_cash
        elif event_type == "convertible_bond":
            if "下修" in text:
                parameters["downward_revision_triggered"] = True
            premium_rate = self._extract_named_ratio(text, ("溢价率",))
            if premium_rate is not None:
                parameters["premium_rate"] = premium_rate
            maturity_date = self._extract_named_date(text, ("到期日", "到期时间"))
            if maturity_date:
                parameters["maturity_date"] = maturity_date
        elif event_type == "executive_change":
            change_type = self._infer_change_type(text)
            if change_type:
                parameters["change_type"] = change_type
        elif event_type == "litigation":
            ratio_to_net_profit = self._extract_named_ratio(text, ("占净利润", "占公司净利润"))
            if ratio_to_net_profit is not None:
                parameters["ratio_to_net_profit"] = ratio_to_net_profit
            case_stage = self._extract_case_stage(text)
            if case_stage:
                parameters["case_stage"] = case_stage
        elif event_type == "penalty_or_inquiry":
            issuing_authority = self._extract_issuing_authority(text)
            if issuing_authority:
                parameters["issuing_authority"] = issuing_authority
            penalty_type = self._infer_penalty_type(text)
            if penalty_type:
                parameters["penalty_type"] = penalty_type
        elif event_type == "guarantee":
            parameters["guarantee_amount"] = amount
            guaranteed_party = self._extract_guaranteed_party(text)
            if guaranteed_party:
                parameters["guaranteed_party"] = guaranteed_party
            ratio_to_net_assets = self._extract_named_ratio(text, ("占净资产",))
            if ratio_to_net_assets is not None:
                parameters["ratio_to_net_assets"] = ratio_to_net_assets
        elif event_type == "related_party_transaction":
            transaction_type = self._infer_transaction_type(text)
            if transaction_type:
                parameters["transaction_type"] = transaction_type
            if "定价依据" in text and any(token in text for token in ("未", "不明确", "缺失")):
                parameters["pricing_basis"] = "missing"
        elif event_type == "audit_opinion_issue":
            parameters["opinion_type"] = self._extract_audit_opinion_type(text) or opinion_type
            affected_scope = self._extract_scope(text)
            if affected_scope:
                parameters["affected_scope"] = affected_scope
            auditor = self._extract_auditor_source(text)
            if auditor:
                parameters["auditor_or_board_source"] = auditor
        elif event_type == "internal_control_issue":
            parameters["defect_level"] = self._infer_defect_level(text, opinion_type)
            conclusion = self._extract_conclusion(text)
            if conclusion:
                parameters["conclusion"] = conclusion
            affected_scope = self._extract_scope(text)
            if affected_scope:
                parameters["affected_scope"] = affected_scope
        elif event_type == "financial_anomaly":
            if metric_name:
                parameters["metric_name"] = metric_name
            if metric_value is not None:
                parameters["current_value"] = metric_value
            if metric_unit:
                parameters["metric_unit"] = metric_unit
            if document.report_period_label:
                parameters["period"] = document.report_period_label
            if classified_type in {"annual_report", "annual_summary"}:
                parameters["fiscal_year"] = document.fiscal_year

        return {key: value for key, value in parameters.items() if value not in (None, "", [])}

    def _build_summary(
        self,
        *,
        text: str,
        event_type: str | None,
        opinion_type: str | None,
        parameters: dict[str, Any],
        metric_name: str | None,
        metric_value: float | None,
        metric_unit: str | None,
        canonical_risk_key: str | None,
    ) -> str:
        if event_type == "share_repurchase":
            amount = parameters.get("repurchase_amount_upper") or parameters.get("amount")
            suffix = f" 涉及金额约{amount}{metric_unit or ''}。" if amount is not None else "。"
            return f"公司披露股份回购安排，需关注资金压力与回购执行意图。{suffix}".replace("。。", "。")
        if event_type == "convertible_bond":
            return "公司披露可转债相关事项，需关注转股动力、现金流承压与后续融资安排。"
        if event_type == "executive_change":
            position = parameters.get("position") or "关键岗位"
            return f"公司披露{position}变动，需关注财务治理稳定性与交接控制。"
        if event_type == "litigation":
            return "公司披露诉讼或仲裁事项，需关注预计负债、披露充分性与经营影响。"
        if event_type == "penalty_or_inquiry":
            return "公司披露处罚或监管问询事项，需关注合规风险、整改进展与信息披露影响。"
        if event_type == "guarantee":
            return "公司披露担保事项，需关注担保规模、被担保对象与潜在偿付压力。"
        if event_type == "related_party_transaction":
            return "公司披露关联交易事项，需关注交易公允性、审批程序与资金流向。"
        if event_type == "audit_opinion_issue":
            opinion = parameters.get("opinion_type") or opinion_type or "审计意见异常"
            return f"审计报告披露{opinion}，需重点关注影响事项及相关会计处理。"
        if event_type == "internal_control_issue":
            defect_level = parameters.get("defect_level") or "内控缺陷"
            return f"内控报告披露{defect_level}或控制结论异常，需关注整改落实与财务报告可靠性。"
        if event_type == "financial_anomaly":
            metric_label = metric_name or "财务指标"
            value_text = f"{metric_value}{metric_unit or ''}" if metric_value is not None else "存在异常变化"
            return f"文档披露的{metric_label}显示异常信号，当前值为{value_text}，需结合规则进一步核查。"
        if canonical_risk_key:
            return f"文档片段命中{canonical_risk_key}相关线索，需结合证据与规则继续核查。"
        compact = re.split(r"[。；;]", text.strip())[0][:64].rstrip("，,：: ")
        return f"{compact}。"

    def _normalize_parameters(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items() if item not in (None, "", [])}
        return {}

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

    def _extract_person_name(self, text: str) -> str | None:
        match = self.PERSON_PATTERN.search(text)
        return match.group("name").strip() if match else None

    def _extract_position(self, text: str) -> str | None:
        match = self.POSITION_PATTERN.search(text)
        return match.group(1).strip() if match else None

    def _extract_named_amount(self, text: str, labels: tuple[str, ...]) -> float | None:
        for label in labels:
            match = re.search(rf"{re.escape(label)}[^0-9]{{0,8}}(?P<value>\d[\d,]*\.?\d*)", text)
            if match:
                return self._coerce_float(match.group("value").replace(",", ""))
        return None

    def _extract_named_ratio(self, text: str, labels: tuple[str, ...]) -> float | None:
        for label in labels:
            match = re.search(rf"{re.escape(label)}[^0-9]{{0,8}}(?P<value>\d[\d,]*\.?\d*)\s*%", text)
            if match:
                value = self._coerce_float(match.group("value"))
                return None if value is None else value / 100.0
        return None

    def _extract_named_date(self, text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            match = re.search(rf"{re.escape(label)}[^0-9]{{0,8}}(20\d{{2}}[-/.年]\d{{1,2}}[-/.月]\d{{1,2}}日?)", text)
            if match:
                return match.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
        return None

    def _infer_change_type(self, text: str) -> str | None:
        if "辞职" in text:
            return "resignation"
        if any(token in text for token in ("聘任", "任命", "选举")):
            return "appointment"
        if "离任" in text:
            return "departure"
        return None

    def _extract_case_stage(self, text: str) -> str | None:
        for token in ("一审", "二审", "执行", "立案", "仲裁"):
            if token in text:
                return token
        return None

    def _extract_issuing_authority(self, text: str) -> str | None:
        match = re.search(r"(中国证监会|证券交易所|证监局|财政部|审计署|银保监会|法院|交易所)", text)
        return match.group(1) if match else None

    def _infer_penalty_type(self, text: str) -> str | None:
        for token in ("行政处罚", "监管问询", "监管函", "警示函", "立案调查"):
            if token in text:
                return token
        return None

    def _extract_guaranteed_party(self, text: str) -> str | None:
        match = re.search(r"为(?P<name>[^，。；]{2,30}?)(提供担保|担保)", text)
        return match.group("name").strip() if match else None

    def _infer_transaction_type(self, text: str) -> str | None:
        for token in ("采购", "销售", "借款", "担保", "资金拆借", "租赁"):
            if token in text:
                return token
        return None

    def _extract_audit_opinion_type(self, text: str) -> str | None:
        for token in ("标准无保留意见", "保留意见", "否定意见", "无法表示意见", "强调事项段"):
            if token in text:
                return token
        return None

    def _extract_conclusion(self, text: str) -> str | None:
        for token in ("有效", "无效", "存在重大缺陷", "存在重要缺陷"):
            if token in text:
                return token
        return None

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

    def _should_skip_by_type(self, text: str, classified_type: str, section_title: str) -> bool:
        for pattern in self.TYPE_NOISE_PATTERNS.get(classified_type, ()):
            if pattern.match(text):
                return True
        if classified_type in {"annual_report", "annual_summary"}:
            if "目录" in text[:10] or "......" in text or "……" in text:
                return True
            if re.fullmatch(r"[A-Za-z0-9（）()\- ]{4,}", text):
                return True
            if re.fullmatch(r"(?:20\d{2}年)?(?:半年度|年度)?报告(?:摘要)?", text):
                return True
        if classified_type in {"audit_report", "internal_control_report"}:
            if self._is_responsibility_noise(text) or self._is_signature_tailnote(text) or self._is_english_footer_noise(text):
                return True
        if classified_type == "announcement_event":
            if text.startswith("公司董事会") or text.startswith("本公司董事会"):
                return True
        return self._is_cover_like_noise(text)

    def _llm_extract(self, document: DocumentMeta, candidates: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        system_prompt, user_prompt = self._build_llm_extract_prompts(document, candidates, classified_type)
        if not system_prompt:
            return []
        result = self.llm_client.chat_completion(
            system_prompt,
            user_prompt,
            json_mode=True,
            request_kind="document_extract",
            metadata={
                "document_id": document.id,
                "enterprise_id": document.enterprise_id,
                "classified_type": classified_type,
                "candidate_count": min(len(candidates), self.LLM_EXTRACT_CANDIDATE_LIMIT),
                "llm_input_chars": sum(len(str(item.get("evidence_excerpt") or "")) for item in candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT]),
            },
            max_tokens=1024,
            max_attempts=1,
            timeout=30.0,
            strict_json_instruction=False,
        )
        return self._extract_llm_items(result)

    def _extract_llm_items(self, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        if isinstance(result.get("items"), list):
            if result.get("payload_mode") == "partial_list":
                logger.info(
                    "document_extract partial_json_recovered document_id=%s payload_mode=%s raw_prefix_kind=%s recovered_count=%s",
                    None,
                    result.get("payload_mode"),
                    result.get("raw_prefix_kind"),
                    len(result.get("items") or []),
                )
            return [item for item in result["items"] if isinstance(item, dict)]
        if isinstance(result.get("extracts"), list):
            return [item for item in result["extracts"] if isinstance(item, dict)]
        raw = result.get("raw")
        if isinstance(raw, str) and raw.strip():
            recovered = self._recover_json_payload(raw)
            if isinstance(recovered, list):
                return [item for item in recovered if isinstance(item, dict)]
            if isinstance(recovered, dict):
                if isinstance(recovered.get("items"), list):
                    return [item for item in recovered["items"] if isinstance(item, dict)]
                if isinstance(recovered.get("extracts"), list):
                    return [item for item in recovered["extracts"] if isinstance(item, dict)]
        return []

    def _recover_json_payload(self, raw: str) -> Any:
        stripped = str(raw or "").strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        block = self._extract_json_block_from_raw(stripped)
        if not block:
            return None
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            return None

    def _extract_json_block_from_raw(self, raw: str) -> str | None:
        start = None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(raw):
            if start is None:
                if char in "{[":
                    start = index
                    depth = 1
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char in "{[":
                depth += 1
                continue
            if char in "}]":
                depth -= 1
                if depth == 0:
                    return raw[start : index + 1].strip()
        return None

    def _normalize_extract_payload(self, document: DocumentMeta, payload: dict[str, Any], index: int) -> dict[str, Any]:
        display_name = clean_document_title(document.document_name) or document.document_name
        summary = self._clean_summary_like_text(
            payload.get("summary")
            or payload.get("problem_summary")
            or payload.get("evidence_excerpt")
            or payload.get("title")
            or display_name
        )
        if not summary:
            summary = display_name
        title = self._clean_summary_like_text(payload.get("title") or f"{display_name}-extract-{index}") or f"{display_name}-extract-{index}"
        raw_evidence_excerpt = self._clean_summary_like_text(payload.get("evidence_excerpt") or summary)
        paragraph_hash = str(payload.get("paragraph_hash") or hashlib.sha1(summary.encode("utf-8")).hexdigest())
        event_type = payload.get("event_type")
        opinion_type = payload.get("opinion_type")
        metric_name = payload.get("metric_name")
        evidence_excerpt = self.evidence_summary_service.summarize_evidence(
            title=title,
            text=raw_evidence_excerpt or summary,
            evidence_type="document_extract",
            report_period=str(payload.get("period") or document.report_period_label or ""),
            context=summary,
        )
        evidence_excerpt = self._trim_evidence_safe(evidence_excerpt or raw_evidence_excerpt or summary)
        risk_points = self._dedupe_strings(list(payload.get("risk_points") or []))
        applied_rules, canonical_risk_key = self._resolve_extract_rules(
            payload=payload,
            title=title,
            summary=summary,
            evidence_excerpt=evidence_excerpt,
            event_type=event_type,
            opinion_type=opinion_type,
            risk_points=risk_points,
        )
        extract_family = self._resolve_extract_family(
            document=document,
            payload=payload,
            event_type=event_type,
            opinion_type=opinion_type,
            metric_name=metric_name,
        )
        return {
            "title": title,
            "extract_type": str(payload.get("extract_type") or "document_issue"),
            "extract_family": extract_family,
            "summary": summary,
            "problem_summary": summary,
            "parameters": self._normalize_parameters(payload.get("parameters")),
            "applied_rules": applied_rules,
            "evidence_excerpt": evidence_excerpt,
            "detail_level": str(payload.get("detail_level") or "general"),
            "fact_tags": self._dedupe_strings(list(payload.get("fact_tags") or [])),
            "page_number": payload.get("page_number"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "section_title": self._clean_summary_like_text(payload.get("section_title")) or payload.get("section_title"),
            "paragraph_hash": paragraph_hash,
            "evidence_span_id": str(payload.get("evidence_span_id") or f"{document.id}:{paragraph_hash[:12]}"),
            "keywords": self._dedupe_strings(list(payload.get("keywords") or [])),
            "financial_topics": self._dedupe_strings(list(payload.get("financial_topics") or [])),
            "note_refs": self._dedupe_strings(list(payload.get("note_refs") or [])),
            "risk_points": risk_points,
            "metric_name": metric_name,
            "metric_value": self._coerce_float(payload.get("metric_value")),
            "metric_unit": payload.get("metric_unit"),
            "compare_target": payload.get("compare_target"),
            "compare_value": self._coerce_float(payload.get("compare_value")),
            "period": payload.get("period") or document.report_period_label,
            "fiscal_year": payload.get("fiscal_year") or document.fiscal_year,
            "fiscal_quarter": payload.get("fiscal_quarter") or self._infer_fiscal_quarter(document.report_period_label),
            "event_type": event_type,
            "event_date": payload.get("event_date"),
            "subject": self._clean_summary_like_text(payload.get("subject") or display_name) or display_name,
            "amount": self._coerce_float(payload.get("amount")),
            "counterparty": self._clean_summary_like_text(payload.get("counterparty")),
            "direction": payload.get("direction"),
            "severity": payload.get("severity"),
            "conditions": self._clean_summary_like_text(payload.get("conditions")),
            "opinion_type": opinion_type,
            "defect_level": payload.get("defect_level"),
            "conclusion": self._clean_summary_like_text(payload.get("conclusion")),
            "affected_scope": payload.get("affected_scope"),
            "auditor_or_board_source": self._clean_summary_like_text(payload.get("auditor_or_board_source")),
            "canonical_risk_key": canonical_risk_key,
        }

    def _resolve_extract_rules(
        self,
        *,
        payload: dict[str, Any],
        title: str,
        summary: str,
        evidence_excerpt: str,
        event_type: Any,
        opinion_type: Any,
        risk_points: list[str],
    ) -> tuple[list[str], str | None]:
        applied_rules = self._dedupe_strings(list(payload.get("applied_rules") or []))
        canonical_risk_key = str(payload.get("canonical_risk_key") or "").strip() or None
        if not canonical_risk_key:
            canonical_risk_key = DocumentFeatureService.EVENT_TO_RISK_KEY.get(
                str(event_type or opinion_type or "").strip()
            )
        if not applied_rules and canonical_risk_key:
            applied_rules = [canonical_risk_key]
        if not applied_rules:
            fallback_text = " ".join(
                part for part in [title, summary, evidence_excerpt, " ".join(risk_points)] if part
            )
            applied_rules = self._match_rule_groups(fallback_text)
            if not canonical_risk_key and applied_rules:
                canonical_risk_key = applied_rules[0]
        return self._dedupe_strings(applied_rules), canonical_risk_key

    def _match_rule_groups(self, text: str) -> list[str]:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return []
        return [
            name
            for name, keywords in self.RULE_GROUPS.items()
            if any(keyword in normalized_text for keyword in keywords)
        ]

    def _resolve_extract_family(
        self,
        *,
        document: DocumentMeta,
        payload: dict[str, Any],
        event_type: Any,
        opinion_type: Any,
        metric_name: Any,
    ) -> str:
        event_name = str(event_type or "").strip()
        if event_name in self.EXTRACT_FAMILY_BY_EVENT_TYPE:
            return self.EXTRACT_FAMILY_BY_EVENT_TYPE[event_name]
        if opinion_type:
            return "opinion_conclusion"
        if document.classified_type in self.FINANCIAL_DOCUMENT_TYPES and (
            metric_name or payload.get("detail_level") == "financial_deep_dive" or payload.get("financial_topics")
        ):
            return "financial_statement"
        return "general"

    def _clean_summary_like_text(self, value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = self._collapse_repeated_title(text)
        if re.fullmatch(r"(?:20\d{2}年)?(?:半年度|年度)?报告(?:摘要)?", text):
            return ""
        return text

    def _apply_extract_overrides(self, db: Session, document_id: int, extracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        overrides = {
            override.target_key: override
            for override in DocumentRepository(db).list_overrides(document_id=document_id, scope="event_type")
        }
        document = db.get(DocumentMeta, document_id)
        for extract in extracts:
            override = overrides.get(str(extract.get("evidence_span_id")))
            if override and override.override_value.get("event_type"):
                extract["event_type"] = str(override.override_value["event_type"])
                extract["extract_family"] = self._resolve_extract_family(
                    document=document or type("DocumentStub", (), {"classified_type": None, "report_period_label": None, "fiscal_year": None})(),
                    payload=extract,
                    event_type=extract.get("event_type"),
                    opinion_type=extract.get("opinion_type"),
                    metric_name=extract.get("metric_name"),
                )
                applied_rules, canonical_risk_key = self._resolve_extract_rules(
                    payload=extract,
                    title=str(extract.get("title") or ""),
                    summary=str(extract.get("summary") or extract.get("problem_summary") or ""),
                    evidence_excerpt=str(extract.get("evidence_excerpt") or ""),
                    event_type=extract.get("event_type"),
                    opinion_type=extract.get("opinion_type"),
                    risk_points=self._dedupe_strings(list(extract.get("risk_points") or [])),
                )
                extract["applied_rules"] = applied_rules
                extract["canonical_risk_key"] = canonical_risk_key
        return extracts

    def _build_structured_extracts(self, document: DocumentMeta, entries: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        setattr(self, "_last_llm_payload_diagnostics", None)
        candidates = []
        for index, entry in enumerate(entries, start=1):
            candidate = self._build_candidate(document, entry, classified_type, index)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=0,
                candidate_count_after_trim=0,
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return []
        trimmed_candidates = self._trim_candidates(candidates, classified_type)
        if not trimmed_candidates:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=0,
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return self._fallback_extracts(document, [], classified_type)
        llm_input_chars = sum(len(str(item.get("evidence_excerpt") or "")) for item in trimmed_candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT])
        if self.llm_client.config_error:
            self._set_extraction_trace(
                analysis_mode="rule_only",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=False,
                llm_error=self._config_error_payload(),
                extract_count=0,
            )
            return self._fallback_extracts(document, trimmed_candidates, classified_type)
        try:
            llm_extracts = self._llm_extract(document, trimmed_candidates, classified_type)
            if llm_extracts:
                normalized = [self._normalize_extract_payload(document, item, index) for index, item in enumerate(llm_extracts, start=1)]
                filtered = [item for item in normalized if not self._is_low_quality_extract(item)]
                if filtered:
                    self._set_extraction_trace(
                        analysis_mode="llm_primary",
                        candidate_count_before_trim=len(candidates),
                        candidate_count_after_trim=len(trimmed_candidates),
                        llm_attempted=True,
                        llm_error=None,
                        extract_count=len(filtered),
                    )
                    return filtered
            llm_error = self._build_llm_extract_fallback_error()
            if llm_error is None:
                llm_error = self._analysis_error_payload(
                    LLMRequestError(
                        "模型未返回有效的结构化抽取结果。",
                        error_type="empty_result",
                        retryable=False,
                    )
                )
            self._set_extraction_trace(
                analysis_mode="hybrid_fallback",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=True,
                llm_error=llm_error,
                extract_count=0,
            )
        except Exception as exc:
            self._set_extraction_trace(
                analysis_mode="hybrid_fallback",
                candidate_count_before_trim=len(candidates),
                candidate_count_after_trim=len(trimmed_candidates),
                llm_attempted=True,
                llm_error=self._analysis_error_payload(exc),
                extract_count=0,
            )
            logger.warning(
                "document structured extraction failed document_id=%s classified_type=%s candidate_count_before_trim=%s candidate_count_after_trim=%s llm_input_chars=%s fallback_used=true error=%s",
                document.id,
                classified_type,
                len(candidates),
                len(trimmed_candidates),
                llm_input_chars,
                exc,
            )
        return self._fallback_extracts(document, trimmed_candidates, classified_type)

    def _llm_extract(self, document: DocumentMeta, candidates: list[dict[str, Any]], classified_type: str) -> list[dict[str, Any]]:
        setattr(self, "_last_llm_payload_diagnostics", None)
        system_prompt, user_prompt = self._build_llm_extract_prompts(document, candidates, classified_type)
        if not system_prompt:
            return []
        result = self.llm_client.chat_completion(
            system_prompt,
            user_prompt,
            json_mode=True,
            request_kind="document_extract",
            metadata={
                "document_id": document.id,
                "enterprise_id": document.enterprise_id,
                "classified_type": classified_type,
                "candidate_count": min(len(candidates), self.LLM_EXTRACT_CANDIDATE_LIMIT),
                "llm_input_chars": sum(len(str(item.get("evidence_excerpt") or "")) for item in candidates[: self.LLM_EXTRACT_CANDIDATE_LIMIT]),
            },
            max_tokens=1024,
            max_attempts=2,
            timeout=30.0,
            strict_json_instruction=True,
        )
        return self._extract_llm_items(result, document_id=document.id)

    def _extract_llm_items(self, result: Any, document_id: int | None = None) -> list[dict[str, Any]]:
        setattr(self, "_last_llm_payload_diagnostics", None)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        if isinstance(result.get("items"), list):
            if result.get("payload_mode") == "partial_list":
                logger.info(
                    "document_extract partial_json_recovered document_id=%s payload_mode=%s raw_prefix_kind=%s recovered_count=%s",
                    document_id,
                    result.get("payload_mode"),
                    result.get("raw_prefix_kind"),
                    len(result.get("items") or []),
                )
            return [item for item in result["items"] if isinstance(item, dict)]
        if isinstance(result.get("extracts"), list):
            return [item for item in result["extracts"] if isinstance(item, dict)]
        raw = result.get("raw")
        if isinstance(raw, str) and raw.strip():
            recovered = self._recover_json_payload(raw)
            if isinstance(recovered, list):
                return [item for item in recovered if isinstance(item, dict)]
            if isinstance(recovered, dict):
                if isinstance(recovered.get("items"), list):
                    return [item for item in recovered["items"] if isinstance(item, dict)]
                if isinstance(recovered.get("extracts"), list):
                    return [item for item in recovered["extracts"] if isinstance(item, dict)]
            partial_items = self._recover_partial_json_items(raw, result.get("raw_prefix_kind"))
            if partial_items:
                setattr(
                    self,
                    "_last_llm_payload_diagnostics",
                    {
                        "mode": "partial_json_recovered",
                        "payload_mode": result.get("payload_mode"),
                        "raw_prefix_kind": result.get("raw_prefix_kind"),
                        "recovered_count": len(partial_items),
                    },
                )
                logger.info(
                    "document_extract partial_json_recovered document_id=%s payload_mode=%s raw_prefix_kind=%s recovered_count=%s",
                    document_id,
                    result.get("payload_mode"),
                    result.get("raw_prefix_kind"),
                    len(partial_items),
                )
                return partial_items
            if result.get("truncated_json_prefix"):
                provider_response = self._trim_evidence_safe(raw)
                setattr(
                    self,
                    "_last_llm_payload_diagnostics",
                    {
                        "mode": "truncated_json_fallback",
                        "payload_mode": result.get("payload_mode"),
                        "raw_prefix_kind": result.get("raw_prefix_kind"),
                        "provider_response_text": provider_response,
                    },
                )
                logger.info(
                    "document_extract truncated_json_fallback document_id=%s payload_mode=%s raw_prefix_kind=%s",
                    document_id,
                    result.get("payload_mode"),
                    result.get("raw_prefix_kind"),
                )
        return []

    def _build_llm_extract_fallback_error(self) -> dict[str, Any] | None:
        diagnostics = getattr(self, "_last_llm_payload_diagnostics", None)
        setattr(self, "_last_llm_payload_diagnostics", None)
        if not diagnostics:
            return None
        if diagnostics.get("mode") != "truncated_json_fallback":
            return None
        return self._analysis_error_payload(
            LLMRequestError(
                "模型返回了截断的 JSON，已回退到规则抽取结果。",
                error_type="truncated_json_fallback",
                provider_response_text=diagnostics.get("provider_response_text"),
                retryable=False,
            )
        )

    def _recover_partial_json_items(self, raw: str, prefix_kind: Any) -> list[dict[str, Any]]:
        text = str(raw or "").strip()
        if not text:
            return []
        kind = str(prefix_kind or "")
        if kind == "object_prefix":
            first_array = text.find("[")
            if first_array != -1:
                return self._recover_partial_json_array_items(text[first_array:])
            first_object = text.find("{")
            if first_object == -1:
                return []
            try:
                payload, _ = json.JSONDecoder().raw_decode(text, first_object)
            except json.JSONDecodeError:
                return []
            if isinstance(payload, dict):
                if isinstance(payload.get("items"), list):
                    return [item for item in payload["items"] if isinstance(item, dict)]
                if isinstance(payload.get("extracts"), list):
                    return [item for item in payload["extracts"] if isinstance(item, dict)]
                return [payload]
            return []
        return self._recover_partial_json_array_items(text)

    def _recover_partial_json_array_items(self, raw: str) -> list[dict[str, Any]]:
        start = raw.find("[")
        if start == -1:
            return []
        decoder = json.JSONDecoder()
        items: list[dict[str, Any]] = []
        index = start + 1
        while index < len(raw):
            while index < len(raw) and raw[index] in " \r\n\t,":
                index += 1
            if index >= len(raw) or raw[index] == "]":
                break
            if raw[index] != "{":
                break
            try:
                payload, end = decoder.raw_decode(raw, index)
            except json.JSONDecodeError:
                break
            if not isinstance(payload, dict):
                break
            items.append(payload)
            index = end
        return items

    def _parse_document_record(self, db: Session, document: DocumentMeta) -> DocumentMeta:
        if not document.file_path and not document.content_text:
            raise ValueError("文档缺少文件路径和正文内容。")

        document.parse_status = "parsing"
        self._build_analysis_meta(
            document,
            analysis_status="running",
            analysis_mode=None,
            candidate_count=0,
            extract_count=0,
            analysis_groups=[],
            analyzed_at=None,
            last_error=None,
            classification_meta={},
            cleaning_meta={},
            llm_diagnostics=None,
        )
        db.commit()

        try:
            text = document.content_text or parse_document_text(document.file_path or "")
            document.content_text = text
            pipeline = DocumentAnalysisPipeline(self)
            override = self._latest_override(db, document_id=document.id, scope="classification")
            classification = self.classify_service.classify(document, text, override)

            document.classified_type = classification.classified_type
            document.classification_version = self.classify_service.CLASSIFICATION_VERSION
            document.classification_source = classification.classification_source
            document.parse_status = "parsed"
            document.parser_version = self.EXTRACT_VERSION
            if document.sync_status == "parse_queued":
                document.sync_status = "stored"

            self._retire_current_rows(db, document.id)
            analysis_result = pipeline.run(
                document=document,
                text=text,
                classified_type=classification.classified_type,
            )
            extracts = self._apply_extract_overrides(db, document.id, analysis_result["extracts"])
            self._last_extraction_trace = analysis_result

            if extracts:
                features = self.feature_service.build_features(
                    extracts,
                    enterprise_id=document.enterprise_id,
                    document_id=document.id,
                )
                extract_rows = self._persist_extracts(db, document, extracts)
                self._persist_features(db, document, features, extract_rows)

            self.knowledge_index_service.replace_document_chunks(
                db,
                enterprise_id=document.enterprise_id,
                document_id=document.id,
                document_name=clean_document_title(document.document_name) or document.document_name,
                version=self.EXTRACT_VERSION,
                extracts=extracts,
            )

            classification_meta = pipeline.build_classification_meta(
                document=document,
                text=text,
                classification=classification,
            )
            self._build_analysis_meta(
                document,
                analysis_status=str(analysis_result.get("analysis_status") or "failed"),
                analysis_mode=str(analysis_result.get("analysis_mode") or "failed"),
                candidate_count=int(analysis_result.get("candidate_count_after_trim") or 0),
                extract_count=len(extracts),
                analysis_groups=self._derive_analysis_groups(document, extracts),
                analyzed_at=datetime.now(timezone.utc).isoformat(),
                last_error=analysis_result.get("last_error"),
                classification_meta=classification_meta,
                cleaning_meta=analysis_result.get("cleaning_meta"),
                llm_diagnostics=analysis_result.get("llm_diagnostics"),
            )

            if not extracts:
                document.parse_status = "failed"
                document.sync_status = "parse_failed"

            db.commit()
            db.refresh(document)
            return document
        except Exception as exc:
            db.rollback()
            document = db.get(DocumentMeta, document.id)
            if document is not None:
                document.parse_status = "failed"
                document.sync_status = "parse_failed"
                pipeline = DocumentAnalysisPipeline(self)
                self.knowledge_index_service.replace_document_chunks(
                    db,
                    enterprise_id=document.enterprise_id,
                    document_id=document.id,
                    document_name=clean_document_title(document.document_name) or document.document_name,
                    version=self.EXTRACT_VERSION,
                    extracts=[],
                )
                self._build_analysis_meta(
                    document,
                    analysis_status="failed",
                    analysis_mode="failed",
                    candidate_count=0,
                    extract_count=0,
                    analysis_groups=[],
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                    last_error=pipeline.exception_to_error_payload(exc),
                    classification_meta=classification_meta,
                )
                db.commit()
            raise
