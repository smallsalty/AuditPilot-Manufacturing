from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import EnterpriseProfile
from app.providers.audit.akshare_fast_provider import AkshareFastProvider
from app.repositories.enterprise_repository import EnterpriseRepository
from app.repositories.risk_repository import RiskRepository
from app.services.risk_analysis_service import RiskAnalysisService


class EnterpriseRuntimeService:
    def __init__(self) -> None:
        self.akshare_provider = AkshareFastProvider()

    def bootstrap(self, db: Session, ticker: str | None = None, name: str | None = None) -> dict[str, Any]:
        repo = EnterpriseRepository(db)
        profile = self.akshare_provider.resolve_company_profile(ticker=ticker, name=name)
        if not profile:
            raise ValueError("未找到可引入的企业，请检查股票代码或公司名称。")

        resolved_ticker = str(profile["ticker"]).upper()
        enterprise = repo.get_by_ticker(resolved_ticker)
        created = enterprise is None
        if enterprise is None:
            enterprise = EnterpriseProfile(
                name=profile.get("name") or resolved_ticker,
                ticker=resolved_ticker,
                report_year=datetime.now().year,
                industry_tag=profile.get("industry_tag") or "制造业",
                exchange=profile.get("exchange") or ("SSE" if resolved_ticker.endswith(".SH") else "SZSE"),
            )
            db.add(enterprise)

        if not created and name:
            matched = repo.find_by_name(name)
            if matched and matched.id != enterprise.id:
                enterprise = matched

        if profile.get("name"):
            enterprise.name = profile["name"]
        enterprise.ticker = resolved_ticker
        enterprise.exchange = profile.get("exchange") or enterprise.exchange
        enterprise.industry_tag = profile.get("industry_tag") or enterprise.industry_tag
        enterprise.province = profile.get("province") or enterprise.province
        enterprise.listed_date = (
            datetime.fromisoformat(profile["listed_date"]).date()
            if profile.get("listed_date")
            else enterprise.listed_date
        )
        aliases = [item for item in (profile.get("company_name_aliases") or []) if item]
        if aliases:
            enterprise.company_name_aliases = sorted(set((enterprise.company_name_aliases or []) + aliases))
        enterprise.source_url = profile.get("source_url") or enterprise.source_url
        enterprise.source_priority = max(enterprise.source_priority or 0, 50)
        enterprise.sync_status = enterprise.sync_status if not created else "never_synced"
        enterprise.source_object_id = profile.get("source_object_id") or enterprise.source_object_id
        enterprise.ingestion_time = datetime.utcnow()
        enterprise.is_official_source = True
        db.commit()
        db.refresh(enterprise)

        return {
          "enterprise_id": enterprise.id,
          "created": created,
          "name": enterprise.name,
          "ticker": enterprise.ticker,
          "industry_tag": enterprise.industry_tag,
        }

    def build_readiness(self, db: Session, company_id: int) -> dict[str, Any]:
        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(company_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        official_doc_count = repo.count_official_documents(company_id)
        official_event_count = repo.count_official_events(company_id)
        analysis_state = RiskAnalysisService().get_analysis_state(db, company_id)
        risk_results = RiskRepository(db).list_results(company_id)
        latest_sync_doc = repo.get_latest_sync_document(company_id)
        latest_sync_event = repo.get_latest_sync_event(company_id)

        last_sync_at = enterprise.latest_sync_at or enterprise.ingestion_time
        if latest_sync_doc and latest_sync_doc.ingestion_time and (not last_sync_at or latest_sync_doc.ingestion_time > last_sync_at):
            last_sync_at = latest_sync_doc.ingestion_time
        if latest_sync_event and latest_sync_event.ingestion_time and (not last_sync_at or latest_sync_event.ingestion_time > last_sync_at):
            last_sync_at = latest_sync_event.ingestion_time

        if enterprise.sync_status == "syncing":
            sync_status = "syncing"
        elif enterprise.sync_status == "failed":
            sync_status = "failed"
        elif official_doc_count > 0 or official_event_count > 0:
            sync_status = "synced"
        else:
            sync_status = "never_synced"

        return {
            "enterprise_id": enterprise.id,
            "profile_ready": bool(enterprise.name and enterprise.ticker),
            "sync_status": sync_status,
            "official_doc_count": official_doc_count,
            "official_event_count": official_event_count,
            "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
            "last_sync_source": "cninfo" if official_doc_count or official_event_count else "akshare_fast",
            "risk_analysis_status": analysis_state["analysis_status"],
            "qa_ready": analysis_state["analysis_status"] == "completed" and (official_doc_count > 0 or len(risk_results) > 0),
        }
