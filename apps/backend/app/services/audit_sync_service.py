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
            raise ValueError("企业不存在。")

        requested_sources = sources or ["akshare_fast", "cninfo"]
        disabled = [source for source in requested_sources if source in self.DISABLED_SOURCES]
        if disabled:
            raise RuntimeError(f"第一阶段已禁用该数据源：{', '.join(disabled)}")

        unsupported = [source for source in requested_sources if source not in self.providers]
        if unsupported:
            raise ValueError(f"不支持的数据源：{', '.join(unsupported)}")

        if enterprise.sync_status == self.SYNC_SYNCING:
            logger.info("sync skipped because enterprise %s is already syncing", company_id)
            return self._build_skipped_summary(enterprise, requested_sources, "当前企业同步任务仍在执行中，请稍后刷新。")

        if (
            date_from is None
            and date_to is None
            and repo.has_recent_successful_sync(company_id, self.AUTO_SYNC_COOLDOWN_MINUTES)
        ):
            logger.info("sync skipped because enterprise %s was synced recently", company_id)
            return self._build_skipped_summary(enterprise, requested_sources, "最近一次同步已完成，当前无需重复拉取。")

        effective_date_to = date_to or date.today()
        effective_date_from = date_from or self._default_date_from(db, enterprise, effective_date_to)

        company_profile_updated = False
        announcements_fetched = 0
        documents_found = 0
        documents_inserted = 0
        events_found = 0
        events_inserted = 0
        parse_queued = 0
        warnings: list[str] = []
        errors: list[str] = []

        enterprise.sync_status = self.SYNC_SYNCING
        db.flush()

        logger.info(
            "sync started enterprise_id=%s ticker=%s sources=%s date_from=%s date_to=%s",
            enterprise.id,
            enterprise.ticker,
            requested_sources,
            effective_date_from.isoformat(),
            effective_date_to.isoformat(),
        )

        for source_name in requested_sources:
            provider = self.providers[source_name]
            source_documents_found = 0
            source_events_found = 0

            try:
                profile_payload = provider.fetch_company_profile(enterprise.ticker)
                if profile_payload:
                    self._apply_profile(enterprise, profile_payload, provider.priority, provider.is_official_source)
                    company_profile_updated = True
            except Exception as exc:
                warnings.append(f"{source_name} 企业资料同步失败：{exc}")
                logger.warning("profile sync failed enterprise_id=%s source=%s error=%s", enterprise.id, source_name, exc)
                continue

            try:
                announcements = provider.fetch_announcements(enterprise.ticker, effective_date_from, effective_date_to)
            except Exception as exc:
                errors.append(f"{source_name} 公告同步失败：{exc}")
                logger.warning("announcement sync failed enterprise_id=%s source=%s error=%s", enterprise.id, source_name, exc)
                continue

            announcements_fetched += len(announcements)
            logger.info(
                "announcements fetched enterprise_id=%s source=%s count=%s",
                enterprise.id,
                source_name,
                len(announcements),
            )

            if source_name == "cninfo" and not announcements:
                warnings.append(
                    f"{source_name} 在 {effective_date_from.isoformat()}~{effective_date_to.isoformat()} 未返回目标公告。"
                )

            for item in announcements:
                category = item.get("category") or "other"
                if category == "document":
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
                    if document.sync_status == self.SYNC_PARSE_QUEUED:
                        parse_queued += 1
                elif category == "penalty":
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

            if source_name == "cninfo" and announcements and source_documents_found == 0 and source_events_found == 0:
                warnings.append(
                    f"{source_name} 已拉取 {len(announcements)} 条公告，但当前窗口内没有命中文档或处罚分类。"
                )

        enterprise.sync_status = self.SYNC_STORED if not errors else self.SYNC_FETCHED
        enterprise.latest_sync_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(enterprise)

        logger.info(
            "sync finished enterprise_id=%s announcements=%s documents_inserted=%s events_inserted=%s parse_queued=%s errors=%s",
            enterprise.id,
            announcements_fetched,
            documents_inserted,
            events_inserted,
            parse_queued,
            len(errors),
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
            "parse_queued": parse_queued,
            "warnings": warnings,
            "errors": errors,
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
            "parse_queued": 0,
            "warnings": [message],
            "errors": [],
        }

    def _default_date_from(self, db: Session, enterprise: EnterpriseProfile, effective_date_to: date) -> date:
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
        lookback_days = (
            settings.sync_lookback_days if (existing_document or existing_event) else settings.sync_initial_lookback_days
        )
        return effective_date_to - timedelta(days=lookback_days)

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
            document_name=str(payload.get("title") or "未命名文档"),
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
            event_type="regulatory_penalty",
            severity="medium",
            title=str(payload.get("title") or "未命名事件"),
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
        if any(keyword in title for keyword in ("立案", "处罚", "纪律处分")):
            return "high"
        if any(keyword in title for keyword in ("监管", "警示函", "问询")):
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
