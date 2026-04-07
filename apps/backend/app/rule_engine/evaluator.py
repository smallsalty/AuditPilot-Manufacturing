from dataclasses import dataclass
from typing import Any

from app.models import AuditRule


@dataclass
class RuleHit:
    rule: AuditRule
    score: float
    reasons: list[str]
    evidence_chain: list[dict[str, Any]]


class RuleEvaluator:
    OPERATOR_MAP = {
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
    }

    def evaluate(self, rule: AuditRule, features: dict[str, float]) -> RuleHit | None:
        config = rule.conditions or {}
        logic = config.get("logic", "all")
        conditions = config.get("conditions", [])
        hits: list[bool] = []
        reasons: list[str] = []
        evidence_chain: list[dict[str, Any]] = []
        for condition in conditions:
            metric = condition["metric"]
            operator = condition.get("operator", ">")
            threshold = float(condition.get("value", 0))
            actual_value = float(features.get(metric, 0.0))
            passed = self.OPERATOR_MAP[operator](actual_value, threshold)
            hits.append(passed)
            if passed:
                label = condition.get("label") or f"{metric} {operator} {threshold}"
                reasons.append(label)
                evidence_chain.append(
                    {
                        "type": "metric",
                        "title": metric,
                        "content": f"{metric}={actual_value:.2f}, 阈值 {operator} {threshold:.2f}",
                        "source": "feature_engineering",
                        "report_period": str(int(features.get("latest_year", 0))),
                        "metadata": {"metric": metric, "value": actual_value, "threshold": threshold},
                    }
                )
        matched = all(hits) if logic == "all" else any(hits)
        if not matched:
            return None
        score = min(100.0, rule.weight * 20.0 + len(reasons) * 10.0)
        return RuleHit(rule=rule, score=score, reasons=reasons, evidence_chain=evidence_chain)

