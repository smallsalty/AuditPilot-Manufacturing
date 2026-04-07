from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditRecommendation, RiskIdentificationResult


class RiskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def clear_enterprise_results(self, enterprise_id: int) -> None:
        self.db.execute(delete(AuditRecommendation).where(AuditRecommendation.enterprise_id == enterprise_id))
        self.db.execute(delete(RiskIdentificationResult).where(RiskIdentificationResult.enterprise_id == enterprise_id))

    def list_results(self, enterprise_id: int) -> list[RiskIdentificationResult]:
        stmt = (
            select(RiskIdentificationResult)
            .where(RiskIdentificationResult.enterprise_id == enterprise_id)
            .order_by(RiskIdentificationResult.risk_score.desc(), RiskIdentificationResult.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_recommendations(self, enterprise_id: int) -> list[AuditRecommendation]:
        stmt = (
            select(AuditRecommendation)
            .where(AuditRecommendation.enterprise_id == enterprise_id)
            .order_by(AuditRecommendation.id.desc())
        )
        return list(self.db.scalars(stmt).all())

