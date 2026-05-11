from __future__ import annotations

from app.ai.llm_client import LLMRequestError
from app.models import DocumentMeta
from app.services.document_analysis_pipeline import DocumentAnalysisPipeline


class DummyLLMClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.config_error = None
        self.model = "deepseek-v4-flash"

    def chat_completion(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.response


class DummyService:
    LLM_EXTRACT_CANDIDATE_LIMIT = 5
    FINANCIAL_DOCUMENT_TYPES = {"annual_report", "annual_summary", "audit_report", "internal_control_report"}

    def __init__(self, llm_client: DummyLLMClient) -> None:
        self.llm_client = llm_client

    def _build_candidate(self, document, entry, classified_type, index):
        return {
            "title": f"candidate-{index}",
            "section_title": entry.get("section_title"),
            "event_type": "financial_anomaly",
            "canonical_risk_key": "cashflow_quality",
            "metric_name": "营业收入",
            "summary": "收入变化需要关注",
            "evidence_excerpt": entry.get("text") or "营业收入同比增长12%",
            "evidence_span_id": f"{document.id}-{index}",
        }

    def _trim_candidates(self, candidates, classified_type):
        return list(candidates)

    def _fallback_extracts(self, document, trimmed_candidates, classified_type):
        if not trimmed_candidates:
            return []
        return [
            {
                "title": "规则回退",
                "summary": "使用规则抽取回退",
                "evidence_excerpt": trimmed_candidates[0].get("evidence_excerpt") or "",
                "extract_type": "document_issue",
                "risk_points": ["收入波动"],
                "parameters": {},
            }
        ]

    def _normalize_extract_payload(self, document, item, index):
        payload = dict(item)
        payload.setdefault("extract_type", "document_issue")
        payload.setdefault("parameters", {})
        return payload

    def _is_low_quality_extract(self, payload):
        return False

    def _trim_evidence_safe(self, value, limit=200):
        text = str(value or "").strip()
        return text[:limit]


def make_document() -> DocumentMeta:
    return DocumentMeta(
        id=1,
        enterprise_id=100,
        document_name="2025年报",
        document_type="annual_report",
        report_period_label="2025FY",
    )


def test_run_stage_returns_llm_primary_on_valid_response():
    service = DummyService(
        DummyLLMClient(
            response={
                "items": [
                    {
                        "title": "收入增长放缓",
                        "summary": "收入增速放缓，需要继续核查。",
                        "evidence_excerpt": "营业收入同比增长12%。",
                        "extract_type": "document_issue",
                        "risk_points": ["收入波动"],
                    }
                ],
                "parsed_ok": True,
                "payload_mode": "dict",
                "retry_attempts": 1,
            }
        )
    )
    pipeline = DocumentAnalysisPipeline(service)

    result = pipeline.run_stage(
        document=make_document(),
        entries=[{"text": "营业收入同比增长12%。", "section_title": "财务报表附注"}],
        classified_type="annual_report",
        prompt_type="annual_report",
        analysis_stage="core",
    )

    assert result["analysis_status"] == "succeeded"
    assert result["analysis_mode"] == "llm_primary"
    assert result["last_error"] is None
    assert len(result["extracts"]) == 1


def test_run_stage_returns_partial_fallback_on_llm_request_error():
    service = DummyService(
        DummyLLMClient(
            error=LLMRequestError(
                "transport failed",
                error_type="transport_error",
                provider_response_text="socket timeout",
                retryable=True,
            )
        )
    )
    pipeline = DocumentAnalysisPipeline(service)

    result = pipeline.run_stage(
        document=make_document(),
        entries=[{"text": "经营现金流同比下滑。", "section_title": "财务报表附注"}],
        classified_type="annual_report",
        prompt_type="annual_report",
        analysis_stage="core",
    )

    assert result["analysis_status"] == "partial_fallback"
    assert result["analysis_mode"] == "hybrid_fallback"
    assert result["last_error"]["error_type"] == "transport_error"
    assert result["llm_diagnostics"]["payload_mode"] == "transport_error"
    assert len(result["extracts"]) == 1
