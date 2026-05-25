from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import enterprises as enterprise_routes


def test_refresh_industry_benchmarks_route_uses_latest_financial_period(monkeypatch):
    calls: dict[str, object] = {}
    enterprise = SimpleNamespace(id=6, report_year=2024)
    financials = [
        SimpleNamespace(period_type="annual", report_year=2024, report_quarter=None, report_period="20241231"),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=3, report_period="20250930"),
    ]

    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def get_by_id(self, enterprise_id):
            return enterprise if enterprise_id == enterprise.id else None

        def get_financials(self, enterprise_id, official_only=False):
            return financials

    class FakeRefreshService:
        def refresh(self, db, *, enterprise_ids, period):
            calls["enterprise_ids"] = enterprise_ids
            calls["period"] = period
            return {"snapshot_count": 8, "failures": []}

    class FakeReportService:
        def build_report(self, db, enterprise_id, *, refresh, include_quarterly):
            calls["report_args"] = {
                "enterprise_id": enterprise_id,
                "refresh": refresh,
                "include_quarterly": include_quarterly,
            }
            return {"enterprise_id": enterprise_id, "industry_comparison": {"cache_state": "hit"}}

    monkeypatch.setattr(enterprise_routes, "EnterpriseRepository", FakeRepo)
    monkeypatch.setattr(enterprise_routes, "IndustryBenchmarkRefreshService", FakeRefreshService)
    monkeypatch.setattr(enterprise_routes, "FinancialReportService", FakeReportService)

    payload = enterprise_routes.refresh_industry_benchmarks(enterprise.id, SimpleNamespace())

    assert payload["enterprise_id"] == enterprise.id
    assert calls["enterprise_ids"] == [enterprise.id]
    assert calls["period"] == "2025Q3"
    assert calls["report_args"] == {
        "enterprise_id": enterprise.id,
        "refresh": False,
        "include_quarterly": True,
    }


def test_latest_financial_period_label_falls_back_to_enterprise_report_year():
    assert enterprise_routes._latest_financial_period_label([], 2024) == "2024FY"


def test_refresh_industry_benchmarks_route_degrades_when_provider_network_fails(monkeypatch):
    enterprise = SimpleNamespace(id=6, report_year=2024)

    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def get_by_id(self, enterprise_id):
            return enterprise if enterprise_id == enterprise.id else None

        def get_financials(self, enterprise_id, official_only=False):
            return []

    class FakeRefreshService:
        def refresh(self, db, *, enterprise_ids, period):
            return {
                "snapshot_count": 0,
                "failures": [{"error": "industry_board_load_failed"}],
            }

    class FakeReportService:
        def build_report(self, db, enterprise_id, *, refresh, include_quarterly):
            return {
                "enterprise_id": enterprise_id,
                "industry_comparison": {
                    "cache_state": "missing",
                    "reference_industry_name": "专用设备",
                },
            }

    monkeypatch.setattr(enterprise_routes, "EnterpriseRepository", FakeRepo)
    monkeypatch.setattr(enterprise_routes, "IndustryBenchmarkRefreshService", FakeRefreshService)
    monkeypatch.setattr(enterprise_routes, "FinancialReportService", FakeReportService)

    payload = enterprise_routes.refresh_industry_benchmarks(enterprise.id, SimpleNamespace())

    assert payload["enterprise_id"] == enterprise.id
    assert payload["industry_comparison"]["cache_state"] == "missing"


def test_refresh_industry_benchmarks_route_keeps_404_for_missing_enterprise(monkeypatch):
    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def get_by_id(self, enterprise_id):
            return None

    monkeypatch.setattr(enterprise_routes, "EnterpriseRepository", FakeRepo)

    with pytest.raises(HTTPException) as exc_info:
        enterprise_routes.refresh_industry_benchmarks(999, SimpleNamespace())

    assert exc_info.value.status_code == 404
