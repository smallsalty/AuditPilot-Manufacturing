from app.models import AuditRule
from app.services.risk_analysis_service import RiskAnalysisService


def test_light_asset_weighting_uses_strict_whitelist() -> None:
    service = RiskAnalysisService()
    rule = AuditRule(code="AR_COLLECTION", name="应收风险", risk_category="财务风险", risk_level="HIGH", description="d", conditions={}, focus_accounts=[], focus_processes=[], recommended_procedures=[], evidence_types=[], weight=1.0)

    manufacturing_multiplier, manufacturing_reasons = service._rule_weight_context(
        rule,
        {"industry_comparison": {"industry_code": "manufacturing"}},
    )
    light_multiplier, light_reasons = service._rule_weight_context(
        rule,
        {"industry_comparison": {"industry_code": "software_service"}},
    )

    assert manufacturing_multiplier == 1.0
    assert manufacturing_reasons == []
    assert light_multiplier == 1.15
    assert light_reasons == ["light_asset_industry"]


def test_high_leverage_weighting_targets_debt_rules() -> None:
    service = RiskAnalysisService()
    debt_rule = AuditRule(code="DEBT_PRESSURE_HIGH", name="偿债压力", risk_category="财务风险", risk_level="MEDIUM", description="d", conditions={}, focus_accounts=[], focus_processes=[], recommended_procedures=[], evidence_types=[], weight=1.0)

    multiplier, reasons = service._rule_weight_context(
        debt_rule,
        {"latest_debt_ratio": 70.0, "industry_comparison": {"industry_code": "manufacturing"}},
    )

    assert multiplier == 1.2
    assert reasons == ["high_leverage_context"]
