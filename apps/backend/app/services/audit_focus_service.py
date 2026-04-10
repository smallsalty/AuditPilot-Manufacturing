from sqlalchemy.orm import Session

from app.repositories.risk_repository import RiskRepository
from app.services.risk_analysis_service import RiskAnalysisService


class AuditFocusService:
    def build_focus(self, db: Session, enterprise_id: int) -> dict:
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)
        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        focus_accounts = sorted({item for rec in recommendations for item in rec.focus_accounts})
        focus_processes = sorted({item for rec in recommendations for item in rec.focus_processes})
        procedures = sorted({item for rec in recommendations for item in rec.recommended_procedures})
        evidence_types = sorted({item for rec in recommendations for item in rec.evidence_types})
        return {
            "enterprise_id": enterprise_id,
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": procedures,
            "evidence_types": evidence_types,
            "recommendations": [rec.recommendation_text for rec in recommendations[:6]],
        }
