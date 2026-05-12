from __future__ import annotations

from types import SimpleNamespace

from app.services.financial_report_service import FinancialReportService


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
    ]

    rows = service._build_rows(financials, set())
    data_risks = service.data_risk_service.evaluate_rows(rows)

    assert rows[0]["fixed_assets"] == 100.0
    assert rows[0]["ocf"] == 10.0
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
