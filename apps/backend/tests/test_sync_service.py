from datetime import date, datetime
from types import SimpleNamespace

import app.services.enterprise_runtime_service as enterprise_runtime_service_module
from app.services.audit_sync_service import AuditSyncService
from app.services.enterprise_runtime_service import EnterpriseRuntimeService


class _DummyDb:
    def __init__(self) -> None:
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, _value) -> None:
        return None


class _DummyProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        generic_items: list[dict] | None = None,
        annual_items: dict[int, list[dict]] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.priority = 100 if provider_name == "cninfo" else 50
        self.is_official_source = provider_name == "cninfo"
        self.generic_items = generic_items or []
        self.annual_items = annual_items or {}

    def fetch_company_profile(self, _ticker: str):
        return None

    def fetch_announcements(self, _ticker: str, _date_from: date, _date_to: date) -> list[dict]:
        return list(self.generic_items)

    def fetch_annual_package(self, _ticker: str, fiscal_year: int) -> list[dict]:
        return list(self.annual_items.get(fiscal_year, []))


def _make_enterprise(report_year: int = 2025):
    return SimpleNamespace(
        id=1,
        name="测试企业",
        ticker="000001.SZ",
        report_year=report_year,
        sync_status="never_synced",
        latest_sync_at=None,
        ingestion_time=None,
        portrait=None,
        source_url=None,
        source_priority=0,
        is_official_source=False,
        source_object_id=None,
        industry_tag="制造业",
        exchange="SZSE",
        province=None,
        listed_date=None,
        company_name_aliases=None,
    )


def _make_document_item(source_object_id: str, title: str, *, fiscal_year: int, sync_path: str = "annual_package") -> dict:
    return {
        "source_object_id": source_object_id,
        "title": title,
        "announcement_date": f"{fiscal_year + 1}-03-30",
        "source_url": f"https://example.com/{source_object_id}.pdf",
        "document_url": f"https://example.com/{source_object_id}.pdf",
        "content_text": None,
        "raw_payload": {"announcementId": source_object_id},
        "category": "document",
        "document_type": "annual_report",
        "diagnostics": {"sync_path": sync_path, "fiscal_year": fiscal_year},
    }


def _make_other_item(source_object_id: str, title: str) -> dict:
    return {
        "source_object_id": source_object_id,
        "title": title,
        "announcement_date": "2026-04-01",
        "source_url": f"https://example.com/{source_object_id}.pdf",
        "document_url": f"https://example.com/{source_object_id}.pdf",
        "content_text": None,
        "raw_payload": {"announcementId": source_object_id},
        "category": "other",
        "document_type": None,
        "diagnostics": {"sync_path": "generic_window"},
    }


def test_bootstrap_sets_previous_year_as_default_report_year(monkeypatch) -> None:
    class _DummyDateTime:
        @classmethod
        def now(cls) -> datetime:
            return datetime(2026, 4, 15, 9, 0, 0)

        @classmethod
        def utcnow(cls) -> datetime:
            return datetime(2026, 4, 15, 9, 0, 0)

        @classmethod
        def fromisoformat(cls, value: str) -> datetime:
            return datetime.fromisoformat(value)

    db = _DummyDb()
    service = EnterpriseRuntimeService()
    service.akshare_provider = SimpleNamespace(
        resolve_company_profile=lambda **_: {
            "ticker": "000425.SZ",
            "name": "徐工机械",
            "industry_tag": "制造业",
            "exchange": "SZSE",
        }
    )

    monkeypatch.setattr(enterprise_runtime_service_module, "datetime", _DummyDateTime)
    monkeypatch.setattr(
        "app.services.enterprise_runtime_service.EnterpriseRepository.get_by_ticker",
        lambda self, ticker: None,
    )
    monkeypatch.setattr(
        "app.services.enterprise_runtime_service.EnterpriseRepository.find_by_name",
        lambda self, name: None,
    )

    service.bootstrap(db, ticker="000425.SZ")

    assert db.added
    assert db.added[0].report_year == 2025


def test_initial_sync_falls_back_to_previous_fiscal_year_annual_package(monkeypatch) -> None:
    service = AuditSyncService()
    enterprise = _make_enterprise(report_year=2025)
    db = _DummyDb()
    cninfo = _DummyProvider(
        provider_name="cninfo",
        annual_items={
            2024: [_make_document_item("doc-2024", "2024年年度报告", fiscal_year=2024)],
        },
    )
    service.providers = {
        "akshare_fast": _DummyProvider(provider_name="akshare_fast"),
        "cninfo": cninfo,
    }
    created_ids: set[str] = set()

    monkeypatch.setattr("app.services.audit_sync_service.EnterpriseRepository.get_by_id", lambda self, company_id: enterprise)
    monkeypatch.setattr(
        "app.services.audit_sync_service.EnterpriseRepository.has_recent_successful_sync",
        lambda self, company_id, minutes: False,
    )
    monkeypatch.setattr(service, "_is_initial_sync", lambda db, enterprise: True)
    monkeypatch.setattr(service, "_apply_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "_upsert_document",
        lambda **kwargs: (
            SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED),
            kwargs["payload"]["source_object_id"] not in created_ids and not created_ids.add(kwargs["payload"]["source_object_id"]),
        ),
    )
    monkeypatch.setattr(service, "_upsert_event", lambda **kwargs: (SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED), True))

    result = service.sync_company(db, company_id=enterprise.id)

    assert result["annual_package_attempted"] is True
    assert result["annual_package_target_years"] == [2025, 2024]
    assert result["annual_package_found"] == 1
    assert result["annual_package_inserted"] == 1
    assert result["documents_found"] == 1
    assert result["empty_reason"] is None
    assert enterprise.portrait["last_sync_diagnostics"]["annual_package_found"] == 1


def test_initial_sync_marks_provider_returned_only_other_when_no_documents(monkeypatch) -> None:
    service = AuditSyncService()
    enterprise = _make_enterprise(report_year=2025)
    db = _DummyDb()
    service.providers = {
        "akshare_fast": _DummyProvider(provider_name="akshare_fast"),
        "cninfo": _DummyProvider(
            provider_name="cninfo",
            generic_items=[_make_other_item("other-1", "关于回购公司股份的公告")],
            annual_items={2025: [], 2024: []},
        ),
    }

    monkeypatch.setattr("app.services.audit_sync_service.EnterpriseRepository.get_by_id", lambda self, company_id: enterprise)
    monkeypatch.setattr(
        "app.services.audit_sync_service.EnterpriseRepository.has_recent_successful_sync",
        lambda self, company_id, minutes: False,
    )
    monkeypatch.setattr(service, "_is_initial_sync", lambda db, enterprise: True)
    monkeypatch.setattr(service, "_apply_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_upsert_document", lambda **kwargs: (SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED), True))
    monkeypatch.setattr(service, "_upsert_event", lambda **kwargs: (SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED), True))

    result = service.sync_company(db, company_id=enterprise.id)

    assert result["documents_found"] == 0
    assert result["empty_reason"] == service.EMPTY_REASON_PROVIDER_RETURNED_ONLY_OTHER
    assert enterprise.portrait["last_sync_empty_reason"] == service.EMPTY_REASON_PROVIDER_RETURNED_ONLY_OTHER


def test_initial_sync_marks_annual_package_not_published_when_everything_is_empty(monkeypatch) -> None:
    service = AuditSyncService()
    enterprise = _make_enterprise(report_year=2025)
    db = _DummyDb()
    service.providers = {
        "akshare_fast": _DummyProvider(provider_name="akshare_fast"),
        "cninfo": _DummyProvider(provider_name="cninfo", annual_items={2025: [], 2024: []}),
    }

    monkeypatch.setattr("app.services.audit_sync_service.EnterpriseRepository.get_by_id", lambda self, company_id: enterprise)
    monkeypatch.setattr(
        "app.services.audit_sync_service.EnterpriseRepository.has_recent_successful_sync",
        lambda self, company_id, minutes: False,
    )
    monkeypatch.setattr(service, "_is_initial_sync", lambda db, enterprise: True)
    monkeypatch.setattr(service, "_apply_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_upsert_document", lambda **kwargs: (SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED), True))
    monkeypatch.setattr(service, "_upsert_event", lambda **kwargs: (SimpleNamespace(sync_status=service.SYNC_PARSE_QUEUED), True))

    result = service.sync_company(db, company_id=enterprise.id)

    assert result["announcements_fetched"] == 0
    assert result["empty_reason"] == service.EMPTY_REASON_ANNUAL_PACKAGE_NOT_PUBLISHED


def test_build_readiness_exposes_no_sync_run_when_enterprise_has_no_history(monkeypatch) -> None:
    enterprise = SimpleNamespace(
        id=7,
        name="测试企业",
        ticker="000001.SZ",
        sync_status="never_synced",
        latest_sync_at=None,
        ingestion_time=None,
        portrait={},
    )

    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_by_id", lambda self, company_id: enterprise)
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.count_official_documents", lambda self, company_id: 0)
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.count_official_events", lambda self, company_id: 0)
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_financials", lambda self, company_id, official_only=True: [])
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_external_events", lambda self, company_id, official_only=True: [])
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_documents", lambda self, company_id, official_only=True: [])
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_latest_sync_document", lambda self, company_id: None)
    monkeypatch.setattr("app.services.enterprise_runtime_service.EnterpriseRepository.get_latest_sync_event", lambda self, company_id: None)
    monkeypatch.setattr(
        "app.services.enterprise_runtime_service.RiskAnalysisService.get_analysis_readiness",
        lambda enterprise, financials, events, documents: {
            "risk_analysis_ready": False,
            "risk_analysis_reason": "no_official_data",
            "risk_analysis_message": "暂无官方数据",
        },
    )
    monkeypatch.setattr(
        "app.services.enterprise_runtime_service.RiskAnalysisService.get_analysis_state",
        lambda self, db, company_id: {"analysis_status": "not_started"},
    )
    monkeypatch.setattr("app.services.enterprise_runtime_service.RiskRepository.list_results", lambda self, company_id: [])

    result = EnterpriseRuntimeService().build_readiness(db=None, company_id=enterprise.id)

    assert result["empty_reason"] == "no_sync_run"
    assert result["last_sync_diagnostics"] is None
