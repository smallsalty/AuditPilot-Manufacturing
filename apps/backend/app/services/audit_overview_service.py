from collections import Counter

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import DocumentMeta, EnterpriseProfile, ExternalEvent


class AuditOverviewService:
    def build_profile(self, db: Session, company_id: int) -> dict:
        enterprise = db.get(EnterpriseProfile, company_id)
        if enterprise is None:
            raise ValueError("Enterprise not found")
        document_count = db.scalar(
            select(func.count(DocumentMeta.id)).where(DocumentMeta.enterprise_id == company_id)
        ) or 0
        penalty_count = db.scalar(
            select(func.count(ExternalEvent.id)).where(ExternalEvent.enterprise_id == company_id)
        ) or 0
        latest_document_date = db.scalar(
            select(func.max(DocumentMeta.announcement_date)).where(DocumentMeta.enterprise_id == company_id)
        )
        latest_event_date = db.scalar(
            select(func.max(ExternalEvent.announcement_date)).where(ExternalEvent.enterprise_id == company_id)
        )
        latest_sync_time = enterprise.latest_sync_at or enterprise.ingestion_time
        return {
            "company": {
                "id": enterprise.id,
                "name": enterprise.name,
                "ticker": enterprise.ticker,
                "industry_tag": enterprise.industry_tag,
                "exchange": enterprise.exchange,
                "report_year": enterprise.report_year,
                "province": enterprise.province,
                "city": enterprise.city,
                "listed_date": enterprise.listed_date.isoformat() if enterprise.listed_date else None,
                "description": enterprise.description,
            },
            "sync_status": enterprise.sync_status,
            "source_priority": enterprise.source_priority,
            "is_official_source": enterprise.is_official_source,
            "latest_sync_at": latest_sync_time.isoformat() if latest_sync_time else None,
            "document_count": int(document_count),
            "penalty_count": int(penalty_count),
            "latest_document_date": latest_document_date.isoformat() if latest_document_date else None,
            "latest_penalty_date": latest_event_date.isoformat() if latest_event_date else None,
        }

    def build_timeline(self, db: Session, company_id: int) -> list[dict]:
        enterprise = db.get(EnterpriseProfile, company_id)
        if enterprise is None:
            raise ValueError("Enterprise not found")
        documents = list(
            db.scalars(
                select(DocumentMeta)
                .where(DocumentMeta.enterprise_id == company_id)
                .order_by(desc(DocumentMeta.announcement_date), desc(DocumentMeta.created_at))
                .limit(30)
            ).all()
        )
        events = list(
            db.scalars(
                select(ExternalEvent)
                .where(ExternalEvent.enterprise_id == company_id)
                .order_by(desc(ExternalEvent.announcement_date), desc(ExternalEvent.created_at))
                .limit(30)
            ).all()
        )
        timeline = [
            {
                "id": f"document-{document.id}",
                "item_type": "document",
                "title": document.document_name,
                "date": document.announcement_date.isoformat() if document.announcement_date else None,
                "source": document.source,
                "status": document.sync_status,
                "document_type": document.document_type,
                "summary": document.document_name,
                "source_url": document.source_url,
                "is_official_source": document.is_official_source,
            }
            for document in documents
        ] + [
            {
                "id": f"event-{event.id}",
                "item_type": "event",
                "title": event.title,
                "date": (event.announcement_date or event.event_date).isoformat()
                if (event.announcement_date or event.event_date)
                else None,
                "source": event.source,
                "status": event.sync_status,
                "event_type": event.event_type,
                "severity": event.severity,
                "summary": event.summary,
                "source_url": event.source_url,
                "is_official_source": event.is_official_source,
            }
            for event in events
        ]
        return sorted(timeline, key=lambda item: item.get("date") or "", reverse=True)

    def build_risk_summary(self, db: Session, company_id: int) -> dict:
        enterprise = db.get(EnterpriseProfile, company_id)
        if enterprise is None:
            raise ValueError("Enterprise not found")
        documents = list(
            db.scalars(select(DocumentMeta).where(DocumentMeta.enterprise_id == company_id)).all()
        )
        events = list(
            db.scalars(select(ExternalEvent).where(ExternalEvent.enterprise_id == company_id)).all()
        )
        doc_counter = Counter(document.document_type for document in documents if document.document_type)
        event_counter = Counter(event.severity for event in events if event.severity)
        highlights: list[str] = []
        if doc_counter:
            dominant_doc_type, dominant_count = doc_counter.most_common(1)[0]
            highlights.append(f"{sum(doc_counter.values())} synced report records. Dominant type: {dominant_doc_type} ({dominant_count}).")
        if events:
            latest_event = sorted(
                events,
                key=lambda item: (item.announcement_date or item.event_date) or enterprise.listed_date,
                reverse=True,
            )[0]
            highlights.append(f"Latest regulatory signal: {latest_event.title}.")
        if not highlights:
            highlights.append("No synced audit reports or regulatory events are available yet.")
        return {
            "document_count": len(documents),
            "penalty_count": len(events),
            "official_document_count": sum(1 for document in documents if document.is_official_source),
            "high_severity_penalty_count": sum(1 for event in events if event.severity == "high"),
            "sync_status": enterprise.sync_status,
            "highlights": highlights,
            "document_breakdown": dict(doc_counter),
            "severity_breakdown": dict(event_counter),
        }
