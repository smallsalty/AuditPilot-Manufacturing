from __future__ import annotations

from datetime import date
from typing import Any


class DocumentFeatureService:
    FEATURE_VERSION = "document-feature:v1"

    EVENT_TO_RISK_KEY = {
        "share_repurchase": "financing_pressure",
        "convertible_bond": "financing_pressure",
        "executive_change": "governance_instability",
        "litigation": "litigation_compliance",
        "penalty_or_inquiry": "litigation_compliance",
        "guarantee": "financing_pressure",
        "related_party_transaction": "related_party_transaction",
        "audit_opinion_issue": "audit_opinion_issue",
        "internal_control_issue": "internal_control_effectiveness",
        "financial_anomaly": "cashflow_quality",
    }

    def build_features(self, extracts: list[dict[str, Any]], *, enterprise_id: int, document_id: int) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []
        for extract in extracts:
            if extract.get("event_type") or extract.get("opinion_type"):
                features.append(
                    {
                        "enterprise_id": enterprise_id,
                        "document_id": document_id,
                        "feature_version": self.FEATURE_VERSION,
                        "feature_type": "event" if extract.get("event_type") else "opinion",
                        "event_type": extract.get("event_type"),
                        "canonical_risk_key": extract.get("canonical_risk_key")
                        or self.EVENT_TO_RISK_KEY.get(str(extract.get("event_type") or extract.get("opinion_type") or "")),
                        "event_date": self._coerce_date(extract.get("event_date")),
                        "subject": extract.get("subject"),
                        "amount": extract.get("amount"),
                        "counterparty": extract.get("counterparty"),
                        "direction": extract.get("direction"),
                        "severity": extract.get("severity"),
                        "conditions": extract.get("conditions"),
                        "opinion_type": extract.get("opinion_type"),
                        "defect_level": extract.get("defect_level"),
                        "conclusion": extract.get("conclusion"),
                        "affected_scope": extract.get("affected_scope"),
                        "auditor_or_board_source": extract.get("auditor_or_board_source"),
                        "metric_name": extract.get("metric_name"),
                        "metric_value": extract.get("metric_value"),
                        "metric_unit": extract.get("metric_unit"),
                        "period": extract.get("period"),
                        "fiscal_year": extract.get("fiscal_year"),
                        "fiscal_quarter": extract.get("fiscal_quarter"),
                        "payload": {
                            "evidence_span_id": extract.get("evidence_span_id"),
                            "extract_family": extract.get("extract_family"),
                            "fact_tags": extract.get("fact_tags") or [],
                            "summary": extract.get("summary") or extract.get("problem_summary"),
                            "parameters": extract.get("parameters") or {},
                        },
                    }
                )
            elif extract.get("metric_name") and extract.get("metric_value") is not None:
                features.append(
                    {
                        "enterprise_id": enterprise_id,
                        "document_id": document_id,
                        "feature_version": self.FEATURE_VERSION,
                        "feature_type": "metric",
                        "metric_name": extract.get("metric_name"),
                        "metric_value": extract.get("metric_value"),
                        "metric_unit": extract.get("metric_unit"),
                        "period": extract.get("period"),
                        "fiscal_year": extract.get("fiscal_year"),
                        "fiscal_quarter": extract.get("fiscal_quarter"),
                        "canonical_risk_key": extract.get("canonical_risk_key"),
                        "payload": {
                            "compare_target": extract.get("compare_target"),
                            "compare_value": extract.get("compare_value"),
                            "evidence_span_id": extract.get("evidence_span_id"),
                            "summary": extract.get("summary") or extract.get("problem_summary"),
                            "parameters": extract.get("parameters") or {},
                        },
                    }
                )
        return features

    def _coerce_date(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            text = value.strip()
            if len(text) >= 10:
                try:
                    return date.fromisoformat(text[:10])
                except ValueError:
                    return None
        return None
