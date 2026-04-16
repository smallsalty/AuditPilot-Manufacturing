import threading
from types import SimpleNamespace

from app.ai.llm_client import LLMRequestError
from app.services.document_service import DocumentService
from app.services.financial_analysis_service import FinancialAnalysisService


class _DummyLLMClient:
    config_error = "disabled"
    provider = "minimax"
    model = "MiniMax-M2.5"


def _reset_summary_state() -> None:
    FinancialAnalysisService._summary_cache.clear()
    FinancialAnalysisService._summary_inflight.clear()


def _mock_financial_repositories(monkeypatch, enterprise_name: str = "测试企业") -> None:
    enterprise = SimpleNamespace(id=1, name=enterprise_name)
    supported_doc = SimpleNamespace(
        id=11,
        enterprise_id=1,
        document_name="2024年年度报告",
        document_type="annual_report",
        classified_type="annual_report",
        report_period_label="2024年度",
        fiscal_year=2024,
        metadata_json={"analysis_status": "succeeded", "analysis_meta": {"analysis_mode": "llm_primary"}},
    )
    extract = SimpleNamespace(
        extract_family="financial_statement",
        detail_level="financial_deep_dive",
        metric_name="应收账款",
        metric_value=123.0,
        metric_unit="万元",
        title="应收账款异常",
        problem_summary="应收账款增长明显，需要复核回款。",
        evidence_excerpt="应收账款增长明显，需要复核回款。",
        canonical_risk_key="receivable_recoverability",
        period="2024年度",
        section_title="管理层讨论与分析",
        page_start=18,
        page_end=18,
        fiscal_year=2024,
    )
    monkeypatch.setattr("app.services.financial_analysis_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr(
        "app.services.financial_analysis_service.EnterpriseRepository.get_documents",
        lambda self, enterprise_id, official_only=True: [supported_doc],
    )
    monkeypatch.setattr(
        "app.services.financial_analysis_service.DocumentRepository.list_extracts",
        lambda self, document_id: [extract],
    )


def test_financial_analysis_service_filters_by_document_type_and_extract_flags(monkeypatch) -> None:
    _reset_summary_state()
    service = FinancialAnalysisService(llm_client=_DummyLLMClient())

    enterprise = SimpleNamespace(id=1, name="测试企业")
    supported_doc = SimpleNamespace(
        id=11,
        enterprise_id=1,
        document_name="2024年年度报告",
        document_type="annual_report",
        classified_type="annual_report",
        report_period_label="2024年度",
        fiscal_year=2024,
        metadata_json={"analysis_status": "succeeded", "analysis_meta": {"analysis_mode": "llm_primary"}},
    )
    unsupported_doc = SimpleNamespace(
        id=12,
        enterprise_id=1,
        document_name="回购公告",
        document_type="announcement_event",
        classified_type="announcement_event",
        report_period_label=None,
        fiscal_year=None,
        metadata_json={},
    )
    good_extract = SimpleNamespace(
        extract_family="financial_statement",
        detail_level="financial_deep_dive",
        metric_name="应收账款",
        metric_value=123.0,
        metric_unit="万元",
        title="应收账款异常",
        problem_summary="应收账款增长明显，需要复核回款。",
        evidence_excerpt="应收账款增长明显，需要复核回款。",
        canonical_risk_key="receivable_recoverability",
        period="2024年度",
        section_title="管理层讨论与分析",
        page_start=18,
        page_end=18,
        fiscal_year=2024,
    )
    bad_extract = SimpleNamespace(
        extract_family="financial_statement",
        detail_level="general",
        metric_name="收入",
        metric_value=456.0,
        metric_unit="万元",
        title="不应入选",
        problem_summary="不应入选",
        evidence_excerpt="不应入选",
        canonical_risk_key="revenue_recognition",
        period="2024年度",
        section_title=None,
        page_start=None,
        page_end=None,
        fiscal_year=2024,
    )

    monkeypatch.setattr("app.services.financial_analysis_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr(
        "app.services.financial_analysis_service.EnterpriseRepository.get_documents",
        lambda self, enterprise_id, official_only=True: [supported_doc, unsupported_doc],
    )
    monkeypatch.setattr(
        "app.services.financial_analysis_service.DocumentRepository.list_extracts",
        lambda self, document_id: [good_extract, bad_extract] if document_id == 11 else [good_extract],
    )

    result = service.build_analysis(db=None, enterprise_id=1)

    assert len(result["documents"]) == 1
    assert result["documents"][0]["document_id"] == 11
    assert len(result["anomalies"]) == 1
    assert result["anomalies"][0]["title"] == "应收账款异常"
    assert result["focus_accounts"] == ["应收账款"]
    assert result["summary_mode"] == "fallback"
    assert result["cache_state"] == "fresh"
    assert result["cached"] is False


def test_document_service_analysis_meta_overwrites_old_error_state() -> None:
    service = DocumentService(llm_client=_DummyLLMClient())
    document = SimpleNamespace(
        metadata_json={
            "analysis_status": "failed",
            "analysis_meta": {"analysis_mode": "rule_only", "analysis_version": "old"},
            "last_error": {"message": "old error", "last_error_at": "old"},
        }
    )

    service._build_analysis_meta(
        document,
        analysis_status="succeeded",
        analysis_mode="llm_primary",
        candidate_count=8,
        extract_count=3,
        analysis_groups=["financial_analysis"],
        analyzed_at="2026-04-15T12:00:00+00:00",
        last_error=None,
    )

    assert document.metadata_json["analysis_status"] == "succeeded"
    assert document.metadata_json["analysis_meta"]["analysis_mode"] == "llm_primary"
    assert document.metadata_json["analysis_meta"]["analysis_version"] == service.EXTRACT_VERSION
    assert document.metadata_json["last_error"] is None


def test_document_service_partial_fallback_with_extracts_clears_last_error() -> None:
    service = DocumentService(llm_client=_DummyLLMClient())
    document = SimpleNamespace(
        metadata_json={
            "analysis_status": "failed",
            "analysis_meta": {"analysis_mode": "rule_only", "analysis_version": "old"},
            "last_error": {"message": "old error", "last_error_at": "old"},
        }
    )

    service._build_analysis_meta(
        document,
        analysis_status="partial_fallback",
        analysis_mode="hybrid_fallback",
        candidate_count=4,
        extract_count=2,
        analysis_groups=["financial_analysis"],
        analyzed_at="2026-04-16T08:00:00+00:00",
        last_error={"message": "模型未返回有效的结构化抽取结果。", "last_error_at": "new"},
    )

    assert document.metadata_json["analysis_status"] == "partial_fallback"
    assert document.metadata_json["analysis_meta"]["extract_count"] == 2
    assert document.metadata_json["last_error"] is None


def test_document_service_derives_fixed_analysis_groups() -> None:
    service = DocumentService(llm_client=_DummyLLMClient())
    document = SimpleNamespace(classified_type="annual_report", document_type="annual_report")
    extracts = [
        {"extract_family": "financial_statement", "detail_level": "financial_deep_dive", "event_type": None, "opinion_type": None},
        {"extract_family": "announcement_event", "detail_level": "general", "event_type": "executive_change", "canonical_risk_key": "governance_instability"},
    ]

    groups = service._derive_analysis_groups(document, extracts)

    assert groups == ["financial_analysis", "announcement_events", "governance"]
    assert all(group in DocumentService.ANALYSIS_GROUPS for group in groups)


def test_financial_analysis_service_falls_back_and_caches_retryable_summary(monkeypatch, caplog) -> None:
    _reset_summary_state()
    caplog.set_level("INFO")

    class RetryableLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def __init__(self) -> None:
            self.calls = 0

        def chat_completion(self, *args, **kwargs):
            self.calls += 1
            raise LLMRequestError(
                "模型服务暂时不可用：HTTP 529。",
                status_code=529,
                error_type="upstream_unavailable",
                retryable=True,
            )

    llm_client = RetryableLLMClient()
    service = FinancialAnalysisService(llm_client=llm_client)
    _mock_financial_repositories(monkeypatch)

    first = service.build_analysis(db=None, enterprise_id=1)
    second = service.build_analysis(db=None, enterprise_id=1)

    assert first["documents"]
    assert first["anomalies"]
    assert "测试企业" in first["summary"]
    assert "建议优先" in first["summary"]
    assert first["summary_mode"] == "fallback"
    assert first["cache_state"] == "fresh"
    assert first["cached"] is False
    assert second["summary"] == first["summary"]
    assert second["summary_mode"] == "fallback"
    assert second["cache_state"] == "cache_hit"
    assert second["cached"] is True
    assert second["updated_at"] == first["updated_at"]
    assert llm_client.calls == 1
    assert "financial-analysis computed" in caplog.text
    assert "financial-analysis cache hit" in caplog.text


def test_financial_analysis_service_surfaces_auth_summary_without_breaking_payload(monkeypatch) -> None:
    _reset_summary_state()

    class AuthLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def chat_completion(self, *args, **kwargs):
            raise LLMRequestError(
                "模型服务返回错误：HTTP 401，请检查 MiniMax 模型名、鉴权和 Anthropic 兼容接口配置。",
                status_code=401,
                error_type="auth_error",
                retryable=False,
            )

    service = FinancialAnalysisService(llm_client=AuthLLMClient())
    _mock_financial_repositories(monkeypatch, enterprise_name="认证测试企业")

    result = service.build_analysis(db=None, enterprise_id=1)

    assert result["documents"]
    assert result["summary"].startswith("MiniMax 摘要暂不可用：")
    assert result["summary_mode"] == "fallback"
    assert result["cache_state"] == "fresh"
    assert result["cached"] is False


def test_financial_analysis_service_marks_inflight_reused(monkeypatch, caplog) -> None:
    _reset_summary_state()
    caplog.set_level("INFO")

    class WaitingLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def __init__(self) -> None:
            self.calls = 0
            self.started = threading.Event()
            self.release = threading.Event()

        def chat_completion(self, *args, **kwargs):
            self.calls += 1
            self.started.set()
            self.release.wait(timeout=5)
            return {"summary": "LLM 摘要"}

    llm_client = WaitingLLMClient()
    service = FinancialAnalysisService(llm_client=llm_client)
    _mock_financial_repositories(monkeypatch)

    results: list[dict] = []

    def run_build() -> None:
        results.append(service.build_analysis(db=None, enterprise_id=1))

    first_thread = threading.Thread(target=run_build)
    second_thread = threading.Thread(target=run_build)

    first_thread.start()
    llm_client.started.wait(timeout=5)
    second_thread.start()
    llm_client.release.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert len(results) == 2
    assert {item["cache_state"] for item in results} == {"fresh", "in_flight_reused"}
    assert all(item["summary_mode"] == "llm" for item in results)
    assert all(item["cached"] is False for item in results)
    assert llm_client.calls == 1
    assert "financial-analysis in-flight reused" in caplog.text


def test_financial_analysis_service_accepts_list_style_summary_payload(monkeypatch) -> None:
    _reset_summary_state()

    class ListLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def chat_completion(self, *args, **kwargs):
            return {"items": [{"summary": "财报摘要"}], "parsed_ok": True, "payload_mode": "list"}

    service = FinancialAnalysisService(llm_client=ListLLMClient())
    _mock_financial_repositories(monkeypatch)

    result = service.build_analysis(db=None, enterprise_id=1)

    assert result["summary"] == "财报摘要"
    assert result["summary_mode"] == "llm"


def test_financial_analysis_service_uses_template_when_raw_text_is_too_long(monkeypatch) -> None:
    _reset_summary_state()

    class RawLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def chat_completion(self, *args, **kwargs):
            return {"parsed_ok": False, "payload_mode": "raw_text", "raw": "{" + ("x" * 260)}

    service = FinancialAnalysisService(llm_client=RawLLMClient())
    _mock_financial_repositories(monkeypatch)

    result = service.build_analysis(db=None, enterprise_id=1)

    assert result["summary_mode"] == "fallback"
    assert result["summary"]


def test_financial_analysis_service_uses_text_mode_for_summary(monkeypatch, caplog) -> None:
    _reset_summary_state()
    caplog.set_level("INFO")

    class TextLLMClient:
        config_error = None
        provider = "minimax"
        model = "MiniMax-M2.7"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def chat_completion(self, *args, **kwargs):
            self.calls.append(kwargs)
            return "这是可直接展示的财报专项摘要。"

    llm_client = TextLLMClient()
    service = FinancialAnalysisService(llm_client=llm_client)
    _mock_financial_repositories(monkeypatch)

    result = service.build_analysis(db=None, enterprise_id=1)

    assert result["summary"] == "这是可直接展示的财报专项摘要。"
    assert result["summary_mode"] == "llm"
    assert llm_client.calls
    assert llm_client.calls[0]["json_mode"] is False
    assert llm_client.calls[0]["max_tokens"] == 220
    assert llm_client.calls[0]["max_attempts"] == 1
    assert llm_client.calls[0]["strict_json_instruction"] is False
    assert "financial_analysis_summary text mode used" in caplog.text
