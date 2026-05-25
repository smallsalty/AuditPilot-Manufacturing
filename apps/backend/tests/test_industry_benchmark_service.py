from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import CompanyIndustryMapping, IndustryBenchmarkSnapshot
from app.models.base import Base
from app.services.industry_benchmark_service import IndustryBenchmarkService


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _financial(indicator_code: str, value: float, year: int = 2025) -> SimpleNamespace:
    return SimpleNamespace(
        period_type="annual",
        report_period=f"{year}1231",
        report_year=year,
        report_quarter=None,
        indicator_code=indicator_code,
        value=value,
    )


def _enterprise() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        name="半导体设备企业",
        ticker="300001.SZ",
        industry_tag="制造业",
        sub_industry="半导体设备",
        portrait={"industry_code": "semiconductor_equipment", "industry_name": "半导体设备"},
    )


def _snapshot(metric: str, *, industry_name: str = "专用设备", level: str = "secondary", sample_count: int = 12, period: str = "2025FY", median: float = 20.0):
    return IndustryBenchmarkSnapshot(
        industry_code=f"{level}:{industry_name}",
        industry_name=industry_name,
        industry_level=level,
        original_industry="半导体设备",
        fallback_used=industry_name != "半导体设备",
        period=period,
        metric=metric,
        mean=median + 1.0 if sample_count >= 5 else None,
        median=median if sample_count >= 5 else None,
        p25=median - 2.0 if sample_count >= 5 else None,
        p75=median + 2.0 if sample_count >= 5 else None,
        sample_count=sample_count,
        confidence="limited" if sample_count >= 10 else ("cautious" if sample_count >= 5 else "unavailable"),
        period_aligned=period == "2025FY",
        actual_peer_period_range=[period],
        aggregation_method="weighted_ratio",
        source="akshare_snapshot",
    )


def test_build_comparison_uses_cached_hierarchy_fallback_per_metric():
    db = _session()
    db.add(_snapshot("gross_margin", industry_name="专用设备", level="secondary", sample_count=18, median=25.0))
    db.add(_snapshot("expense_ratio", industry_name="半导体设备", level="tertiary", sample_count=3, median=9.0))
    db.commit()

    comparison = IndustryBenchmarkService().build_comparison(
        db,
        _enterprise(),
        [
            _financial("gross_margin", 32.0),
            _financial("expense_ratio", 8.0),
        ],
    )

    assert comparison["reference_industry_name"] == "专用设备"
    assert comparison["industry_level"] == "secondary"
    assert comparison["fallback_used"] is True
    assert comparison["cache_state"] == "partial_hit"
    assert comparison["gross_margin"]["available"] is True
    assert comparison["gross_margin"]["industry_median"] == pytest.approx(25.0)
    assert comparison["gross_margin"]["gap"] == pytest.approx(7.0)
    assert comparison["expense_ratio"]["available"] is False
    assert comparison["expense_ratio"]["unavailable_reason"] == "insufficient_sample"
    assert comparison["expense_ratio"]["sample_count"] == 3


def test_build_comparison_allows_recent_snapshot_period_mismatch():
    db = _session()
    snapshot = _snapshot("ar_turnover", period="2024FY", median=4.5)
    snapshot.period_aligned = False
    snapshot.actual_peer_period_range = ["2024FY", "2025FY"]
    db.add(snapshot)
    db.commit()

    comparison = IndustryBenchmarkService().build_comparison(
        db,
        _enterprise(),
        [_financial("ar_turnover", 3.0), _financial("revenue", 1200.0), _financial("revenue", 1000.0, year=2024)],
    )

    assert comparison["ar_turnover"]["available"] is True
    assert comparison["ar_turnover"]["period"] == "2024FY"
    assert comparison["ar_turnover"]["period_aligned"] is False
    assert comparison["ar_turnover"]["actual_peer_period_range"] == ["2024FY", "2025FY"]


def test_build_comparison_derives_revenue_growth_without_requiring_other_metrics():
    db = _session()
    db.add(_snapshot("revenue_growth", sample_count=10, median=15.0))
    db.commit()

    comparison = IndustryBenchmarkService().build_comparison(
        db,
        _enterprise(),
        [_financial("revenue", 1200.0), _financial("revenue", 1000.0, year=2024)],
    )

    assert comparison["revenue_growth"]["available"] is True
    assert comparison["revenue_growth"]["company_value"] == pytest.approx(20.0)
    assert comparison["gross_margin"]["available"] is False
    assert comparison["gross_margin"]["unavailable_reason"] == "cache_missing"


def test_build_comparison_prefers_company_industry_mapping_snapshots():
    db = _session()
    db.add(
        CompanyIndustryMapping(
            ticker="300001",
            company_name="半导体设备企业",
            source="eastmoney_board",
            standard="东方财富行业",
            industry_code="BK1033",
            industry_name="电池",
            industry_level="board",
        )
    )
    db.add(_snapshot("gross_margin", industry_name="电池", level="board", sample_count=12, median=30.0))
    db.commit()

    comparison = IndustryBenchmarkService().build_comparison(
        db,
        _enterprise(),
        [_financial("gross_margin", 36.0)],
    )

    assert comparison["reference_industry_name"] == "电池"
    assert comparison["industry_level"] == "board"
    assert comparison["gross_margin"]["available"] is True
    assert comparison["gross_margin"]["industry_median"] == pytest.approx(30.0)
