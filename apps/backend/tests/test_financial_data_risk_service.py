from __future__ import annotations

from app.services.financial_data_risk_service import FinancialDataRiskService


def test_financial_data_risk_service_flags_recent_quarter_risks():
    service = FinancialDataRiskService()
    rows = [
        {
            "year": 2025,
            "quarter": "Q1",
            "report_period": "2025Q1",
            "revenue": 100.0,
            "revenue_qoq": None,
            "net_profit": 20.0,
            "gross_margin": 30.0,
            "net_margin": 12.0,
            "debt_ratio": 50.0,
            "ocf": 18.0,
            "fixed_assets": 100.0,
        },
        {
            "year": 2025,
            "quarter": "Q2",
            "report_period": "2025Q2",
            "revenue": 135.0,
            "revenue_qoq": 35.0,
            "net_profit": 22.0,
            "gross_margin": 28.0,
            "net_margin": 11.0,
            "debt_ratio": 52.0,
            "ocf": 15.0,
            "fixed_assets": 103.0,
        },
        {
            "year": 2025,
            "quarter": "Q3",
            "report_period": "2025Q3",
            "revenue": 120.0,
            "revenue_qoq": -11.11,
            "net_profit": 21.0,
            "gross_margin": 27.0,
            "net_margin": 10.0,
            "debt_ratio": 54.0,
            "ocf": 8.0,
            "fixed_assets": 112.0,
        },
        {
            "year": 2025,
            "quarter": "Q4",
            "report_period": "2025Q4",
            "revenue": 118.0,
            "revenue_qoq": -1.67,
            "net_profit": 19.0,
            "gross_margin": 24.0,
            "net_margin": 8.0,
            "debt_ratio": 55.0,
            "ocf": -2.0,
            "fixed_assets": 118.0,
        },
    ]

    risks = service.evaluate_rows(rows)
    codes = {risk["rule_code"] for risk in risks}

    assert "FIN_DATA_REVENUE_VOLATILITY" in codes
    assert "FIN_DATA_PROFIT_CASH_MISMATCH" in codes
    assert "FIN_DATA_FIXED_ASSET_VOLATILITY" in codes
    assert service.max_score(risks) >= 75.0
    assert all(risk["evidence"] for risk in risks)
