from sqlalchemy.orm import Session

from app.repositories.risk_repository import RiskRepository


class AuditFocusService:
    def build_focus(self, db: Session, enterprise_id: int) -> dict:
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)
        focus_accounts = sorted({item for rec in recommendations for item in rec.focus_accounts})
        focus_processes = sorted({item for rec in recommendations for item in rec.focus_processes})
        procedures = sorted({item for rec in recommendations for item in rec.recommended_procedures})
        evidence_types = sorted({item for rec in recommendations for item in rec.evidence_types})
        return {
            "enterprise_id": enterprise_id,
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": procedures,
            "evidence_types": evidence_types,
            "recommendations": [rec.recommendation_text for rec in recommendations[:6]],
        }

