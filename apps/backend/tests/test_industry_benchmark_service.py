from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import EnterpriseProfile, IndustryBenchmarkRefreshState, IndustryLeaderBenchmark, IndustryLeaderCompany
from app.models.base import Base
from app.services.industry_benchmark_service import IndustryBenchmarkService


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _financial(code: str, value: float, *, year: int = 2026, quarter: int = 1):
    return SimpleNamespace(
        period_type="quarterly",
        report_period=f"{year}0331",
        report_year=year,
        report_quarter=quarter,
        indicator_code=code,
        value=value,
    )


def _enterprise(db):
    enterprise = EnterpriseProfile(name="宁德时代", ticker="300750.SZ", report_year=2026, industry_tag="制造业", exchange="SZSE")
    db.add(enterprise)
    db.commit()
    db.refresh(enterprise)
    return enterprise


def _ready_rows(db, enterprise_id: int, *, status: str = "ready", period: str = "2026Q1"):
    db.add(
        IndustryBenchmarkRefreshState(
            enterprise_id=enterprise_id,
            ticker="300750",
            period=period,
            industry_name="电池",
            board_code="BK1033",
            source="eastmoney_yjbb",
            status=status,
            board_validation_status="verified",
            error_reason=None if status == "ready" else "insufficient_leader_sample",
            refreshed_at=datetime.now(timezone.utc),
        )
    )
    db.add(IndustryLeaderCompany(industry_name="电池", period=period, rank=1, ticker="300014", company_name="亿纬锂能", metrics_json={}, source="eastmoney_yjbb"))
    db.add(IndustryLeaderBenchmark(industry_name="电池", period=period, metric_code="gross_margin", leader_benchmark=24.0, sample_count=5, source="eastmoney_yjbb"))
    db.commit()


def test_build_comparison_reads_only_ready_current_period():
    db = _session()
    try:
        enterprise = _enterprise(db)
        _ready_rows(db, enterprise.id)
        comparison = IndustryBenchmarkService().build_comparison(db, enterprise, [_financial("gross_margin", 32.0)])

        assert comparison["status"] == "ready"
        assert comparison["industry_name"] == "电池"
        assert comparison["source"] == "eastmoney_yjbb"
        assert comparison["leader_companies"] == [{"rank": 1, "ticker": "300014", "name": "亿纬锂能"}]
        assert comparison["metrics"]["gross_margin"]["leader_benchmark"] == pytest.approx(24.0)
        assert comparison["metrics"]["gross_margin"]["gap"] == pytest.approx(8.0)
    finally:
        db.close()


def test_build_comparison_hides_failed_refresh_and_old_period():
    for status, period in (("failed", "2026Q1"), ("ready", "2025Q1")):
        db = _session()
        try:
            enterprise = _enterprise(db)
            _ready_rows(db, enterprise.id, status=status, period=period)
            comparison = IndustryBenchmarkService().build_comparison(db, enterprise, [_financial("gross_margin", 32.0)])

            assert comparison["status"] in {"error", "missing"}
            assert comparison["metrics"]["gross_margin"]["available"] is False
            assert comparison["metrics"]["gross_margin"]["leader_benchmark"] is None
        finally:
            db.close()


def test_build_comparison_derives_company_revenue_growth():
    db = _session()
    try:
        enterprise = _enterprise(db)
        _ready_rows(db, enterprise.id)
        db.add(IndustryLeaderBenchmark(industry_name="电池", period="2026Q1", metric_code="revenue_growth", leader_benchmark=10.0, sample_count=5, source="eastmoney_yjbb"))
        db.commit()

        comparison = IndustryBenchmarkService().build_comparison(
            db,
            enterprise,
            [_financial("revenue", 120.0), _financial("revenue", 100.0, year=2025)],
        )

        assert comparison["metrics"]["revenue_growth"]["company_value"] == pytest.approx(20.0)
        assert comparison["metrics"]["revenue_growth"]["gap"] == pytest.approx(10.0)
    finally:
        db.close()
