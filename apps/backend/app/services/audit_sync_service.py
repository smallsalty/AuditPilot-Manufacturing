from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DocumentMeta, EnterpriseProfile, ExternalEvent
from app.providers import AkshareFastProvider, CninfoProvider
from app.repositories.enterprise_repository import EnterpriseRepository
from app.utils.display_text import clean_document_title, clean_file_name_like


logger = logging.getLogger(__name__)


class AuditSyncService:
    SYNC_PENDING = "pending"
    SYNC_FETCHED = "fetched"
    SYNC_STORED = "stored"
    SYNC_SYNCING = "syncing"
    SYNC_PARSE_QUEUED = "parse_queued"
    SYNC_PARSED = "parsed"
    SYNC_PARSE_FAILED = "parse_failed"
    DISABLED_SOURCES = {"tushare_fast"}
    AUTO_SYNC_COOLDOWN_MINUTES = 10
    EMPTY_REASON_NO_SYNC_RUN = "no_sync_run"
    EMPTY_REASON_GENERIC_WINDOW_NO_DOCUMENTS = "generic_window_no_documents"
    EMPTY_REASON_ANNUAL_PACKAGE_NOT_PUBLISHED = "annual_package_not_published"
    EMPTY_REASON_PROVIDER_RETURNED_ONLY_OTHER = "provider_returned_only_other"
    EMPTY_REASON_PROVIDER_ERROR = "provider_error"

    def __init__(self) -> None:
        self.providers = {
            "akshare_fast": AkshareFastProvider(),
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
        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(company_id)
        if enterprise is None:
            raise ValueError("\u4f01\u4e1a\u4e0d\u5b58\u5728\u3002")

        requested_sources = sources or ["akshare_fast", "cninfo"]
        disabled = [source for source in requested_sources if source in self.DISABLED_SOURCES]
        if disabled:
            raise RuntimeError(f"\u7b2c\u4e00\u9636\u6bb5\u5df2\u7981\u7528\u8be5\u6570\u636e\u6e90\uff1a{', '.join(disabled)}")

        unsupported = [source for source in requested_sources if source not in self.providers]
        if unsupported:
            raise ValueError(f"\u4e0d\u652f\u6301\u7684\u6570\u636e\u6e90\uff1a{', '.join(unsupported)}")

        if enterprise.sync_status == self.SYNC_SYNCING:
            logger.info("sync skipped because enterprise %s is already syncing", company_id)
            return self._build_skipped_summary(
                enterprise,
                requested_sources,
                "\u5f53\u524d\u4f01\u4e1a\u540c\u6b65\u4efb\u52a1\u4ecd\u5728\u6267\u884c\u4e2d\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u3002",
            )

        if (
            date_from is None
            and date_to is None
            and repo.has_recent_successful_sync(company_id, self.AUTO_SYNC_COOLDOWN_MINUTES)
        ):
            logger.info("sync skipped because enterprise %s was synced recently", company_id)
            return self._build_skipped_summary(
                enterprise,
                requested_sources,
                "\u6700\u8fd1\u4e00\u6b21\u540c\u6b65\u5df2\u5b8c\u6210\uff0c\u5f53\u524d\u65e0\u9700\u91cd\u590d\u62c9\u53d6\u3002",
            )

        raw_date_to = date_to or date.today()
        is_initial_sync = self._is_initial_sync(db, enterprise)
        effective_date_to = self._default_date_to(
            enterprise,
            raw_date_to,
            is_initial_sync,
            explicit_date_to=date_to is not None,
        )
        effective_date_from = date_from or self._default_date_from(enterprise, effective_date_to, is_initial_sync)

        company_profile_updated = False
        announcements_fetched = 0
        documents_found = 0
        documents_inserted = 0
        events_found = 0
        events_inserted = 0
        other_found = 0
        parse_queued = 0
        annual_package_attempted = False
        annual_package_target_years: list[int] = []
        annual_package_found = 0
        annual_package_inserted = 0
        warnings: list[str] = []
        errors: list[str] = []

        enterprise.sync_status = self.SYNC_SYNCING
        db.flush()

        logger.info(
            "sync started enterprise_id=%s ticker=%s sources=%s date_from=%s date_to=%s is_initial_sync=%s",
            enterprise.id,
            enterprise.ticker,
            requested_sources,
            effective_date_from.isoformat(),
            effective_date_to.isoformat(),
            is_initial_sync,
        )

        for source_name in requested_sources:
            provider = self.providers[source_name]
            source_documents_found = 0
            source_events_found = 0
            source_other_found = 0

            try:
                profile_payload = provider.fetch_company_profile(enterprise.ticker)
                if profile_payload:
                    self._apply_profile(enterprise, profile_payload, provider.priority, provider.is_official_source)
                    company_profile_updated = True
            except Exception as exc:
                warnings.append(f"{source_name} \u4f01\u4e1a\u8d44\u6599\u540c\u6b65\u5931\u8d25\uff1a{exc}")
                logger.warning("profile sync failed enterprise_id=%s source=%s error=%s", enterprise.id, source_name, exc)
                continue

            try:
                announcements = provider.fetch_announcements(enterprise.ticker, effective_date_from, effective_date_to)
            except Exception as exc:
                errors.append(f"{source_name} \u516c\u544a\u540c\u6b65\u5931\u8d25\uff1a{exc}")
                logger.warning("announcement sync failed enterprise_id=%s source=%s error=%s", enterprise.id, source_name, exc)
                continue

            annual_package_items: list[dict[str, Any]] = []
            if source_name == "cninfo" and is_initial_sync:
                annual_package_attempted = True
                if not annual_package_target_years:
                    annual_package_target_years = self._build_annual_package_target_years(enterprise.report_year)
                for fiscal_year in annual_package_target_years:
                    try:
                        year_items = provider.fetch_annual_package(enterprise.ticker, fiscal_year)
                    except Exception as exc:
                        errors.append(f"{source_name} \u5e74\u62a5\u5305\u8865\u6293\u5931\u8d25\uff1a{exc}")
                        logger.warning(
                            "annual package sync failed enterprise_id=%s source=%s fiscal_year=%s error=%s",
                            enterprise.id,
                            source_name,
                            fiscal_year,
                            exc,
                        )
                        break
                    if year_items:
                        annual_package_items = year_items
                        annual_package_found = len(year_items)
                        break

            merged_announcements = self._merge_announcements(announcements, annual_package_items)

            announcements_fetched += len(merged_announcements)
            logger.info(
                "announcements fetched enterprise_id=%s source=%s count=%s",
                enterprise.id,
                source_name,
                len(merged_announcements),
            )

            if source_name == "cninfo" and not merged_announcements:
                warnings.append(
                    f"{source_name} \u5728 {effective_date_from.isoformat()}~{effective_date_to.isoformat()} \u672a\u8fd4\u56de\u76ee\u6807\u516c\u544a\u3002"
                )

            for item in merged_announcements:
                category = item.get("category") or "other"
                is_event_item = category == "penalty" or bool(item.get("title_matches"))
                if is_event_item:
                    events_found += 1
                    source_events_found += 1
                    event, created = self._upsert_event(
                        db=db,
                        enterprise=enterprise,
                        provider_name=provider.provider_name,
                        provider_priority=provider.priority,
                        official=provider.is_official_source,
                        payload=item,
                    )
                    if created:
                        events_inserted += 1
                    if event.sync_status == self.SYNC_PARSE_QUEUED:
                        parse_queued += 1
                elif category == "document":
                    documents_found += 1
                    source_documents_found += 1
                    document, created = self._upsert_document(
                        db=db,
                        enterprise=enterprise,
                        provider_name=provider.provider_name,
                        provider_priority=provider.priority,
                        official=provider.is_official_source,
                        payload=item,
                    )
                    if created:
                        documents_inserted += 1
                        if self._is_annual_package_item(item):
                            annual_package_inserted += 1
                    if document.sync_status == self.SYNC_PARSE_QUEUED:
                        parse_queued += 1
                else:
                    other_found += 1
                    source_other_found += 1

            if source_name == "cninfo" and merged_announcements and source_documents_found == 0 and source_events_found == 0:
                warnings.append(
                    f"{source_name} \u5df2\u6293\u53d6 {len(merged_announcements)} \u6761\u516c\u544a\uff0c"
                    "\u4f46\u5f53\u524d\u5206\u7c7b\u89c4\u5219\u672a\u547d\u4e2d\u8d22\u62a5\u7c7b\u5173\u952e\u8bcd\u3002"
                )

            logger.info(
                "source summary enterprise_id=%s source=%s document=%s penalty=%s other=%s",
                enterprise.id,
                source_name,
                source_documents_found,
                source_events_found,
                source_other_found,
            )

        enterprise.sync_status = self.SYNC_STORED if not errors else self.SYNC_FETCHED
        enterprise.latest_sync_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(enterprise)

        empty_reason = self._infer_empty_reason(
            announcements_fetched=announcements_fetched,
            documents_found=documents_found,
            events_found=events_found,
            other_found=other_found,
            annual_package_attempted=annual_package_attempted,
            annual_package_found=annual_package_found,
            errors=errors,
        )
        diagnostics = {
            "is_initial_sync": is_initial_sync,
            "window_kind": "audit_year" if is_initial_sync and date_from is None and date_to is None else "incremental",
            "date_from": effective_date_from.isoformat(),
            "date_to": effective_date_to.isoformat(),
            "initial_window": {
                "date_from": effective_date_from.isoformat(),
                "date_to": effective_date_to.isoformat(),
            },
            "annual_package_attempted": annual_package_attempted,
            "annual_package_target_years": annual_package_target_years,
            "annual_package_found": annual_package_found,
            "annual_package_inserted": annual_package_inserted,
            "empty_reason": empty_reason,
            "classification_counts": {
                "document": documents_found,
                "penalty": events_found,
                "other": other_found,
            },
        }
        self._persist_sync_diagnostics(enterprise, diagnostics, empty_reason)

        logger.info(
            "sync finished enterprise_id=%s announcements=%s documents_inserted=%s events_inserted=%s other=%s parse_queued=%s errors=%s diagnostics=%s",
            enterprise.id,
            announcements_fetched,
            documents_inserted,
            events_inserted,
            other_found,
            parse_queued,
            len(errors),
            diagnostics,
        )

        return {
            "enterprise_id": enterprise.id,
            "sources": requested_sources,
            "company_profile_updated": company_profile_updated,
            "announcements_fetched": announcements_fetched,
            "documents_found": documents_found,
            "documents_inserted": documents_inserted,
            "events_found": events_found,
            "events_inserted": events_inserted,
            "other_found": other_found,
            "parse_queued": parse_queued,
            "annual_package_attempted": annual_package_attempted,
            "annual_package_target_years": annual_package_target_years,
            "annual_package_found": annual_package_found,
            "annual_package_inserted": annual_package_inserted,
            "empty_reason": empty_reason,
            "warnings": warnings,
            "errors": errors,
            "diagnostics": diagnostics,
        }

    def _build_skipped_summary(self, enterprise: EnterpriseProfile, sources: list[str], message: str) -> dict[str, Any]:
        return {
            "enterprise_id": enterprise.id,
            "sources": sources,
            "company_profile_updated": False,
            "announcements_fetched": 0,
            "documents_found": 0,
            "documents_inserted": 0,
            "events_found": 0,
            "events_inserted": 0,
            "other_found": 0,
            "parse_queued": 0,
            "annual_package_attempted": False,
            "annual_package_target_years": [],
            "annual_package_found": 0,
            "annual_package_inserted": 0,
            "empty_reason": None,
            "warnings": [message],
            "errors": [],
            "diagnostics": None,
        }

    def _build_annual_package_target_years(self, report_year: int) -> list[int]:
        years = [report_year, report_year - 1]
        deduped: list[int] = []
        for year in years:
            if year >= 2000 and year not in deduped:
                deduped.append(year)
        return deduped

    def _merge_announcements(
        self,
        generic_items: list[dict[str, Any]],
        annual_package_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in generic_items:
            merged[self._announcement_dedupe_key(item)] = item
        for item in annual_package_items:
            key = self._announcement_dedupe_key(item)
            merged[key] = {**merged.get(key, {}), **item}
        return list(merged.values())

    def _announcement_dedupe_key(self, item: dict[str, Any]) -> str:
        if item.get("source_object_id"):
            return f"id:{item['source_object_id']}"
        return "|".join(
            [
                str(item.get("title") or ""),
                str(item.get("announcement_date") or ""),
                str(item.get("source_url") or ""),
            ]
        )

    def _is_annual_package_item(self, item: dict[str, Any]) -> bool:
        diagnostics = item.get("diagnostics") or {}
        return diagnostics.get("sync_path") == "annual_package"

    def _infer_empty_reason(
        self,
        *,
        announcements_fetched: int,
        documents_found: int,
        events_found: int,
        other_found: int,
        annual_package_attempted: bool,
        annual_package_found: int,
        errors: list[str],
    ) -> str | None:
        if documents_found > 0 or events_found > 0:
            return None
        if errors:
            return self.EMPTY_REASON_PROVIDER_ERROR
        if annual_package_attempted and annual_package_found == 0:
            if announcements_fetched == 0:
                return self.EMPTY_REASON_ANNUAL_PACKAGE_NOT_PUBLISHED
            if other_found > 0:
                return self.EMPTY_REASON_PROVIDER_RETURNED_ONLY_OTHER
        if announcements_fetched == 0:
            return self.EMPTY_REASON_GENERIC_WINDOW_NO_DOCUMENTS
        return self.EMPTY_REASON_PROVIDER_RETURNED_ONLY_OTHER

    def _persist_sync_diagnostics(
        self,
        enterprise: EnterpriseProfile,
        diagnostics: dict[str, Any],
        empty_reason: str | None,
    ) -> None:
        portrait = dict(enterprise.portrait or {})
        portrait["last_sync_diagnostics"] = diagnostics
        portrait["last_sync_empty_reason"] = empty_reason
        enterprise.portrait = portrait

    def _default_date_from(self, enterprise: EnterpriseProfile, effective_date_to: date, is_initial_sync: bool) -> date:
        if is_initial_sync:
            audit_year_start = date(enterprise.report_year, 1, 1)
            if effective_date_to < audit_year_start:
                return effective_date_to
            return audit_year_start
        return effective_date_to - timedelta(days=settings.sync_lookback_days)

    def _default_date_to(
        self,
        enterprise: EnterpriseProfile,
        effective_date_to: date,
        is_initial_sync: bool,
        *,
        explicit_date_to: bool,
    ) -> date:
        if not is_initial_sync or explicit_date_to:
            return effective_date_to
        audit_year_end = date(enterprise.report_year, 12, 31)
        return min(effective_date_to, audit_year_end)

    def _is_initial_sync(self, db: Session, enterprise: EnterpriseProfile) -> bool:
        existing_document = db.scalar(
            select(DocumentMeta.id).where(
                DocumentMeta.enterprise_id == enterprise.id,
                or_(DocumentMeta.source == "cninfo", DocumentMeta.is_official_source.is_(True)),
            ).limit(1)
        )
        existing_event = db.scalar(
            select(ExternalEvent.id).where(
                ExternalEvent.enterprise_id == enterprise.id,
                or_(ExternalEvent.source == "cninfo", ExternalEvent.is_official_source.is_(True)),
            ).limit(1)
        )
        return not bool(existing_document or existing_event)

    def _apply_profile(self, enterprise: EnterpriseProfile, payload: dict[str, Any], priority: int, official: bool) -> None:
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
        aliases = payload.get("company_name_aliases")
        if aliases:
            enterprise.company_name_aliases = aliases
        enterprise.source_url = payload.get("source_url") or enterprise.source_url
        enterprise.source_priority = max(enterprise.source_priority or 0, priority)
        enterprise.is_official_source = official or enterprise.is_official_source
        enterprise.source_object_id = payload.get("source_object_id") or enterprise.source_object_id
        if payload.get("raw_payload"):
            enterprise.portrait = {**(enterprise.portrait or {}), "sync_profile": payload["raw_payload"]}
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
            document_name=str(payload.get("title") or "\u672a\u547d\u540d\u6587\u6863"),
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
            "sync_diagnostics": payload.get("diagnostics"),
            "title_matches": payload.get("title_matches") or [],
            "primary_title_match": payload.get("primary_title_match"),
            "normalized_title": payload.get("normalized_title"),
        }
        file_url = payload.get("document_url")
        document.file_url = file_url
        document.file_name = self._infer_file_name(document.document_name, file_url)
        document.mime_type = self._infer_mime_type(file_url)
        if file_url:
            file_path, file_hash, file_size, download_status = self._download_file(
                file_url,
                enterprise.id,
                document.file_name or document.document_name,
            )
            if file_path:
                document.file_path = str(file_path)
            if file_hash:
                document.file_hash = file_hash
            document.file_size = file_size
            document.download_status = download_status
        else:
            document.download_status = "missing"
        document.sync_status = self.SYNC_PARSE_QUEUED if document.file_path or document.content_text else self.SYNC_FETCHED
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
            event_type=str(payload.get("event_type") or "announcement_title_match"),
            severity="medium",
            title=str(payload.get("title") or "\u672a\u547d\u540d\u4e8b\u4ef6"),
            summary=str(payload.get("summary") or payload.get("title") or ""),
        )
        event_payload = {
            "source_payload": payload.get("raw_payload"),
            "title_matches": payload.get("title_matches") or [],
            "primary_title_match": payload.get("primary_title_match"),
            "diagnostics": payload.get("diagnostics") or {},
        }
        event.event_type = str(payload.get("event_type") or "announcement_title_match")
        event.severity = str(payload.get("severity") or self._guess_severity(event.title))
        event.title = str(payload.get("title") or event.title)
        event.event_date = announcement_date
        event.announcement_date = announcement_date
        event.source = provider_name
        event.summary = str(payload.get("summary") or payload.get("title") or event.summary)
        event.payload = event_payload
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

    def _download_file(
        self,
        url: str,
        enterprise_id: int,
        file_name: str,
    ) -> tuple[Path | None, str | None, int | None, str]:
        safe_name = self._sanitize_file_name(file_name)
        target_dir = settings.uploads_dir / "synced" / str(enterprise_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
            target_path.write_bytes(content)
            return target_path, hashlib.sha256(content).hexdigest(), len(content), "downloaded"
        except Exception:
            return None, None, None, "failed"

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
        if any(keyword in title for keyword in ("\u7acb\u6848", "\u5904\u7f5a", "\u7eaa\u5f8b\u5904\u5206")):
            return "high"
        if any(keyword in title for keyword in ("\u76d1\u7ba1", "\u8b66\u793a\u51fd", "\u95ee\u8be2")):
            return "medium"
        return "low"

    @staticmethod
    def _infer_file_name(title: str, file_url: str | None) -> str:
        if file_url:
            suffix = Path(file_url.split("?")[0]).suffix
            if suffix:
                return f"{title}{suffix}"
        return f"{title}.pdf"

    @staticmethod
    def _infer_mime_type(file_url: str | None) -> str:
        if file_url and file_url.lower().endswith(".pdf"):
            return "application/pdf"
        return "application/octet-stream"

    @staticmethod
    def _sanitize_file_name(file_name: str) -> str:
        sanitized = "".join(char if char.isalnum() or char in ("-", "_", ".", " ") else "_" for char in file_name).strip()
        return sanitized[:180] or "document.pdf"

    @staticmethod
    def _normalize_document_title(title: Any) -> str:
        cleaned = clean_document_title(title)
        return cleaned or "未命名文档"

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
        normalized_title = self._normalize_document_title(payload.get("title"))
        content_hash = self._content_hash(
            title=normalized_title,
            announcement_date=announcement_date.isoformat() if announcement_date else "",
            content=payload.get("content_text") or payload.get("source_url") or "",
        )
        existing = self._find_document(
            db=db,
            enterprise_id=enterprise.id,
            source_object_id=payload.get("source_object_id"),
            title=normalized_title,
            announcement_date=announcement_date,
            content_hash=content_hash,
        )
        created = existing is None
        document = existing or DocumentMeta(
            enterprise_id=enterprise.id,
            document_name=normalized_title,
        )
        document.document_name = normalized_title
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
            "sync_diagnostics": payload.get("diagnostics"),
        }
        file_url = payload.get("document_url")
        document.file_url = file_url
        document.file_name = self._infer_file_name(document.document_name, file_url)
        document.mime_type = self._infer_mime_type(file_url)
        if file_url:
            file_path, file_hash, file_size, download_status = self._download_file(
                file_url,
                enterprise.id,
                document.file_name or document.document_name,
            )
            if file_path:
                document.file_path = str(file_path)
            if file_hash:
                document.file_hash = file_hash
            document.file_size = file_size
            document.download_status = download_status
        else:
            document.download_status = "missing"
        document.sync_status = self.SYNC_PARSE_QUEUED if document.file_path or document.content_text else self.SYNC_FETCHED
        if created:
            db.add(document)
        db.flush()
        return document, created

    def _find_document(
        self,
        db: Session,
        enterprise_id: int,
        source_object_id: str | None,
        title: str | None,
        announcement_date: date | None,
        content_hash: str,
    ) -> DocumentMeta | None:
        normalized_title = self._normalize_document_title(title)
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
            DocumentMeta.document_name == normalized_title,
            DocumentMeta.announcement_date == announcement_date,
            DocumentMeta.content_hash == content_hash,
        )
        return db.scalar(stmt)

    @staticmethod
    def _infer_file_name(title: str, file_url: str | None) -> str:
        if file_url:
            suffix = Path(file_url.split("?")[0]).suffix or ".pdf"
            return clean_file_name_like(title, fallback_suffix=suffix)
        return clean_file_name_like(title, fallback_suffix=".pdf")
