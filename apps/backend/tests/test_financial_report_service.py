from __future__ import annotations

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
