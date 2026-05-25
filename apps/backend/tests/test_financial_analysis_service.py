from __future__ import annotations

from types import SimpleNamespace

from app.services.financial_analysis_service import FinancialAnalysisService


def _financial(indicator_code: str, value: float, year: int = 2025) -> SimpleNamespace:
    return SimpleNamespace(
        report_year=year,
        report_quarter=None,
        period_type="annual",
        report_period=f"{year}1231",
        indicator_code=indicator_code,
        value=value,
    )


def test_structured_key_metrics_injects_eight_akshare_metrics():
    metrics = FinancialAnalysisService()._structured_key_metrics(
        [
            _financial("revenue", 1200.0),
            _financial("revenue", 1000.0, year=2024),
            _financial("gross_margin", 30.0),
            _financial("net_margin", 12.0),
            _financial("ar_turnover", 4.0),
            _financial("inventory_turnover", 5.0),
            _financial("debt_ratio", 55.0),
            _financial("expense_ratio", 11.0),
        ]
    )

    codes = {metric["metric_code"] for metric in metrics}

    assert codes == {
        "revenue_growth",
        "gross_margin",
        "net_margin",
        "revenue",
        "ar_turnover",
        "inventory_turnover",
        "debt_ratio",
        "expense_ratio",
    }
    assert next(metric for metric in metrics if metric["metric_code"] == "revenue_growth")["metric_value"] == 20.0
    assert all(metric["document_id"] is None for metric in metrics)
    assert all(metric["document_name"] == "AkShare结构化财报" for metric in metrics)

