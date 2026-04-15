from collections import Counter

from sqlalchemy.orm import Session

from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.enterprise_runtime_service import EnterpriseRuntimeService
from app.utils.display_text import clean_document_title


class AuditOverviewService:
    def build_profile(self, db: Session, company_id: int) -> dict:
        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(company_id)
        if enterprise is None:
            raise ValueError("企业不存在")

        documents = repo.get_documents(company_id, official_only=True)
        events = repo.get_external_events(company_id, official_only=True)
        readiness = EnterpriseRuntimeService().build_readiness(db, company_id)
        latest_document = documents[0] if documents else None
        latest_event = events[0] if events else None

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
            "sync_status": readiness["sync_status"],
            "source_priority": enterprise.source_priority,
            "is_official_source": enterprise.is_official_source,
            "latest_sync_at": readiness["last_sync_at"],
            "document_count": len(documents),
            "penalty_count": len(events),
            "latest_document_date": latest_document.announcement_date.isoformat() if latest_document and latest_document.announcement_date else None,
            "latest_penalty_date": latest_event.announcement_date.isoformat() if latest_event and latest_event.announcement_date else None,
            "data_sources": {
                "profile": "akshare_fast",
                "documents": "cninfo/upload",
                "events": "cninfo",
                "risk_analysis_status": readiness["risk_analysis_status"],
            },
        }

    def build_timeline(self, db: Session, company_id: int) -> list[dict]:
        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(company_id)
        if enterprise is None:
            raise ValueError("企业不存在")

        documents = repo.get_documents(company_id, official_only=True)[:30]
        events = repo.get_external_events(company_id, official_only=True)[:30]

        timeline = [
            {
                "id": f"document-{document.id}",
                "item_type": "document",
                "title": clean_document_title(document.document_name),
                "date": document.announcement_date.isoformat() if document.announcement_date else None,
                "source": document.source,
                "status": document.parse_status or document.sync_status,
                "document_type": document.document_type,
                "summary": clean_document_title(document.document_name),
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
        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(company_id)
        if enterprise is None:
            raise ValueError("企业不存在")

        documents = repo.get_documents(company_id, official_only=True)
        events = repo.get_external_events(company_id, official_only=True)
        readiness = EnterpriseRuntimeService().build_readiness(db, company_id)

        doc_counter = Counter(document.document_type for document in documents if document.document_type)
        event_counter = Counter(event.severity for event in events if event.severity)
        highlights: list[str] = []

        if doc_counter:
            dominant_doc_type, dominant_count = doc_counter.most_common(1)[0]
            highlights.append(f"已同步 {sum(doc_counter.values())} 份官方文档，当前主类型为 {dominant_doc_type}（{dominant_count}）。")
        if events:
            latest_event = sorted(
                events,
                key=lambda item: (item.announcement_date or item.event_date) or enterprise.listed_date,
                reverse=True,
            )[0]
            highlights.append(f"最新监管信号：{latest_event.title}")
        if not highlights:
            highlights.append("当前企业尚无可展示的官方文档或监管事件。")

        return {
            "document_count": len(documents),
            "penalty_count": len(events),
            "official_document_count": len(documents),
            "high_severity_penalty_count": sum(1 for event in events if event.severity == "high"),
            "sync_status": readiness["sync_status"],
            "highlights": highlights,
            "document_breakdown": dict(doc_counter),
            "severity_breakdown": dict(event_counter),
        }
