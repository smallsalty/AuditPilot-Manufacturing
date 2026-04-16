from app.models import AuditRule
from app.rule_engine.evaluator import RuleEvaluator


def test_rule_evaluator_applies_context_weight_multiplier() -> None:
    rule = AuditRule(
        code="DEBT_PRESSURE_HIGH",
        name="融资与偿债压力风险",
        risk_category="财务风险",
        risk_level="MEDIUM",
        description="desc",
        conditions={
            "logic": "all",
            "conditions": [{"metric": "short_term_debt_pressure", "operator": ">=", "value": 1, "label": "高杠杆"}],
        },
        focus_accounts=[],
        focus_processes=[],
        recommended_procedures=[],
        evidence_types=[],
        weight=2.0,
        enabled=True,
    )

    hit = RuleEvaluator().evaluate(
        rule,
        {"short_term_debt_pressure": 1.0, "latest_year": 2024.0},
        context_weight_multiplier=1.2,
        weight_reasons=["high_leverage_context"],
    )

    assert hit is not None
    assert hit.base_score == 50.0
    assert hit.score == 58.0
    assert hit.weight_multiplier == 1.2
    assert hit.weight_reasons == ["high_leverage_context"]
    assert hit.evidence_chain[0]["metadata"]["score_details"]["final_score"] == 58.0
