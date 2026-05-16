from __future__ import annotations

from app.ai.evidence_summary_service import EvidenceSummaryService
from app.models import DocumentMeta
from app.services.document_service import DocumentService


class DummyLLMClient:
    config_error = None
    model = "dummy"

    def __init__(self, response: str = "亿元") -> None:
        self.response = response

    def chat_completion(self, *_args, **_kwargs):
        return self.response


def test_evidence_summary_prefers_sentence_with_key_numbers():
    service = EvidenceSummaryService(DummyLLMClient())
    text = (
        "董事会审议通过相关议案。"
        "公司披露40-80亿元股份回购计划，累计已回购43.86亿元，需关注资金压力与回购执行风险。"
        "其他事项未发生重大变化。"
    )

    result = service.summarize_evidence(
        title="大额股份回购计划",
        text=text,
        context="公司披露股份回购计划",
        keywords=["股份回购", "40-80亿元", "43.86亿元"],
    )

    assert "股份回购" in result
    assert "40-80亿元" in result
    assert "43.86亿元" in result
    assert result != "亿元"


def test_evidence_summary_shortens_long_sentence_preserving_keywords():
    service = EvidenceSummaryService(DummyLLMClient())
    text = (
        "公司在报告期内围绕资金安排、董事会授权、实施窗口、市场价格、库存股用途、"
        "交易系统、合规审查、信息披露节奏、资金拨付计划和后续注销安排进行了较长说明，"
        "公司披露40-80亿元股份回购计划，累计已回购43.86亿元，需关注资金压力与回购执行风险。"
    )

    result = service.summarize_evidence(
        title="大额股份回购计划",
        text=text,
        context="股份回购计划",
        keywords=["股份回购", "40-80亿元", "43.86亿元"],
    )

    assert len(result) <= service.MAX_EVIDENCE_SUMMARY_CHARS
    assert "股份回购" in result
    assert "40-80亿元" in result
    assert "43.86亿元" in result


def test_low_information_excerpt_falls_back_to_context_sentence():
    service = EvidenceSummaryService(DummyLLMClient("亿元"))

    result = service.summarize_evidence(
        title="大额股份回购计划",
        text="亿元",
        context="公司披露40-80亿元股份回购计划，累计已回购43.86亿元，需关注资金压力与回购执行风险。",
        keywords=["股份回购", "40-80亿元", "43.86亿元"],
    )

    assert result != "亿元"
    assert "股份回购" in result
    assert "40-80亿元" in result
    assert "43.86亿元" in result


def test_document_extract_normalization_rejects_bad_evidence_summary():
    service = DocumentService(llm_client=DummyLLMClient("亿元"))
    document = DocumentMeta(
        id=13,
        enterprise_id=6,
        document_name="2025年年度报告",
        report_period_label="2025半年度",
    )

    normalized = service._normalize_extract_payload(
        document,
        {
            "title": "大额股份回购计划",
            "summary": "公司披露40-80亿元股份回购计划，累计已回购43.86亿元，需关注资金压力与回购执行风险。",
            "evidence_excerpt": "亿元",
            "event_type": "share_repurchase",
            "risk_points": ["融资与资金压力风险"],
            "keywords": ["股份回购", "40-80亿元", "43.86亿元"],
        },
        1,
    )

    assert normalized["evidence_excerpt"] != "亿元"
    assert "股份回购" in normalized["evidence_excerpt"]
    assert "40-80亿元" in normalized["evidence_excerpt"]
    assert "43.86亿元" in normalized["evidence_excerpt"]
