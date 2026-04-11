from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DocumentMeta, EnterpriseProfile, ExternalEvent
from app.providers import CninfoProvider, TushareFastProvider
from app.repositories.enterprise_repository import EnterpriseRepository


class AuditSyncService:
    SYNC_PENDING = "pending"
    SYNC_FETCHED = "fetched"
    SYNC_STORED = "stored"
    SYNC_PARSE_QUEUED = "parse_queued"

    def __init__(self) -> None:
        self.providers = {
            "tushare_fast": TushareFastProvider(),
            "cninfo": CninfoProvider(),
        }

    def sync_company(
        self,
        db: Session,
        company_id: int,
        sources: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        enterprise = EnterpriseRepository(db).get_by_id(company_id)
        if enterprise is None:
            raise ValueError("Enterprise not found")

        effective_sources = [source for source in (sources or ["tushare_fast", "cninfo"]) if source in self.providers]
        if not effective_sources:
            raise ValueError("No supported sync sources selected")

        effective_date_to = date_to or date.today()
        effective_date_from = date_from or (effective_date_to - timedelta(days=settings.sync_lookback_days))

        profile_updated = False
        documents_stored = 0
        events_stored = 0
        parse_queued = 0

        enterprise.sync_status = self.SYNC_PENDING
        db.flush()

        for source_name in effective_sources:
            provider = self.providers[source_name]
            profile_payload = provider.fetch_company_profile(enterprise.ticker)
            if profile_payload:
                self._apply_profile(enterprise, profile_payload, provider.priority, provider.is_official_source)
                profile_updated = True

            announcements = provider.fetch_announcements(enterprise.ticker, effective_date_from, effective_date_to)
            for item in announcements:
                category = item.get("category") or "other"
                if category == "document":
                    document, created = self._upsert_document(
                        db=db,
                        enterprise=enterprise,
                        provider_name=provider.provider_name,
                        provider_priority=provider.priority,
                        official=provider.is_official_source,
                        payload=item,
                    )
                    if created:
                        documents_stored += 1
                    if document.sync_status == self.SYNC_PARSE_QUEUED:
                        parse_queued += 1
                elif category == "penalty":
                    event, created = self._upsert_event(
                        db=db,
                        enterprise=enterprise,
                        provider_name=provider.provider_name,
                        provider_priority=provider.priority,
                        official=provider.is_official_source,
                        payload=item,
                    )
                    if created:
                        events_stored += 1
                    if event.sync_status == self.SYNC_PARSE_QUEUED:
                        parse_queued += 1

        enterprise.sync_status = self.SYNC_STORED
        enterprise.latest_sync_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(enterprise)

        return {
            "company_id": enterprise.id,
            "company_name": enterprise.name,
            "sources": effective_sources,
            "profile_updated": profile_updated,
            "documents_stored": documents_stored,
            "events_stored": events_stored,
            "parse_queued": parse_queued,
            "message": f"Stored {documents_stored} documents and {events_stored} events.",
        }

    def _apply_profile(
        self,
        enterprise: EnterpriseProfile,
        payload: dict[str, Any],
        priority: int,
        official: bool,
    ) -> None:
        if payload.get("name"):
            enterprise.name = payload["name"]
        if payload.get("industry_tag"):
            enterprise.industry_tag = payload["industry_tag"]
        if payload.get("exchange"):
            enterprise.exchange = payload["exchange"]
        if payload.get("province"):
            enterprise.province = payload["province"]
        if payload.get("listed_date"):
            enterprise.listed_date = date.fromisoformat(payload["listed_date"])
        enterprise.source_url = payload.get("source_url") or enterprise.source_url
        enterprise.source_priority = max(enterprise.source_priority or 0, priority)
        enterprise.is_official_source = official or enterprise.is_official_source
        enterprise.source_object_id = payload.get("source_object_id") or enterprise.source_object_id
        if payload.get("raw_payload"):
            enterprise.portrait = {**(enterprise.portrait or {}), "sync_profile": payload["raw_payload"]}
        enterprise.sync_status = self.SYNC_STORED
        enterprise.ingestion_time = datetime.now(timezone.utc)

    def _upsert_document(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        provider_name: str,
        provider_priority: int,
        official: bool,
        payload: dict[str, Any],
    ) -> tuple[DocumentMeta, bool]:
        announcement_date = self._parse_date(payload.get("announcement_date"))
        content_hash = self._content_hash(
            title=payload.get("title"),
            announcement_date=announcement_date.isoformat() if announcement_date else "",
            content=payload.get("content_text") or payload.get("source_url") or "",
        )
        existing = self._find_document(
            db=db,
            enterprise_id=enterprise.id,
            source_object_id=payload.get("source_object_id"),
            title=payload.get("title"),
            announcement_date=announcement_date,
            content_hash=content_hash,
        )
        created = existing is None
        document = existing or DocumentMeta(
            enterprise_id=enterprise.id,
            document_name=str(payload.get("title") or "Untitled document"),
        )
        document.document_name = str(payload.get("title") or document.document_name)
        document.document_type = str(payload.get("document_type") or document.document_type or "annual_report")
        document.source = provider_name
        document.source_url = payload.get("source_url")
        document.source_priority = provider_priority
        document.sync_status = self.SYNC_FETCHED
        document.ingestion_time = datetime.now(timezone.utc)
        document.is_official_source = official
        document.source_object_id = payload.get("source_object_id")
        document.announcement_date = announcement_date
        document.report_period_label = payload.get("report_period")
        document.fiscal_year = self._guess_fiscal_year(document.document_name, announcement_date)
        document.raw_payload = payload.get("raw_payload")
        document.content_text = payload.get("content_text") or document.content_text
        document.content_hash = content_hash
        document.metadata_json = {
            **(document.metadata_json or {}),
            "source_payload": payload.get("raw_payload"),
            "source_provider": provider_name,
        }
        file_url = payload.get("document_url")
        if file_url:
            file_path, file_hash = self._download_file(file_url, enterprise.id, document.document_name)
            if file_path:
                document.file_path = str(file_path)
            if file_hash:
                document.file_hash = file_hash
        document.sync_status = self.SYNC_PARSE_QUEUED
        if created:
            db.add(document)
        db.flush()
        return document, created

    def _upsert_event(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        provider_name: str,
        provider_priority: int,
        official: bool,
        payload: dict[str, Any],
    ) -> tuple[ExternalEvent, bool]:
        announcement_date = self._parse_date(payload.get("announcement_date"))
        content_hash = self._content_hash(
            title=payload.get("title"),
            announcement_date=announcement_date.isoformat() if announcement_date else "",
            content=payload.get("summary") or payload.get("source_url") or "",
        )
        existing = self._find_event(
            db=db,
            enterprise_id=enterprise.id,
            source_object_id=payload.get("source_object_id"),
            title=payload.get("title"),
            announcement_date=announcement_date,
            content_hash=content_hash,
        )
        created = existing is None
        event = existing or ExternalEvent(
            enterprise_id=enterprise.id,
            event_type="regulatory_penalty",
            severity="medium",
            title=str(payload.get("title") or "Untitled event"),
            summary=str(payload.get("summary") or payload.get("title") or ""),
        )
        event.event_type = str(payload.get("event_type") or "regulatory_penalty")
        event.severity = str(payload.get("severity") or self._guess_severity(event.title))
        event.title = str(payload.get("title") or event.title)
        event.event_date = announcement_date
        event.announcement_date = announcement_date
        event.source = provider_name
        event.summary = str(payload.get("summary") or payload.get("title") or event.summary)
        event.payload = payload.get("raw_payload")
        event.source_url = payload.get("source_url")
        event.source_priority = provider_priority
        event.sync_status = self.SYNC_PARSE_QUEUED
        event.parser_version = None
        event.ingestion_time = datetime.now(timezone.utc)
        event.is_official_source = official
        event.source_object_id = payload.get("source_object_id")
        event.content_hash = content_hash
        event.raw_payload = payload.get("raw_payload")
        event.regulator = payload.get("regulator") or "cninfo"
        if created:
            db.add(event)
        db.flush()
        return event, created

    def _find_document(
        self,
        db: Session,
        enterprise_id: int,
        source_object_id: str | None,
        title: str | None,
        announcement_date: date | None,
        content_hash: str,
    ) -> DocumentMeta | None:
        if source_object_id:
            stmt = select(DocumentMeta).where(
                DocumentMeta.enterprise_id == enterprise_id,
                DocumentMeta.source_object_id == source_object_id,
            )
            existing = db.scalar(stmt)
            if existing is not None:
                return existing
        stmt = select(DocumentMeta).where(
            DocumentMeta.enterprise_id == enterprise_id,
            DocumentMeta.document_name == str(title or ""),
            DocumentMeta.announcement_date == announcement_date,
            DocumentMeta.content_hash == content_hash,
        )
        return db.scalar(stmt)

    def _find_event(
        self,
        db: Session,
        enterprise_id: int,
        source_object_id: str | None,
        title: str | None,
        announcement_date: date | None,
        content_hash: str,
    ) -> ExternalEvent | None:
        if source_object_id:
            stmt = select(ExternalEvent).where(
                ExternalEvent.enterprise_id == enterprise_id,
                ExternalEvent.source_object_id == source_object_id,
            )
            existing = db.scalar(stmt)
            if existing is not None:
                return existing
        stmt = select(ExternalEvent).where(
            ExternalEvent.enterprise_id == enterprise_id,
            ExternalEvent.title == str(title or ""),
            ExternalEvent.announcement_date == announcement_date,
            ExternalEvent.content_hash == content_hash,
        )
        return db.scalar(stmt)

    def _download_file(self, url: str, enterprise_id: int, title: str) -> tuple[Path | None, str | None]:
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in title)[:80] or "document"
        suffix = ".pdf" if url.lower().endswith(".pdf") else ".bin"
        target_dir = settings.uploads_dir / "synced" / str(enterprise_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{safe_name}{suffix}"
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
            target_path.write_bytes(content)
            return target_path, hashlib.sha256(content).hexdigest()
        except Exception:
            return None, None

    @staticmethod
    def _content_hash(title: Any, announcement_date: str, content: str) -> str:
        raw = f"{title or ''}|{announcement_date}|{content or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @staticmethod
    def _guess_fiscal_year(title: str, announcement_date: date | None) -> int | None:
        digits = "".join(ch for ch in title if ch.isdigit())
        if len(digits) >= 4:
            first_year = digits[:4]
            if first_year.isdigit():
                return int(first_year)
        return announcement_date.year if announcement_date else None

    @staticmethod
    def _guess_severity(title: str) -> str:
        if any(keyword in title for keyword in ("立案", "处罚", "纪律处分")):
            return "high"
        if any(keyword in title for keyword in ("监管", "警示函", "问询")):
            return "medium"
        return "low"
