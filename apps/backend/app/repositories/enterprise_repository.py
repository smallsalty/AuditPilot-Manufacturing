from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnterpriseProfile, ExternalEvent, FinancialIndicator


class EnterpriseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enterprises(self) -> list[EnterpriseProfile]:
        return list(self.db.scalars(select(EnterpriseProfile).order_by(EnterpriseProfile.id)).all())

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

