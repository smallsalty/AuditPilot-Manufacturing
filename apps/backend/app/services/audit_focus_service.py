from sqlalchemy.orm import Session

from app.repositories.risk_repository import RiskRepository
from app.services.risk_analysis_service import RiskAnalysisService


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
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)
        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        focus_accounts = sorted({item for rec in recommendations for item in rec.focus_accounts})
        focus_processes = sorted({item for rec in recommendations for item in rec.focus_processes})
        procedures = sorted({item for rec in recommendations for item in rec.recommended_procedures})
        evidence_types = sorted({item for rec in recommendations for item in rec.evidence_types})

        recommendation_items = []
        for rec in recommendations[:6]:
          labels = [self.SOURCE_LABELS.get(item, item) for item in (rec.evidence_types or [])]
          recommendation_items.append({"text": rec.recommendation_text, "sources": labels})

        return {
            "enterprise_id": enterprise_id,
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": procedures,
            "evidence_types": evidence_types,
            "recommendations": [rec["text"] for rec in recommendation_items],
            "recommendation_items": recommendation_items,
        }
