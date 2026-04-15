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

from app.ai.llm_client import LLMClient, LLMRequestError
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository
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
    SUPPORTED_DOCUMENT_TYPES = {"annual_report", "annual_summary", "audit_report", "internal_control_report"}
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
                    "section_title": extract.section_title,
                    "page_start": extract.page_start,
                    "page_end": extract.page_end,
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
        summary_result = self._build_summary(
            enterprise_id=enterprise_id,
            enterprise_name=enterprise.name,
            periods=periods,
            anomalies=anomalies,
            focus_accounts=focus_accounts,
            recommended_procedures=recommended_procedures,
        )
        return {
            "enterprise_id": enterprise_id,
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

        prompt = (
            f"企业：{enterprise_name}\n"
            f"期间：{', '.join(periods[:4]) or '当前期间'}\n"
            f"重点科目：{', '.join(focus_accounts[:8]) or '关键财务科目'}\n"
            f"异常摘要：{json.dumps(self._summarize_anomalies(anomalies[:6]), ensure_ascii=False)}\n"
            f"建议程序：{json.dumps(recommended_procedures[:6], ensure_ascii=False)}\n"
            "请输出一个简短 JSON 对象，至少包含 summary 字段。"
        )
        try:
            result = self.llm_client.chat_completion(
                "你是一名财报审阅助手。请用中文生成简洁、可直接展示的财报专项摘要。",
                prompt,
                json_mode=True,
                request_kind="financial_analysis_summary",
                metadata={
                    "enterprise_id": enterprise_id,
                    "candidate_count": len(anomalies),
                    "context_variant": "financial_analysis_summary",
                },
                max_tokens=512,
                max_attempts=2,
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
                    summary=f"MiniMax 摘要暂不可用：{exc.message}",
                    summary_mode="fallback",
                    cache_state="fresh",
                    cached=False,
                    updated_at=self._now_iso(),
                )

        return self._fallback_result(enterprise_name, periods, focus_accounts, recommended_procedures, cache_state="fresh")

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
                            if summary:
                                return summary
                return self._sanitize_summary_text(raw)
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    summary = self._sanitize_summary_text(item.get("summary"))
                    if summary:
                        return summary
        if isinstance(result, str):
            return self._sanitize_summary_text(result)
        return None

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
        if len(text) > 220:
            punctuation_cutoffs = [text.rfind(mark, 0, 220) for mark in ("。", "；", "！", "？")]
            cutoff = max(punctuation_cutoffs)
            if cutoff <= 0:
                return None
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
            summary=f"{enterprise_name} 在 {top_period} 的财报专项分析中，重点异常主要集中在 {top_accounts}，建议优先 {top_procedure}。",
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

        logger.info("financial_analysis_summary text mode used enterprise_id=%s", enterprise_id)
        prompt = (
            f"企业：{enterprise_name}\n"
            f"期间：{', '.join(periods[:3]) or '当前期间'}\n"
            f"重点科目：{', '.join(focus_accounts[:5]) or '关键财务科目'}\n"
            f"异常摘要：{json.dumps(self._summarize_anomalies(anomalies[:4]), ensure_ascii=False)}\n"
            f"建议程序：{json.dumps(recommended_procedures[:4], ensure_ascii=False)}\n"
            "请直接输出一段中文单段摘要，不要使用 JSON、列表、代码块或额外说明。"
        )
        try:
            result = self.llm_client.chat_completion(
                "你是一名财报审阅助手。请用中文生成简洁、可直接展示的财报专项摘要。",
                prompt,
                json_mode=False,
                request_kind="financial_analysis_summary",
                metadata={
                    "enterprise_id": enterprise_id,
                    "candidate_count": min(len(anomalies), 4),
                    "context_variant": "financial_analysis_summary",
                },
                max_tokens=220,
                max_attempts=2,
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
                    summary=f"MiniMax 摘要暂不可用：{exc.message}",
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
