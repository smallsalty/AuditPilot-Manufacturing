from __future__ import annotations

import sys
import types
from datetime import date


if "anthropic" not in sys.modules:
    anthropic = types.ModuleType("anthropic")

    class _DummyError(Exception):
        pass

    class _DummyAnthropic:
        def __init__(self, *args, **kwargs) -> None:
            pass

    anthropic.APIConnectionError = _DummyError
    anthropic.APIResponseValidationError = _DummyError
    anthropic.APIStatusError = _DummyError
    anthropic.APITimeoutError = _DummyError
    anthropic.Anthropic = _DummyAnthropic
    sys.modules["anthropic"] = anthropic


from app.models import DocumentMeta
from app.services.document_service import DocumentService


def _document(document_name: str, document_type: str, report_period_label: str | None = None) -> DocumentMeta:
    return DocumentMeta(
        id=9,
        enterprise_id=1,
        document_name=document_name,
        document_type=document_type,
        report_period_label=report_period_label,
        fiscal_year=2024,
        announcement_date=date(2025, 3, 12),
        source="cninfo",
        parse_status="parsed",
    )


def test_extracts_share_repurchase_parameters_and_one_sentence_summary() -> None:
    service = DocumentService()
    document = _document("股份回购公告", "announcement_event")
    entry = {
        "text": "公司拟使用自有资金回购股份，回购金额不超过20000万元，回购价格不超过18.5元/股，回购方案披露日期为2025年3月12日。",
        "section_title": "回购方案",
        "paragraph_hash": "hash-repurchase",
        "page_start": 3,
        "page_end": 3,
    }

    result = service._build_candidate(document, entry, "announcement_event", 1)

    assert result is not None
    assert result["event_type"] == "share_repurchase"
    assert result["extract_family"] == "announcement_event"
    assert isinstance(result["parameters"], dict)
    assert result["parameters"]["event_date"] == "2025-3-12" or result["parameters"]["event_date"] == "2025-03-12"
    assert result["parameters"]["repurchase_amount_upper"] == result["amount"]
    assert result["summary"].endswith("。")
    assert result["summary"] != entry["text"]


def test_extracts_audit_opinion_issue_with_opinion_parameters() -> None:
    service = DocumentService()
    document = _document("2024年度审计报告", "audit_report", "2024年度")
    entry = {
        "text": "我们对公司2024年度财务报表出具保留意见，并提示财务报告内部控制存在重大缺陷。",
        "section_title": "审计意见",
        "paragraph_hash": "hash-opinion",
        "page_start": 5,
        "page_end": 5,
    }

    result = service._build_candidate(document, entry, "audit_report", 1)

    assert result is not None
    assert result["event_type"] == "audit_opinion_issue"
    assert result["extract_family"] == "opinion_conclusion"
    assert result["parameters"]["opinion_type"] == "保留意见"
    assert result["parameters"]["affected_scope"] == "financial_reporting_internal_control"
    assert result["summary"].endswith("。")
    assert result["summary"] != entry["text"]


def test_extracts_financial_anomaly_for_annual_report() -> None:
    service = DocumentService()
    document = _document("2024年年度报告", "annual_report", "2024年度")
    entry = {
        "text": "应收账款为123456万元，同比增长明显，经营现金流下降，需关注收入质量。",
        "section_title": "管理层讨论与分析",
        "paragraph_hash": "hash-financial",
        "page_start": 18,
        "page_end": 18,
    }

    result = service._build_candidate(document, entry, "annual_report", 1)

    assert result is not None
    assert result["event_type"] == "financial_anomaly"
    assert result["extract_family"] == "financial_statement"
    assert result["parameters"]["metric_name"] == "应收账款"
    assert result["parameters"]["period"] == "2024年度"
    assert result["summary"].endswith("。")
    assert result["summary"] != entry["text"]


def test_normalize_extract_payload_preserves_flat_parameters() -> None:
    service = DocumentService()
    document = _document("问询函回复公告", "announcement_event")

    normalized = service._normalize_extract_payload(
        document,
        {
            "title": "监管问询",
            "summary": "公司披露监管问询事项，需关注整改进展与信息披露影响。",
            "parameters": {"issuing_authority": "证券交易所", "severity": "high"},
            "event_type": "penalty_or_inquiry",
            "extract_family": "announcement_event",
            "evidence_excerpt": "公司收到证券交易所监管问询函。",
        },
        1,
    )

    assert normalized["summary"] == "公司披露监管问询事项，需关注整改进展与信息披露影响。"
    assert normalized["problem_summary"] == normalized["summary"]
    assert normalized["parameters"] == {"issuing_authority": "证券交易所", "severity": "high"}
