from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.risk_agent_skill_registry import RiskAgentSkillRegistry
from app.ai.llm_client import LLMClient, LLMRequestError
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.financial_report_service import FinancialReportService
from app.utils.display_text import clean_document_title


logger = logging.getLogger(__name__)


@dataclass
class _SummaryResult:
    summary: str
    summary_mode: str
    cache_state: str
    cached: bool
    updated_at: str | None


@dataclass
class _SummaryCacheEntry:
    result: _SummaryResult
    expires_at: float


@dataclass
class _SummaryInflightState:
    event: threading.Event = field(default_factory=threading.Event)
    result: _SummaryResult | None = None


class FinancialAnalysisService:
    AGENT_SKILL = RiskAgentSkillRegistry.get("financial_report_risk_analysis").key
    SNAPSHOT_KEY = "financial_analysis_snapshot"
    SNAPSHOT_VERSION = "financial-analysis-snapshot:v4"
    SUPPORTED_DOCUMENT_TYPES = {"annual_report", "quarter_report", "audit_report", "internal_control_report"}
    DEFAULT_PROCEDURES = [
        "实施趋势分析并复核异常波动原因",
        "结合附注与披露复核关键财务指标口径",
        "核对经营现金流、收入与利润的匹配关系",
        "对重点科目执行穿行测试和截止测试",
    ]
    SUMMARY_CACHE_TTL_SECONDS = 30
    SUMMARY_WAIT_TIMEOUT_SECONDS = 15

    _summary_lock = threading.Lock()
    _summary_cache: dict[str, _SummaryCacheEntry] = {}
    _summary_inflight: dict[str, _SummaryInflightState] = {}

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def build_analysis(self, db: Session, enterprise_id: int) -> dict[str, Any]:
        enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        enterprise_repo = EnterpriseRepository(db)
        document_repo = DocumentRepository(db)

        document_items: list[dict[str, Any]] = []
        periods: list[str] = []
        key_metrics: list[dict[str, Any]] = []
        anomalies: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        focus_accounts: list[str] = []
        source_document_ids: list[int] = []
        source_extract_count = 0
        input_documents: list[dict[str, Any]] = []
        structured_key_metrics = self._structured_key_metrics(enterprise_repo.get_financials(enterprise_id, official_only=True))
        key_metrics.extend(structured_key_metrics)
        for metric in structured_key_metrics:
            period = metric.get("period")
            metric_name = metric.get("metric_name")
            if period and period not in periods:
                periods.append(str(period))
            if metric_name and metric_name not in focus_accounts:
                focus_accounts.append(str(metric_name))

        for document in enterprise_repo.get_documents(enterprise_id, official_only=True):
            document_type = document.classified_type or document.document_type or "general"
            if document_type not in self.SUPPORTED_DOCUMENT_TYPES:
                continue

            extracts = [
                extract
                for extract in document_repo.list_extracts(document.id)
                if extract.extract_family == "financial_statement"
                and extract.detail_level == "financial_deep_dive"
            ]
            source_document_ids.append(document.id)
            source_extract_count += len(extracts)
            input_documents.append(self._document_input_signature(document, document_type, extracts))
            if not extracts:
                continue

            metadata = document.metadata_json or {}
            analysis_meta = metadata.get("analysis_meta") or {}
            document_metrics: list[dict[str, Any]] = []
            document_anomalies: list[dict[str, Any]] = []

            for extract in extracts:
                period = extract.period or document.report_period_label
                if period and period not in periods:
                    periods.append(period)

                metric_name = extract.metric_name or extract.title
                if metric_name and metric_name not in focus_accounts:
                    focus_accounts.append(metric_name)

                metric_payload = {
                    "document_id": document.id,
                    "document_name": clean_document_title(document.document_name),
                    "metric_name": metric_name,
                    "metric_value": extract.metric_value,
                    "metric_unit": extract.metric_unit,
                    "period": period,
                    "fiscal_year": extract.fiscal_year or document.fiscal_year,
                }
                if metric_name:
                    key_metrics.append(metric_payload)
                    document_metrics.append(metric_payload)

                risk_score = self._score_financial_extract(extract)
                anomaly_payload = {
                    "document_id": document.id,
                    "document_name": clean_document_title(document.document_name),
                    "title": extract.title,
                    "summary": extract.problem_summary or extract.evidence_excerpt or extract.title,
                    "canonical_risk_key": extract.canonical_risk_key,
                    "metric_name": extract.metric_name,
                    "metric_value": extract.metric_value,
                    "metric_unit": extract.metric_unit,
                    "period": period,
                    "fiscal_year": extract.fiscal_year or document.fiscal_year,
                    "fiscal_quarter": extract.fiscal_quarter,
                    "document_report_period": document.report_period_label,
                    "announcement_date": document.announcement_date.isoformat() if document.announcement_date else None,
                    "section_title": extract.section_title,
                    "page_start": extract.page_start,
                    "page_end": extract.page_end,
                    "risk_score": risk_score,
                    "risk_level": self._score_to_level(risk_score),
                }
                anomalies.append(anomaly_payload)
                document_anomalies.append(anomaly_payload)

                evidence.append(
                    {
                        "document_id": document.id,
                        "document_name": clean_document_title(document.document_name),
                        "title": extract.title,
                        "snippet": extract.evidence_excerpt or extract.problem_summary or extract.title,
                        "period": period,
                        "section_title": extract.section_title,
                        "page_start": extract.page_start,
                        "page_end": extract.page_end,
                    }
                )

            document_items.append(
                {
                    "document_id": document.id,
                    "document_name": clean_document_title(document.document_name),
                    "classified_type": document_type,
                    "period": document.report_period_label,
                    "fiscal_year": document.fiscal_year,
                    "analysis_status": metadata.get("analysis_status"),
                    "analysis_mode": analysis_meta.get("analysis_mode"),
                    "extract_count": len(extracts),
                    "key_metrics": document_metrics,
                    "anomalies": document_anomalies,
                }
            )

        recommended_procedures = self._build_recommended_procedures(key_metrics, anomalies)
        input_hash = self._financial_input_hash(enterprise_id, input_documents, structured_key_metrics)
        persisted_payload = self._load_financial_snapshot(enterprise, input_hash)
        if persisted_payload is not None:
            return persisted_payload

        summary_result = self._build_summary(
            enterprise_id=enterprise_id,
            enterprise_name=enterprise.name,
            periods=periods,
            anomalies=anomalies,
            focus_accounts=focus_accounts,
            recommended_procedures=recommended_procedures,
        )
        payload = {
            "enterprise_id": enterprise_id,
            "agent_skill": self.AGENT_SKILL,
            "summary": summary_result.summary,
            "summary_mode": summary_result.summary_mode,
            "cached": summary_result.cached,
            "cache_state": summary_result.cache_state,
            "updated_at": summary_result.updated_at,
            "documents": document_items,
            "periods": periods,
            "key_metrics": key_metrics[:20],
            "anomalies": anomalies[:20],
            "evidence": evidence[:12],
            "focus_accounts": focus_accounts[:12],
            "recommended_procedures": recommended_procedures,
        }
        self._store_financial_snapshot(
            db,
            enterprise=enterprise,
            input_hash=input_hash,
            payload=payload,
            source_document_ids=source_document_ids,
            source_extract_count=source_extract_count,
        )
        return payload

    def _document_input_signature(self, document: Any, document_type: str, extracts: list[Any]) -> dict[str, Any]:
        return {
            "document_id": document.id,
            "classified_type": document_type,
            "parser_version": document.parser_version,
            "content_hash": document.content_hash,
            "updated_at": self._iso_value(getattr(document, "updated_at", None)),
            "extracts": [
                {
                    "id": extract.id,
                    "extract_version": extract.extract_version,
                    "is_current": extract.is_current,
                    "extract_family": extract.extract_family,
                    "detail_level": extract.detail_level,
                    "title": extract.title,
                    "problem_summary": extract.problem_summary,
                    "evidence_excerpt": extract.evidence_excerpt,
                    "metric_name": extract.metric_name,
                    "metric_value": extract.metric_value,
                    "metric_unit": extract.metric_unit,
                    "period": extract.period,
                    "canonical_risk_key": extract.canonical_risk_key,
                    "updated_at": self._iso_value(getattr(extract, "updated_at", None)),
                }
                for extract in sorted(extracts, key=lambda item: item.id)
            ],
        }

    def _structured_key_metrics(self, financials: list[Any]) -> list[dict[str, Any]]:
        if not financials:
            return []
        try:
            rows = FinancialReportService()._build_rows(financials, set())
        except Exception:
            return []
        if not rows:
            return []
        latest = sorted(rows, key=FinancialReportService()._row_sort_key, reverse=True)[0]
        metric_defs = [
            ("revenue_growth", "营业收入增长率", "pct"),
            ("gross_margin", "毛利率", "pct"),
            ("net_margin", "净利率", "pct"),
            ("revenue", "营业收入", "cny"),
            ("ar_turnover", "应收账款周转率", "ratio"),
            ("inventory_turnover", "存货周转率", "ratio"),
            ("debt_ratio", "资产负债率", "pct"),
            ("expense_ratio", "费用率", "pct"),
        ]
        metrics: list[dict[str, Any]] = []
        for field_name, metric_name, unit in metric_defs:
            value = latest.get(field_name)
            if value is None:
                continue
            metrics.append(
                {
                    "document_id": None,
                    "document_name": "AkShare结构化财报",
                    "metric_name": metric_name,
                    "metric_code": field_name,
                    "metric_value": value,
                    "metric_unit": unit,
                    "period": latest.get("report_period"),
                    "fiscal_year": latest.get("year"),
                    "source": "akshare",
                }
            )
        return metrics

    def _financial_input_hash(
        self,
        enterprise_id: int,
        documents: list[dict[str, Any]],
        structured_key_metrics: list[dict[str, Any]],
    ) -> str:
        payload = {
            "enterprise_id": enterprise_id,
            "analysis_version": self.SNAPSHOT_VERSION,
            "documents": sorted(documents, key=lambda item: item.get("document_id") or 0),
            "structured_key_metrics": sorted(
                structured_key_metrics,
                key=lambda item: (str(item.get("period") or ""), str(item.get("metric_code") or item.get("metric_name") or "")),
            ),
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _load_financial_snapshot(self, enterprise: Any, input_hash: str) -> dict[str, Any] | None:
        portrait = enterprise.portrait if isinstance(getattr(enterprise, "portrait", None), dict) else {}
        snapshot = portrait.get(self.SNAPSHOT_KEY) if isinstance(portrait, dict) else None
        if not isinstance(snapshot, dict) or snapshot.get("input_hash") != input_hash:
            return None
        return {
            "enterprise_id": enterprise.id,
            "agent_skill": self.AGENT_SKILL,
            "summary": str(snapshot.get("summary") or ""),
            "summary_mode": str(snapshot.get("summary_mode") or "fallback"),
            "cached": True,
            "cache_state": "persisted_hit",
            "updated_at": snapshot.get("generated_at"),
            "documents": list(snapshot.get("documents") or []),
            "periods": list(snapshot.get("periods") or []),
            "key_metrics": list(snapshot.get("key_metrics") or []),
            "anomalies": list(snapshot.get("anomalies") or []),
            "evidence": list(snapshot.get("evidence") or []),
            "focus_accounts": list(snapshot.get("focus_accounts") or []),
            "recommended_procedures": list(snapshot.get("recommended_procedures") or []),
        }

    def _store_financial_snapshot(
        self,
        db: Session,
        *,
        enterprise: Any,
        input_hash: str,
        payload: dict[str, Any],
        source_document_ids: list[int],
        source_extract_count: int,
    ) -> None:
        generated_at = payload.get("updated_at") or self._now_iso()
        snapshot = {
            "input_hash": input_hash,
            "generated_at": generated_at,
            "agent_skill": self.AGENT_SKILL,
            "summary": payload.get("summary"),
            "summary_mode": payload.get("summary_mode"),
            "documents": payload.get("documents") or [],
            "periods": payload.get("periods") or [],
            "key_metrics": payload.get("key_metrics") or [],
            "anomalies": payload.get("anomalies") or [],
            "evidence": payload.get("evidence") or [],
            "focus_accounts": payload.get("focus_accounts") or [],
            "recommended_procedures": payload.get("recommended_procedures") or [],
            "source_document_ids": sorted(set(source_document_ids)),
            "source_extract_count": source_extract_count,
            "analysis_version": self.SNAPSHOT_VERSION,
        }
        portrait = dict(enterprise.portrait or {})
        portrait[self.SNAPSHOT_KEY] = snapshot
        enterprise.portrait = portrait
        db.add(enterprise)
        db.commit()

    def _build_recommended_procedures(
        self,
        key_metrics: list[dict[str, Any]],
        anomalies: list[dict[str, Any]],
    ) -> list[str]:
        procedures = list(self.DEFAULT_PROCEDURES)
        metric_names = {str(item.get("metric_name") or "") for item in key_metrics}
        if "应收账款" in metric_names:
            procedures.append("关注应收账款账龄、回款测试与坏账准备计提依据")
        if "存货" in metric_names:
            procedures.append("复核存货跌价准备、库龄结构与监盘证据")
        if "经营现金流" in metric_names or "净利润" in metric_names:
            procedures.append("对经营现金流与利润背离执行专项复核")
        if any(item.get("canonical_risk_key") == "revenue_recognition" for item in anomalies):
            procedures.append("对收入确认时点与截止测试执行专项复核")

        deduped: list[str] = []
        for item in procedures:
            if item not in deduped:
                deduped.append(item)
        return deduped[:8]

    def latest_financial_anomalies(self, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not anomalies:
            return []
        latest = max(anomalies, key=self._anomaly_source_sort_key)
        latest_document_id = latest.get("document_id")
        if latest_document_id is None:
            return [latest]
        return [item for item in anomalies if item.get("document_id") == latest_document_id]

    def _score_financial_extract(self, extract: Any) -> float:
        score = 64.0
        if getattr(extract, "detail_level", None) == "financial_deep_dive":
            score += 8.0
        applied_rules = getattr(extract, "applied_rules", None) or []
        if isinstance(applied_rules, list):
            score += min(len(applied_rules) * 4.0, 12.0)
        if getattr(extract, "canonical_risk_key", None):
            score += 4.0
        if getattr(extract, "metric_value", None) is not None:
            score += 3.0
        if getattr(extract, "compare_value", None) is not None:
            score += 3.0
        if getattr(extract, "problem_summary", None) or getattr(extract, "evidence_excerpt", None):
            score += 4.0

        severity = str(getattr(extract, "severity", "") or "").strip().lower()
        if severity in {"high", "高", "高风险"}:
            score += 8.0
        elif severity in {"medium", "中", "中风险"}:
            score += 4.0

        return round(min(95.0, max(0.0, score)), 1)

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 80:
            return "HIGH"
        if score >= 60:
            return "MEDIUM"
        return "LOW"

    def _anomaly_source_sort_key(self, anomaly: dict[str, Any]) -> tuple[int, int, int, int]:
        year = self._int_value(anomaly.get("fiscal_year"))
        quarter = self._int_value(anomaly.get("fiscal_quarter"))
        period_text = " ".join(
            str(value or "")
            for value in (
                anomaly.get("period"),
                anomaly.get("document_report_period"),
                anomaly.get("document_name"),
                anomaly.get("title"),
            )
        )
        inferred_year, inferred_quarter = self._infer_report_period_rank(period_text)
        date_rank = self._date_rank(anomaly.get("announcement_date"))
        document_id = self._int_value(anomaly.get("document_id"))
        return year or inferred_year, max(quarter, inferred_quarter), date_rank, document_id

    @staticmethod
    def _infer_report_period_rank(text: str) -> tuple[int, int]:
        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else 0
        if re.search(r"年度报告|年报|全年|FY", text, flags=re.I):
            return year, 5
        if re.search(r"三季|第三季度|Q3", text, flags=re.I):
            return year, 3
        if re.search(r"半年度|半年报|上半年|中报|Q2", text, flags=re.I):
            return year, 2
        if re.search(r"一季|第一季度|Q1", text, flags=re.I):
            return year, 1
        return year, 0

    @staticmethod
    def _date_rank(value: Any) -> int:
        text = str(value or "").strip()
        if not text:
            return 0
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 8:
            return int(digits[:8])
        return int(digits) if digits.isdigit() else 0

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _build_summary(
        self,
        *,
        enterprise_id: int,
        enterprise_name: str,
        periods: list[str],
        anomalies: list[dict[str, Any]],
        focus_accounts: list[str],
        recommended_procedures: list[str],
    ) -> _SummaryResult:
        if not anomalies:
            return _SummaryResult(
                summary="当前尚未形成可展示的财报专项异常，请先完成年报或审计报告解析。",
                summary_mode="fallback",
                cache_state="fresh",
                cached=False,
                updated_at=self._now_iso(),
            )

        summary_payload = {
            "enterprise_name": enterprise_name,
            "periods": periods[:4],
            "focus_accounts": focus_accounts[:8],
            "anomalies": self._summarize_anomalies(anomalies[:6]),
            "recommended_procedures": recommended_procedures[:6],
        }
        cache_key = self._summary_cache_key(enterprise_id, summary_payload)

        cached = self._get_cached_summary(cache_key)
        if cached is not None:
            logger.info(
                "financial-analysis cache hit enterprise_id=%s cache_state=%s summary_mode=%s updated_at=%s",
                enterprise_id,
                cached.cache_state,
                cached.summary_mode,
                cached.updated_at,
            )
            return cached

        inflight, is_owner = self._acquire_summary_slot(cache_key)
        if not is_owner:
            logger.info(
                "financial-analysis in-flight reused enterprise_id=%s cache_state=in_flight_reused",
                enterprise_id,
            )
            inflight.event.wait(timeout=self.SUMMARY_WAIT_TIMEOUT_SECONDS)
            if inflight.result is not None:
                return _SummaryResult(
                    summary=inflight.result.summary,
                    summary_mode=inflight.result.summary_mode,
                    cache_state="in_flight_reused",
                    cached=False,
                    updated_at=inflight.result.updated_at,
                )
            cached_after_wait = self._get_cached_summary(cache_key)
            if cached_after_wait is not None:
                return _SummaryResult(
                    summary=cached_after_wait.summary,
                    summary_mode=cached_after_wait.summary_mode,
                    cache_state="in_flight_reused",
                    cached=False,
                    updated_at=cached_after_wait.updated_at,
                )
            return self._fallback_result(enterprise_name, periods, focus_accounts, recommended_procedures, cache_state="in_flight_reused")

        try:
            result = self._generate_summary(
                enterprise_id=enterprise_id,
                enterprise_name=enterprise_name,
                periods=periods,
                anomalies=anomalies,
                focus_accounts=focus_accounts,
                recommended_procedures=recommended_procedures,
            )
        except Exception:
            result = self._fallback_result(enterprise_name, periods, focus_accounts, recommended_procedures, cache_state="fresh")

        logger.info(
            "financial-analysis computed enterprise_id=%s cache_state=%s summary_mode=%s updated_at=%s",
            enterprise_id,
            result.cache_state,
            result.summary_mode,
            result.updated_at,
        )
        self._store_summary(cache_key, inflight, result)
        return result

    def _summarize_anomalies(self, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "period": item.get("period"),
                "metric_name": item.get("metric_name"),
            }
            for item in anomalies
        ]

    def _recover_summary_payload(self, raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        block = self._extract_json_block(raw)
        if not block:
            return None
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            return None

    def _extract_json_block(self, raw: str) -> str | None:
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

    def _sanitize_summary_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r'^[\s"\']+|[\s"\']+$', "", text)
        text = re.sub(r"^[\-\*\d\.\)\(、]+\s*", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        if text.startswith("{") or text.startswith("["):
            return None
        if len(text) > 1200:
            punctuation_cutoffs = [text.rfind(mark, 0, 1200) for mark in ("。", "；", "！", "？")]
            cutoff = max(punctuation_cutoffs)
            if cutoff <= 0:
                text = text[:1200].strip()
            else:
                text = text[: cutoff + 1].strip()
        return text or None

    def _fallback_result(
        self,
        enterprise_name: str,
        periods: list[str],
        focus_accounts: list[str],
        recommended_procedures: list[str],
        *,
        cache_state: str,
    ) -> _SummaryResult:
        top_accounts = "、".join(focus_accounts[:3]) if focus_accounts else "关键财务科目"
        top_period = periods[0] if periods else "当前期间"
        top_procedure = recommended_procedures[0] if recommended_procedures else "执行趋势复核和关键科目测试"
        return _SummaryResult(
            summary=f"{enterprise_name} 在 {top_period} 的财报异常集中在 {top_accounts}。这些信号更像是指标口径与经营质量的组合问题，建议优先 {top_procedure}。",
            summary_mode="fallback",
            cache_state=cache_state,
            cached=False,
            updated_at=self._now_iso(),
        )

    def _summary_cache_key(self, enterprise_id: int, payload: dict[str, Any]) -> str:
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"{enterprise_id}:{digest}"

    def _get_cached_summary(self, cache_key: str) -> _SummaryResult | None:
        now = time.monotonic()
        with self._summary_lock:
            cached = self._summary_cache.get(cache_key)
            if cached is None:
                return None
            if cached.expires_at <= now:
                self._summary_cache.pop(cache_key, None)
                return None
            return _SummaryResult(
                summary=cached.result.summary,
                summary_mode=cached.result.summary_mode,
                cache_state="cache_hit",
                cached=True,
                updated_at=cached.result.updated_at,
            )

    def _acquire_summary_slot(self, cache_key: str) -> tuple[_SummaryInflightState, bool]:
        with self._summary_lock:
            inflight = self._summary_inflight.get(cache_key)
            if inflight is not None:
                return inflight, False
            inflight = _SummaryInflightState()
            self._summary_inflight[cache_key] = inflight
            return inflight, True

    def _store_summary(self, cache_key: str, inflight: _SummaryInflightState, result: _SummaryResult) -> None:
        inflight.result = result
        inflight.event.set()
        with self._summary_lock:
            self._summary_cache[cache_key] = _SummaryCacheEntry(
                result=_SummaryResult(
                    summary=result.summary,
                    summary_mode=result.summary_mode,
                    cache_state="cache_hit",
                    cached=True,
                    updated_at=result.updated_at,
                ),
                expires_at=time.monotonic() + self.SUMMARY_CACHE_TTL_SECONDS,
            )
            self._summary_inflight.pop(cache_key, None)

    def _iso_value(self, value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_summary(
        self,
        *,
        enterprise_id: int,
        enterprise_name: str,
        periods: list[str],
        anomalies: list[dict[str, Any]],
        focus_accounts: list[str],
        recommended_procedures: list[str],
    ) -> _SummaryResult:
        if self.llm_client.config_error:
            return self._fallback_result(enterprise_name, periods, focus_accounts, recommended_procedures, cache_state="fresh")

        skill = RiskAgentSkillRegistry.get(self.AGENT_SKILL)
        logger.info("financial_analysis_summary text mode used enterprise_id=%s", enterprise_id)
        prompt = (
            f"agent_skill：{skill.key}\n"
            f"skill_contract：\n{skill.prompt_contract()}\n"
            f"企业：{enterprise_name}\n"
            f"期间：{', '.join(periods[:3]) or '当前期间'}\n"
            f"重点科目：{', '.join(focus_accounts[:5]) or '关键财务科目'}\n"
            f"异常摘要：{json.dumps(self._summarize_anomalies(anomalies[:4]), ensure_ascii=False)}\n"
            f"建议程序：{json.dumps(recommended_procedures[:4], ensure_ascii=False)}\n"
            "请直接输出一段中文单段摘要，不要使用 JSON、列表、代码块或额外说明。"
            "必须做聚合判断，不要逐条复制异常摘要；用 2-3 句说明主要问题集中在哪些指标、可能意味着什么、审计上最该关注什么。"
        )
        try:
            result = self.llm_client.chat_completion(
                f"{skill.role}。{skill.summary_format}",
                (
                    f"{prompt}\n"
                    "请输出完整的单段中文摘要，覆盖主要异常、重点科目和建议程序；不要省略，不要使用省略号，不要以未完成的半句结尾。"
                ),
                json_mode=False,
                request_kind="financial_analysis_summary",
                metadata={
                    "enterprise_id": enterprise_id,
                    "candidate_count": min(len(anomalies), 4),
                    "context_variant": "financial_analysis_summary",
                    "agent_skill": skill.key,
                },
                max_tokens=1024,
                max_attempts=1,
                strict_json_instruction=False,
            )
            summary = self._extract_summary_text(result)
            if summary:
                return _SummaryResult(
                    summary=summary,
                    summary_mode="llm",
                    cache_state="fresh",
                    cached=False,
                    updated_at=self._now_iso(),
                )
        except LLMRequestError as exc:
            if exc.status_code == 401:
                return _SummaryResult(
                    summary=f"DeepSeek 摘要暂不可用：{exc.message}",
                    summary_mode="fallback",
                    cache_state="fresh",
                    cached=False,
                    updated_at=self._now_iso(),
                )

        return self._fallback_result(enterprise_name, periods, focus_accounts, recommended_procedures, cache_state="fresh")

    def _extract_summary_text(self, result: Any) -> str | None:
        if isinstance(result, dict):
            summary = self._sanitize_summary_text(result.get("summary"))
            if summary:
                return summary
            items = result.get("items")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        summary = self._sanitize_summary_text(item.get("summary"))
                    elif isinstance(item, str):
                        summary = self._sanitize_summary_text(item)
                    else:
                        summary = None
                    if summary:
                        return summary
            raw = result.get("raw")
            if isinstance(raw, str) and raw.strip():
                recovered = self._recover_summary_payload(raw)
                if isinstance(recovered, dict):
                    summary = self._sanitize_summary_text(recovered.get("summary"))
                    if summary:
                        return summary
                if isinstance(recovered, list):
                    for item in recovered:
                        if isinstance(item, dict):
                            summary = self._sanitize_summary_text(item.get("summary"))
                        elif isinstance(item, str):
                            summary = self._sanitize_summary_text(item)
                        else:
                            summary = None
                        if summary:
                            return summary
                return self._sanitize_summary_text(raw)
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    summary = self._sanitize_summary_text(item.get("summary"))
                elif isinstance(item, str):
                    summary = self._sanitize_summary_text(item)
                else:
                    summary = None
                if summary:
                    return summary
        if isinstance(result, str):
            return self._sanitize_summary_text(result)
        return None

