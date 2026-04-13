from sqlalchemy.orm import Session

from app.services.risk_analysis_service import RiskAnalysisService
from app.services.document_risk_service import DocumentRiskService


class AuditFocusService:
    SOURCE_LABELS = {
        "financial_anomaly": "来自财务异常",
        "risk_rule": "来自规则命中",
        "announcement_event": "来自公告事件",
        "penalty_event": "来自处罚/问询",
        "uploaded_document": "来自上传文档",
        "management_interview": "来自管理层访谈建议",
    }

    def build_focus(self, db: Session, enterprise_id: int) -> dict:
        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        risk_items = DocumentRiskService().build_focus_items(db, enterprise_id)
        recommendation_items = []
        for item in risk_items:
            recommendation_items.append(
                {
                    "text": item["summary"],
                    "sources": [self.SOURCE_LABELS.get(source, source) for source in (item.get("sources") or [])],
                }
            )

        return {
            "enterprise_id": enterprise_id,
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "focus_accounts": [],
            "focus_processes": [],
            "recommended_procedures": [],
            "evidence_types": [],
            "recommendations": [rec["text"] for rec in recommendation_items],
            "recommendation_items": recommendation_items,
            "items": risk_items,
        }
