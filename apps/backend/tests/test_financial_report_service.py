from __future__ import annotations

from types import SimpleNamespace

from app.schemas.enterprise import FinancialReportPayload
from app.services.financial_report_service import FinancialReportService


def _industry_metric(
    *,
    available: bool = True,
    company_value: float | None = 0.0,
    industry_mean: float | None = 0.0,
    gap: float | None = 0.0,
    gap_pct: float | None = 0.0,
    sample_count: int = 12,
) -> dict:
    return {
        "company_value": company_value,
        "industry_mean": industry_mean,
        "industry_median": industry_mean,
        "p25": industry_mean - 1 if industry_mean is not None else None,
        "p75": industry_mean + 1 if industry_mean is not None else None,
        "gap": gap,
        "gap_pct": gap_pct,
        "zscore": None,
        "percentile": None,
        "available": available,
        "sample_count": sample_count,
        "confidence": "limited",
        "source": "peer_financials",
        "unavailable_reason": None if available else "insufficient_sample",
        "distribution_available": False,
        "metric": None,
        "period": "2025FY",
        "actual_peer_period_range": ["2025FY"],
        "period_aligned": True,
    }


def _industry_comparison() -> dict:
    return {
        "industry_code": "manufacturing",
        "industry_name": "制造业",
        "industry_source": "mapping",
        "latest_year": 2025,
        "reference_industry_name": "制造业",
        "industry_level": "manufacturing",
        "fallback_used": False,
        "original_industry": "制造业",
        "cache_state": "hit",
        "cache_updated_at": None,
        "revenue_growth": _industry_metric(company_value=12.0, industry_mean=8.0, gap=4.0),
        "gross_margin": _industry_metric(company_value=32.0, industry_mean=22.0, gap=10.0),
        "net_margin": _industry_metric(company_value=12.0, industry_mean=8.0, gap=4.0),
        "revenue": _industry_metric(company_value=1200.0, industry_mean=900.0, gap=300.0, gap_pct=0.33),
        "ar_turnover": _industry_metric(company_value=2.2, industry_mean=4.0, gap=-1.8, gap_pct=-0.45),
        "inventory_turnover": _industry_metric(company_value=3.4, industry_mean=4.4, gap=-1.0, gap_pct=-0.22),
        "debt_ratio": _industry_metric(company_value=62.0, industry_mean=58.0, gap=4.0),
        "expense_ratio": _industry_metric(company_value=9.0, industry_mean=10.0, gap=-1.0),
    }


def test_row_sort_key_orders_quarters_before_fiscal_year():
    service = FinancialReportService()
    rows = [
        {"year": 2025, "quarter": "FY"},
        {"year": 2025, "quarter": "Q4"},
        {"year": 2025, "quarter": "Q2"},
        {"year": 2025, "quarter": "Q1"},
        {"year": 2025, "quarter": "Q3"},
    ]

    sorted_rows = sorted(rows, key=service._row_sort_key)

    assert [row["quarter"] for row in sorted_rows] == ["Q1", "Q2", "Q3", "Q4", "FY"]


def test_build_rows_includes_fixed_assets_and_data_risk_payload_fields():
    service = FinancialReportService()
    financials = [
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="fixed_assets", value=100.0),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="operating_cash_flow", value=10.0),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="profit_cash_content", value=0.5),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="ar_turnover", value=2.0),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="inventory_turnover", value=3.0),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="interest_bearing_debt_ratio", value=12.0),
    ]

    rows = service._build_rows(financials, set())
    data_risks = service.data_risk_service.evaluate_rows(rows)

    assert rows[0]["fixed_assets"] == 100.0
    assert rows[0]["ocf"] == 10.0
    assert rows[0]["profit_cash_content"] == 0.5
    assert rows[0]["ar_turnover"] == 2.0
    assert rows[0]["inventory_turnover"] == 3.0
    assert rows[0]["interest_bearing_debt_ratio"] == 12.0
    assert data_risks == []


def test_revenue_qoq_uses_previous_quarter_not_fiscal_year_for_q1():
    service = FinancialReportService()
    financials = [
        SimpleNamespace(report_year=2024, report_quarter=4, period_type="quarterly", report_period="20241231", indicator_code="revenue", value=100.0),
        SimpleNamespace(report_year=2024, report_quarter=None, period_type="annual", report_period="20241231", indicator_code="revenue", value=1000.0),
        SimpleNamespace(report_year=2025, report_quarter=1, period_type="quarterly", report_period="20250331", indicator_code="revenue", value=120.0),
    ]

    rows = {row["report_period"]: row for row in service._build_rows(financials, set())}

    assert rows["2025Q1"]["revenue_qoq"] == 20.0


def test_revenue_qoq_for_fiscal_year_uses_previous_fiscal_year():
    service = FinancialReportService()
    financials = [
        SimpleNamespace(report_year=2024, report_quarter=None, period_type="annual", report_period="20241231", indicator_code="revenue", value=1000.0),
        SimpleNamespace(report_year=2025, report_quarter=None, period_type="annual", report_period="20251231", indicator_code="revenue", value=1100.0),
    ]

    rows = {row["report_period"]: row for row in service._build_rows(financials, set())}

    assert rows["2025FY"]["revenue_qoq"] == 10.0


def test_latest_metrics_includes_new_derived_fields():
    service = FinancialReportService()

    snapshot = service._build_latest_metrics(
        {
            "report_period": "2025Q1",
            "profit_cash_content": 1.25,
            "interest_bearing_debt_ratio": 18.5,
        }
    )

    assert snapshot["profit_cash_content"] == 1.25
    assert snapshot["interest_bearing_debt_ratio"] == 18.5


def test_build_report_includes_industry_comparison_and_data_risk():
    comparison = _industry_comparison()
    enterprise = SimpleNamespace(id=6, name="测试制造", ticker="300000.SZ", report_year=2025)
    financials = [
        SimpleNamespace(
            report_year=2025,
            report_quarter=None,
            period_type="annual",
            report_period="20251231",
            indicator_code="gross_margin",
            value=32.0,
            created_at=None,
            updated_at=None,
        ),
        SimpleNamespace(
            report_year=2025,
            report_quarter=None,
            period_type="annual",
            report_period="20251231",
            indicator_code="debt_ratio",
            value=62.0,
            created_at=None,
            updated_at=None,
        ),
        SimpleNamespace(
            report_year=2025,
            report_quarter=None,
            period_type="annual",
            report_period="20251231",
            indicator_code="expense_ratio",
            value=9.0,
            created_at=None,
            updated_at=None,
        ),
    ]

    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def get_by_id(self, enterprise_id):
            return enterprise if enterprise_id == enterprise.id else None

        def get_financials(self, enterprise_id, official_only=False):
            return financials

        def get_documents(self, enterprise_id, official_only=False):
            return []

    service = FinancialReportService()
    service.enterprise_repo = FakeRepo
    service.industry_benchmark_service = SimpleNamespace(build_comparison=lambda db, item, rows: comparison)

    payload = service.build_report(SimpleNamespace(), enterprise.id)
    codes = {risk["rule_code"] for risk in payload["data_risks"]}
    validated = FinancialReportPayload.model_validate(payload)

    assert payload["industry_comparison"] == comparison
    assert validated.industry_comparison.industry_name == "制造业"
    assert validated.industry_comparison.expense_ratio.company_value == 9.0
    assert "FIN_DATA_INDUSTRY_DEVIATION" in codes
