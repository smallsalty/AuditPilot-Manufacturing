from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, DocumentMeta, EnterpriseProfile, ExternalEvent, FinancialIndicator


class EnterpriseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enterprises(self, query: str | None = None) -> list[EnterpriseProfile]:
        stmt = select(EnterpriseProfile)
        if query:
            normalized = query.strip().lower().replace(" ", "")
            if normalized:
                stmt = stmt.where(
                    or_(
                        func.replace(func.lower(EnterpriseProfile.name), " ", "").contains(normalized),
                        func.replace(func.lower(EnterpriseProfile.ticker), " ", "").contains(normalized),
                    )
                )
        stmt = stmt.order_by(EnterpriseProfile.id)
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, enterprise_id: int) -> EnterpriseProfile | None:
        return self.db.get(EnterpriseProfile, enterprise_id)

    def get_by_ticker(self, ticker: str) -> EnterpriseProfile | None:
        stmt = select(EnterpriseProfile).where(EnterpriseProfile.ticker == ticker)
        return self.db.scalar(stmt)

    def get_financials(self, enterprise_id: int) -> list[FinancialIndicator]:
        stmt = (
            select(FinancialIndicator)
            .where(FinancialIndicator.enterprise_id == enterprise_id)
            .order_by(FinancialIndicator.report_period, FinancialIndicator.indicator_code)
        )
        return list(self.db.scalars(stmt).all())

    def get_external_events(self, enterprise_id: int) -> list[ExternalEvent]:
        stmt = (
            select(ExternalEvent)
            .where(ExternalEvent.enterprise_id == enterprise_id)
            .order_by(ExternalEvent.event_date.desc(), ExternalEvent.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_documents(self, enterprise_id: int) -> list[DocumentMeta]:
        stmt = (
            select(DocumentMeta)
            .where(DocumentMeta.enterprise_id == enterprise_id)
            .order_by(DocumentMeta.created_at.desc(), DocumentMeta.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_latest_analysis_run(self, enterprise_id: int) -> AnalysisRun | None:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.enterprise_id == enterprise_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        )
        return self.db.scalar(stmt)
