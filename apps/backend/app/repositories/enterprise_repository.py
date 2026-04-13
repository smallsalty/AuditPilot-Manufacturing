from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, DocumentMeta, EnterpriseProfile, ExternalEvent, FinancialIndicator


class EnterpriseRepository:
    OFFICIAL_DOCUMENT_SOURCES = {"cninfo", "upload"}
    OFFICIAL_EVENT_SOURCES = {"cninfo", "upload"}
    OFFICIAL_FINANCIAL_SOURCES = {"akshare"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enterprises(
        self,
        query: str | None = None,
        official_only: bool = False,
    ) -> list[EnterpriseProfile]:
        stmt = select(EnterpriseProfile)
        if official_only:
            stmt = stmt.where(
                or_(
                    EnterpriseProfile.source_object_id.is_not(None),
                    EnterpriseProfile.source_url.is_not(None),
                    EnterpriseProfile.sync_status.in_(["syncing", "stored", "parse_queued", "parsed"]),
                    EnterpriseProfile.id.in_(
                        select(DocumentMeta.enterprise_id).where(
                            or_(
                                DocumentMeta.is_official_source.is_(True),
                                DocumentMeta.source.in_(self.OFFICIAL_DOCUMENT_SOURCES),
                            )
                        )
                    ),
                )
            )
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

    def find_by_name(self, name: str) -> EnterpriseProfile | None:
        normalized = name.strip().lower().replace(" ", "")
        if not normalized:
            return None
        stmt = select(EnterpriseProfile).where(
            or_(
                func.replace(func.lower(EnterpriseProfile.name), " ", "") == normalized,
                func.replace(func.lower(func.coalesce(EnterpriseProfile.description, "")), " ", "").contains(normalized),
            )
        )
        return self.db.scalar(stmt)

    def get_financials(self, enterprise_id: int, official_only: bool = False) -> list[FinancialIndicator]:
        stmt = select(FinancialIndicator).where(FinancialIndicator.enterprise_id == enterprise_id)
        if official_only:
            stmt = stmt.where(FinancialIndicator.source.in_(self.OFFICIAL_FINANCIAL_SOURCES))
        stmt = stmt.order_by(FinancialIndicator.report_period, FinancialIndicator.indicator_code)
        return list(self.db.scalars(stmt).all())

    def get_external_events(self, enterprise_id: int, official_only: bool = False) -> list[ExternalEvent]:
        stmt = select(ExternalEvent).where(ExternalEvent.enterprise_id == enterprise_id)
        if official_only:
            stmt = stmt.where(
                or_(
                    ExternalEvent.is_official_source.is_(True),
                    ExternalEvent.source.in_(self.OFFICIAL_EVENT_SOURCES),
                )
            )
        stmt = stmt.order_by(ExternalEvent.event_date.desc(), ExternalEvent.id.desc())
        return list(self.db.scalars(stmt).all())

    def get_documents(self, enterprise_id: int, official_only: bool = False) -> list[DocumentMeta]:
        stmt = select(DocumentMeta).where(DocumentMeta.enterprise_id == enterprise_id)
        if official_only:
            stmt = stmt.where(
                or_(
                    DocumentMeta.is_official_source.is_(True),
                    DocumentMeta.source.in_(self.OFFICIAL_DOCUMENT_SOURCES),
                )
            )
        stmt = stmt.order_by(DocumentMeta.created_at.desc(), DocumentMeta.id.desc())
        return list(self.db.scalars(stmt).all())

    def get_latest_analysis_run(self, enterprise_id: int) -> AnalysisRun | None:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.enterprise_id == enterprise_id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        )
        return self.db.scalar(stmt)

    def get_latest_sync_document(self, enterprise_id: int) -> DocumentMeta | None:
        stmt = (
            select(DocumentMeta)
            .where(
                DocumentMeta.enterprise_id == enterprise_id,
                or_(
                    DocumentMeta.is_official_source.is_(True),
                    DocumentMeta.source.in_(self.OFFICIAL_DOCUMENT_SOURCES),
                ),
            )
            .order_by(DocumentMeta.ingestion_time.desc(), DocumentMeta.created_at.desc(), DocumentMeta.id.desc())
        )
        return self.db.scalar(stmt)

    def get_latest_sync_event(self, enterprise_id: int) -> ExternalEvent | None:
        stmt = (
            select(ExternalEvent)
            .where(
                ExternalEvent.enterprise_id == enterprise_id,
                or_(
                    ExternalEvent.is_official_source.is_(True),
                    ExternalEvent.source.in_(self.OFFICIAL_EVENT_SOURCES),
                ),
            )
            .order_by(ExternalEvent.ingestion_time.desc(), ExternalEvent.created_at.desc(), ExternalEvent.id.desc())
        )
        return self.db.scalar(stmt)

    def count_official_documents(self, enterprise_id: int) -> int:
        stmt = select(func.count(DocumentMeta.id)).where(
            DocumentMeta.enterprise_id == enterprise_id,
            or_(
                DocumentMeta.is_official_source.is_(True),
                DocumentMeta.source.in_(self.OFFICIAL_DOCUMENT_SOURCES),
            ),
        )
        return int(self.db.scalar(stmt) or 0)

    def count_official_events(self, enterprise_id: int) -> int:
        stmt = select(func.count(ExternalEvent.id)).where(
            ExternalEvent.enterprise_id == enterprise_id,
            or_(
                ExternalEvent.is_official_source.is_(True),
                ExternalEvent.source.in_(self.OFFICIAL_EVENT_SOURCES),
            ),
        )
        return int(self.db.scalar(stmt) or 0)

    def has_recent_successful_sync(self, enterprise_id: int, minutes: int) -> bool:
        enterprise = self.get_by_id(enterprise_id)
        if enterprise is None or not enterprise.latest_sync_at:
            return False
        latest_sync = enterprise.latest_sync_at
        if latest_sync.tzinfo is None:
            latest_sync = latest_sync.replace(tzinfo=timezone.utc)
        return enterprise.sync_status == "stored" and latest_sync >= datetime.now(timezone.utc) - timedelta(minutes=minutes)
