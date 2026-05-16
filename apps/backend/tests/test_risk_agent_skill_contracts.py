from __future__ import annotations

from types import SimpleNamespace

from app.ai.document_prompt_registry import DocumentPromptRegistry
from app.ai.llm_client import LLMClient
from app.ai.risk_agent_skill_registry import RiskAgentSkillRegistry
from app.services.announcement_event_analysis_service import AnnouncementEventAnalysisService
from app.services.document_analysis_pipeline import DocumentAnalysisPipeline
from app.services.document_risk_service import DocumentRiskService


class DummyPipelineService:
    llm_client = SimpleNamespace(model="deepseek-v4-flash")

    def _trim_evidence_safe(self, value, limit=200):
        return str(value or "")[:limit]


def test_risk_agent_skills_have_structured_output_contracts():
    expected = {
        "data_risk_analysis",
        "document_risk_analysis",
        "announcement_risk_analysis",
        "financial_report_risk_analysis",
    }

    assert set(RiskAgentSkillRegistry.SKILLS) == expected
    for skill in RiskAgentSkillRegistry.SKILLS.values():
        contract = skill.output_contract()
        assert "required_top_level_keys" in contract
        assert "required_item_keys" in contract
        assert "required_any_of" in contract
        assert "fixed_item_fields" in contract
        assert "forbidden_item_fields" in contract


def test_document_prompts_use_skill_contracts_and_financial_prompt_rules():
    candidate = {
        "section_title": "Management discussion",
        "summary": "Governance issue",
        "evidence_excerpt": "The CFO resigned during the reporting period.",
    }

    document_prompt = DocumentPromptRegistry.build_prompts(
        document_name="2025 annual report",
        classified_type="annual_report",
        prompt_type="annual_report",
        candidates=[candidate],
    )
    financial_prompt = DocumentPromptRegistry.build_prompts(
        document_name="2025 interim report",
        classified_type="annual_report",
        prompt_type="annual_financial_subanalysis",
        candidates=[candidate],
    )

    assert document_prompt["agent_skill"] == "document_risk_analysis"
    assert document_prompt["required_item_keys"] == RiskAgentSkillRegistry.get("document_risk_analysis").required_item_keys
    assert financial_prompt["agent_skill"] == "financial_report_risk_analysis"
    assert financial_prompt["required_any_of"] == RiskAgentSkillRegistry.get("financial_report_risk_analysis").required_any_of
    assert "required_output_contract" in financial_prompt["system_prompt"]
    assert "JSON number" in financial_prompt["system_prompt"]


def test_announcement_skill_contract_is_validated():
    service = AnnouncementEventAnalysisService(llm_client=SimpleNamespace())
    valid_result = {
        "summary": "Regulatory inquiry risk.",
        "key_facts": ["Inquiry received."],
        "risk_points": ["Disclosure risk."],
        "audit_focus": ["Review response."],
        "evidence_excerpt": "The company received an inquiry letter.",
    }

    assert service._validate_skill_result(valid_result, "announcement_risk_analysis") is None
    assert service._validate_skill_result({"summary": "Missing fields."}, "announcement_risk_analysis") is not None


def test_document_skill_rejects_financial_report_items():
    pipeline = DocumentAnalysisPipeline(DummyPipelineService())

    items, diagnostics, error = pipeline.validate_llm_stage_result(
        result={
            "items": [
                {
                    "title": "Revenue anomaly",
                    "summary": "Revenue requires audit attention.",
                    "evidence_excerpt": "Revenue increased by 30%.",
                    "extract_family": "financial_statement",
                    "metric_name": "revenue",
                    "risk_points": ["revenue recognition"],
                }
            ],
            "parsed_ok": True,
            "payload_mode": "dict",
        },
        classified_type="annual_report",
        prompt_template="document_extract:annual_report",
        schema_name="annual_report_extract_v1",
        required_item_keys=(),
        required_any_of=(),
        candidate_count=1,
        llm_input_chars=100,
        max_tokens=2048,
        agent_skill="document_risk_analysis",
    )

    assert items == []
    assert error["error_type"] == "skill_contract_validation_error"
    assert diagnostics["rejected_item_count"] == 1


def test_financial_skill_rejects_items_without_financial_fields():
    pipeline = DocumentAnalysisPipeline(DummyPipelineService())

    items, diagnostics, error = pipeline.validate_llm_stage_result(
        result={
            "items": [
                {
                    "title": "Generic issue",
                    "summary": "The report contains a generic issue.",
                    "evidence_excerpt": "Generic disclosure.",
                    "risk_points": ["generic"],
                }
            ],
            "parsed_ok": True,
            "payload_mode": "dict",
        },
        classified_type="annual_report",
        prompt_template="document_extract:annual_financial_subanalysis",
        schema_name="annual_financial_subanalysis_v1",
        required_item_keys=(),
        required_any_of=(),
        candidate_count=1,
        llm_input_chars=100,
        max_tokens=4096,
        agent_skill="financial_report_risk_analysis",
    )

    assert items == []
    assert error["error_type"] == "skill_contract_validation_error"
    assert diagnostics["rejected_item_count"] == 1


def test_financial_subanalysis_is_skipped_by_document_risk_service():
    service = DocumentRiskService()
    extract = SimpleNamespace(
        extract_family="financial_statement",
        detail_level="financial_deep_dive",
        parameters={"analysis_stage": "financial_subanalysis"},
        content="{}",
    )
    feature = SimpleNamespace(
        feature_type="metric",
        payload={
            "extract_family": "financial_statement",
            "parameters": {"analysis_stage": "financial_subanalysis"},
        },
    )

    assert service._is_financial_report_extract(extract) is True
    assert service._is_financial_report_feature(feature) is True


def test_llm_client_recovers_complete_items_from_truncated_items_object():
    client = object.__new__(LLMClient)
    raw = (
        '{"items":[{"title":"Revenue","summary":"Revenue changed.",'
        '"evidence_excerpt":"Revenue increased 30%.","metric_name":"revenue",'
        '"financial_topics":["revenue"],"note_refs":[]},'
        '{"title":"Credit impairment","summary":"unfinished"'
    )

    result = client._parse_json_response(raw)

    assert result["parsed_ok"] is True
    assert result["payload_mode"] == "partial_items_dict"
    assert len(result["items"]) == 1
    assert result["items"][0]["metric_name"] == "revenue"


def test_llm_client_skips_later_invalid_items_with_bad_json_number():
    client = object.__new__(LLMClient)
    raw = (
        '{"items":[{"title":"Revenue","summary":"Revenue changed.",'
        '"evidence_excerpt":"Revenue increased 30%.","metric_name":"revenue",'
        '"financial_topics":["revenue"],"note_refs":[]},'
        '{"title":"Credit impairment","summary":"Bad number",'
        '"evidence_excerpt":"Credit impairment -418,585","metric_value":-418,585}]}'
    )

    result = client._parse_json_response(raw)

    assert result["parsed_ok"] is True
    assert result["payload_mode"] == "partial_items_dict"
    assert len(result["items"]) == 1
