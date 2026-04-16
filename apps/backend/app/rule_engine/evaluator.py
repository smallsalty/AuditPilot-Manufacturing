from dataclasses import dataclass
from typing import Any

from app.models import AuditRule


@dataclass
class RuleHit:
    rule: AuditRule
    score: float
    reasons: list[str]
    evidence_chain: list[dict[str, Any]]
    base_score: float
    effective_weight: float
    weight_multiplier: float
    weight_reasons: list[str]


class RuleEvaluator:
    OPERATOR_MAP = {
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
    }

    def evaluate(
        self,
        rule: AuditRule,
        features: dict[str, Any],
        *,
        context_weight_multiplier: float = 1.0,
        weight_reasons: list[str] | None = None,
    ) -> RuleHit | None:
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
            actual_value = self._coerce_float(features.get(metric))
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
        multiplier = min(1.30, max(0.0, float(context_weight_multiplier or 1.0)))
        effective_weight = float(rule.weight or 0.0) * multiplier
        base_score = min(100.0, float(rule.weight or 0.0) * 20.0 + len(reasons) * 10.0)
        score = min(100.0, effective_weight * 20.0 + len(reasons) * 10.0)
        details = {
            "base_score": base_score,
            "final_score": score,
            "effective_weight": effective_weight,
            "weight_multiplier": multiplier,
            "weight_reasons": list(weight_reasons or []),
        }
        for evidence in evidence_chain:
            metadata = evidence.setdefault("metadata", {})
            metadata["score_details"] = details
        return RuleHit(
            rule=rule,
            score=score,
            reasons=reasons,
            evidence_chain=evidence_chain,
            base_score=base_score,
            effective_weight=effective_weight,
            weight_multiplier=multiplier,
            weight_reasons=list(weight_reasons or []),
        )

    def _coerce_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
