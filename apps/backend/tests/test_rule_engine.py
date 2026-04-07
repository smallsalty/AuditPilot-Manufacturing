from app.models import AuditRule
from app.rule_engine.evaluator import RuleEvaluator


def test_rule_evaluator_returns_hit_when_threshold_exceeded() -> None:
    rule = AuditRule(
        code="TEST_RULE",
        name="测试规则",
        risk_category="财务风险",
        risk_level="HIGH",
        description="desc",
        conditions={
            "logic": "all",
            "conditions": [
                {"metric": "ar_revenue_growth_gap", "operator": ">", "value": 0.1, "label": "应收增速过快"}
            ],
        },
        focus_accounts=["应收账款"],
        focus_processes=["回款管理"],
        recommended_procedures=["期后回款测试"],
        evidence_types=["回款流水"],
        weight=3.0,
        enabled=True,
    )
    hit = RuleEvaluator().evaluate(rule, {"ar_revenue_growth_gap": 0.3, "latest_year": 2024.0})
    assert hit is not None
    assert hit.reasons == ["应收增速过快"]
    assert hit.score > 0

