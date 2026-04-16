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
from app.services.document_classify_service import DocumentClassifyService
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


def test_clean_document_removes_cover_noise_for_internal_control_report() -> None:
    service = DocumentService()
    text = "\n".join(
        [
            "三一重工股份有限公司",
            "2025年12月31日",
            "内部控制审计报告",
            "董事会的责任",
            "一、内部控制审计意见",
            "我们认为，公司于2025年12月31日按照企业内部控制基本规范在所有重大方面保持了有效的财务报告内部控制。",
            "二、企业对内部控制的责任",
            "管理层的责任",
            "三、整改情况",
            "针对关键流程缺陷，公司已制定整改计划并明确责任人。",
        ]
    )

    entries = service._clean_document(text, "internal_control_report")
    texts = [entry["text"] for entry in entries]

    assert "三一重工股份有限公司" not in texts
    assert "2025年12月31日" not in texts
    assert "董事会的责任" not in texts
    assert any("有效的财务报告内部控制" in item for item in texts)
    assert any("整改计划" in item for item in texts)


def test_classify_prefers_internal_control_report_over_annual_report_keywords() -> None:
    classifier = DocumentClassifyService()
    document = _document("2024年年度报告内部控制评价报告", "annual_report", "2024年度")
    text = "\n".join(
        [
            "2024年年度报告",
            "内部控制评价报告",
            "公司披露内部控制有效性结论，并说明重大缺陷整改情况。",
        ]
    )

    classified_type, source = classifier.classify(document, text)

    assert classified_type == "internal_control_report"
    assert source == "rule"


def test_clean_document_removes_responsibility_and_english_footer_for_internal_control_report() -> None:
    service = DocumentService()
    text = "\n".join(
        [
            "内部控制评价报告",
            "董事会的责任",
            "中国 北京 2026年3月30日",
            "A member firm of Ernst & Young Global Limited",
            "一、内部控制审计意见",
            "我们认为，公司于2025年12月31日在所有重大方面保持了有效的财务报告内部控制。",
            "二、整改情况",
            "针对重大缺陷，公司已制定整改计划并明确责任人。",
        ]
    )

    entries = service._clean_document(text, "internal_control_report")
    texts = [entry["text"] for entry in entries]

    assert "董事会的责任" not in texts
    assert "中国 北京 2026年3月30日" not in texts
    assert "A member firm of Ernst & Young Global Limited" not in texts
    assert any("有效的财务报告内部控制" in item for item in texts)
    assert any("整改计划" in item for item in texts)


def test_clean_document_removes_salutation_and_firm_footer_for_audit_report() -> None:
    service = DocumentService()
    text = "\n".join(
        [
            "致全体股东：",
            "安永华明会计师事务所（特殊普通合伙）",
            "A member firm of Ernst & Young Global Limited",
            "一、审计意见",
            "我们对财务报表出具保留意见。",
            "二、关键审计事项",
            "收入确认是本次审计的关键审计事项。",
        ]
    )

    entries = service._clean_document(text, "audit_report")
    texts = [entry["text"] for entry in entries]

    assert "致全体股东：" not in texts
    assert "安永华明会计师事务所（特殊普通合伙）" not in texts
    assert "A member firm of Ernst & Young Global Limited" not in texts
    assert any("保留意见" in item for item in texts)
    assert any("关键审计事项" in item for item in texts)


def test_build_structured_extracts_trims_candidates_and_uses_clean_fallback() -> None:
    service = DocumentService()
    document = _document("三一重工股份有限公司2025年度内部控制审计报告", "internal_control_report", "2025年度")
    entries = [
        {
            "text": "三一重工股份有限公司",
            "section_title": None,
            "paragraph_hash": "noise-company",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "text": "2025年12月31日",
            "section_title": None,
            "paragraph_hash": "noise-date",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "text": "内部控制审计报告",
            "section_title": None,
            "paragraph_hash": "noise-title",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "text": "我们认为，公司于2025年12月31日按照企业内部控制基本规范在所有重大方面保持了有效的财务报告内部控制。",
            "section_title": "内部控制审计意见",
            "paragraph_hash": "good-opinion",
            "page_start": 2,
            "page_end": 2,
        },
        {
            "text": "针对关键流程缺陷，公司已制定整改计划并明确责任人。",
            "section_title": "整改情况",
            "paragraph_hash": "good-remediation",
            "page_start": 3,
            "page_end": 3,
        },
    ]

    service._llm_extract = lambda document, candidates, classified_type: []  # type: ignore[method-assign]
    extracts = service._build_structured_extracts(document, entries, "internal_control_report")

    assert 1 <= len(extracts) <= service.FALLBACK_LIMITS["internal_control_report"]
    assert all(item["summary"] not in {"三一重工股份有限公司。", "2025年12月31日。"} for item in extracts)
    assert all(item["evidence_excerpt"] not in {"三一重工股份有限公司", "2025年12月31日"} for item in extracts)
    assert any(item["section_title"] in {"内部控制审计意见", "整改情况"} for item in extracts)


def test_build_structured_extracts_ignores_responsibility_and_footer_noise() -> None:
    service = DocumentService()
    document = _document("2025年度内部控制评价报告", "internal_control_report", "2025年度")
    entries = [
        {
            "text": "董事会的责任",
            "section_title": "内部控制报告",
            "paragraph_hash": "noise-responsibility",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "text": "A member firm of Ernst & Young Global Limited",
            "section_title": "内部控制报告",
            "paragraph_hash": "noise-footer",
            "page_start": 1,
            "page_end": 1,
        },
        {
            "text": "我们认为，公司于2025年12月31日在所有重大方面保持了有效的财务报告内部控制。",
            "section_title": "内部控制审计意见",
            "paragraph_hash": "good-opinion",
            "page_start": 2,
            "page_end": 2,
        },
        {
            "text": "针对重大缺陷，公司已制定整改计划并明确责任人。",
            "section_title": "整改情况",
            "paragraph_hash": "good-remediation",
            "page_start": 3,
            "page_end": 3,
        },
    ]

    service._llm_extract = lambda document, candidates, classified_type: []  # type: ignore[method-assign]
    extracts = service._build_structured_extracts(document, entries, "internal_control_report")

    assert extracts
    assert all("董事会的责任" not in item["summary"] for item in extracts)
    assert all("Ernst & Young" not in item["summary"] for item in extracts)
    assert any(item["section_title"] in {"内部控制审计意见", "整改情况"} for item in extracts)


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
def test_normalize_entry_text_strips_highlight_html_and_repeated_titles() -> None:
    service = DocumentService()

    normalized = service._normalize_entry_text("<em>2025年</em>半<em>年度报告</em><em>2025年</em>半<em>年度报告</em><em>摘要</em>")

    assert "<em>" not in normalized
    assert normalized.count("2025年") == 1


def test_llm_extract_accepts_recovered_raw_array() -> None:
    service = DocumentService()

    items = service._extract_llm_items(
        {
            "parsed_ok": False,
            "payload_mode": "raw_text",
            "raw": '说明如下：[{"summary":"异常","event_type":"executive_change","extract_family":"financial_statement","evidence_excerpt":"董事变更"}]谢谢',
        }
    )

    assert len(items) == 1
    assert items[0]["event_type"] == "executive_change"


def test_trim_evidence_safe_accepts_custom_limit() -> None:
    service = DocumentService()

    trimmed = service._trim_evidence_safe("abcdefghijklmnopqrstuvwxyz", limit=10)

    assert trimmed == "abcdefghij…"


def test_normalize_extract_payload_reconciles_event_family_mismatch() -> None:
    service = DocumentService()
    document = _document("2024年年度报告", "annual_report", "2024年度")

    normalized = service._normalize_extract_payload(
        document,
        {
            "title": "高管变动",
            "summary": "公司披露董事变更事项。",
            "event_type": "executive_change",
            "extract_family": "financial_statement",
            "evidence_excerpt": "董事会成员发生调整。",
        },
        1,
    )

    assert normalized["extract_family"] == "announcement_event"


def test_llm_extract_partially_recovers_complete_items_from_truncated_array() -> None:
    service = DocumentService()

    items = service._extract_llm_items(
        {
            "parsed_ok": False,
            "payload_mode": "raw_text",
            "raw_prefix_kind": "array_prefix",
            "truncated_json_prefix": True,
            "raw": '[{"summary":"异常一","event_type":"executive_change","evidence_excerpt":"董事变更"},'
            '{"summary":"异常二","event_type":"major_contract","evidence_excerpt":"重大合同"},'
            '{"summary":"异常三"',
        },
        document_id=8,
    )

    assert len(items) == 2
    assert items[0]["event_type"] == "executive_change"
    assert items[1]["event_type"] == "major_contract"


def test_llm_extract_accepts_llm_client_partial_list_payload() -> None:
    service = DocumentService()

    items = service._extract_llm_items(
        {
            "parsed_ok": True,
            "payload_mode": "partial_list",
            "raw_prefix_kind": "array_prefix",
            "truncated_json_prefix": True,
            "items": [
                {
                    "summary": "寮傚父",
                    "event_type": "executive_change",
                    "extract_family": "financial_statement",
                    "evidence_excerpt": "钁ｄ簨鍙樻洿",
                }
            ],
        },
        document_id=8,
    )

    assert len(items) == 1
    assert items[0]["event_type"] == "executive_change"


def test_llm_extract_records_truncated_json_fallback_when_nothing_recoverable() -> None:
    service = DocumentService()

    items = service._extract_llm_items(
        {
            "parsed_ok": False,
            "payload_mode": "raw_text",
            "raw_prefix_kind": "array_prefix",
            "truncated_json_prefix": True,
            "raw": '[{"summary":"只有开头"',
        },
        document_id=8,
    )

    error_payload = service._build_llm_extract_fallback_error()

    assert items == []
    assert error_payload is not None
    assert error_payload["error_type"] == "truncated_json_fallback"
