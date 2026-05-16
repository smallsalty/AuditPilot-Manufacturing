from typing import Any

from sqlalchemy.orm import Session

from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.document_risk_service import DocumentRiskService
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.financial_data_risk_service import FinancialDataRiskService
from app.services.risk_analysis_service import RiskAnalysisService


class DashboardService:
    CATEGORY_MAP = {
        "财务风险": "financial",
        "经营风险": "operational",
        "合规风险": "compliance",
        "内控风险": "compliance",
    }
    DOCUMENT_RISK_CATEGORY_MAP = {
        "revenue_recognition": "financial",
        "receivable_recoverability": "financial",
        "inventory_impairment": "operational",
        "cashflow_quality": "financial",
        "related_party_transaction": "compliance",
        "related_party_funds_occupation": "compliance",
        "litigation_compliance": "compliance",
        "internal_control_effectiveness": "compliance",
        "audit_opinion_issue": "compliance",
        "going_concern": "financial",
        "financing_pressure": "financial",
        "tax_effective_rate_anomaly": "compliance",
        "tax_cashflow_mismatch": "financial",
        "deferred_tax_volatility": "financial",
        "tax_payable_accrual": "compliance",
        "announcement_regulatory_litigation": "compliance",
        "announcement_accounting_audit": "compliance",
        "announcement_related_party_guarantee": "compliance",
        "announcement_debt_liquidity": "financial",
        "announcement_equity_control_pledge": "operational",
        "announcement_performance_revision_impairment": "financial",
        "announcement_governance_internal_control": "compliance",
        "governance_instability": "compliance",
        "market_signal_conflict": "operational",
        "uncategorized": "operational",
    }

    def _is_scored_risk(self, risk: dict[str, Any]) -> bool:
        return not (
            risk.get("source_type") == "baseline"
            or risk.get("source_mode") == "baseline_observation"
            or risk.get("is_baseline_observation") is True
        )

    def _resolve_bucket(self, risk: dict[str, Any]) -> str:
        risk_category = str(risk.get("risk_category") or "")
        if risk_category in self.CATEGORY_MAP:
            return self.CATEGORY_MAP[risk_category]
        canonical_risk_key = str(risk.get("canonical_risk_key") or "")
        return self.DOCUMENT_RISK_CATEGORY_MAP.get(canonical_risk_key, "operational")

    def _sort_risks(self, risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            [risk for risk in risks if self._is_scored_risk(risk)],
            key=lambda item: (-float(item.get("risk_score") or 0), str(item.get("risk_name") or "")),
        )

    def _average_score(self, risks: list[dict[str, Any]]) -> float:
        scores = [float(risk.get("risk_score") or 0) for risk in risks if risk.get("risk_score") is not None]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    def _is_announcement_risk(self, risk: dict[str, Any]) -> bool:
        return (
            risk.get("source_type") == "event"
            or risk.get("source_mode") == "announcement_event"
            or risk.get("evidence_status") == "announcement_event"
            or bool(risk.get("source_events"))
        )

    def _is_document_risk(self, risk: dict[str, Any]) -> bool:
        return (
            bool(risk.get("source_documents"))
            or risk.get("source_mode") in {"document_primary", "document_plus_rule", "document_rule"}
            or risk.get("evidence_status") in {"document_supported", "document_plus_rule"}
        )

    def build_dashboard(self, db: Session, enterprise_id: int) -> dict:
        enterprise_repo = EnterpriseRepository(db)
        enterprise = enterprise_repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        scored_results = self._sort_risks(DocumentRiskService().list_risks(db, enterprise_id))
        financial_analysis_service = FinancialAnalysisService()
        financial_analysis = financial_analysis_service.build_analysis(db, enterprise_id)
        latest_financial_anomalies = financial_analysis_service.latest_financial_anomalies(
            list(financial_analysis.get("anomalies") or [])
        )
        data_risks = FinancialDataRiskService().evaluate_indicators(enterprise_repo.get_financials(enterprise_id, official_only=True))
        announcement_risks = [risk for risk in scored_results if self._is_announcement_risk(risk)]
        document_risks = [risk for risk in scored_results if self._is_document_risk(risk) and not self._is_announcement_risk(risk)]

        financial = self._average_score(latest_financial_anomalies)
        operational = self._average_score(data_risks)
        compliance = self._average_score(announcement_risks)
        text_warning = self._average_score(document_risks)
        total = round((financial + operational + compliance + text_warning) / 4, 1)
        trend = [
            {"report_period": f"T{idx}", "risk_score": float(result.get("risk_score") or 0)}
            for idx, result in enumerate(scored_results[:6], 1)
        ]

        return {
            "enterprise": {
                "id": enterprise.id,
                "name": enterprise.name,
                "ticker": enterprise.ticker,
                "industry_tag": enterprise.industry_tag,
                "report_year": enterprise.report_year,
            },
            "score": {
                "total": total,
                "financial": financial,
                "operational": operational,
                "compliance": compliance,
                "text_warning": text_warning,
            },
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "radar": [
                {"name": "财务风险", "value": financial},
                {"name": "经营风险", "value": operational},
                {"name": "合规风险", "value": compliance},
                {"name": "文本预警", "value": text_warning},
                {"name": "综合风险", "value": total},
            ],
            "trend": trend or [{"report_period": "未分析", "risk_score": 0}],
            "top_risks": [
                {
                    "id": int(result.get("id") or 0),
                    "risk_name": str(result.get("risk_name") or ""),
                    "risk_level": str(result.get("risk_level") or ""),
                    "risk_score": float(result.get("risk_score") or 0),
                    "source_type": str(result.get("source_type") or ""),
                }
                for result in scored_results[:5]
            ],
        }
