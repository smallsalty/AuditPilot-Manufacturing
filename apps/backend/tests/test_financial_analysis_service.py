from types import SimpleNamespace

from app.services.document_service import DocumentService
from app.services.financial_analysis_service import FinancialAnalysisService


class _DummyLLMClient:
    config_error = "disabled"
    provider = "minimax"
    model = "MiniMax-M2.5"


def test_financial_analysis_service_filters_by_document_type_and_extract_flags(monkeypatch) -> None:
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
