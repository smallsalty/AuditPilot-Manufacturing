from __future__ import annotations

from app.services.financial_data_risk_service import FinancialDataRiskService


def _industry_metric(
    *,
    available: bool = True,
    company_value: float | None = 0.0,
    leader_benchmark: float | None = 0.0,
    gap: float | None = 0.0,
    gap_pct: float | None = 0.0,
    sample_count: int = 12,
) -> dict:
    return {
        "company_value": company_value,
        "leader_benchmark": leader_benchmark,
        "gap": gap,
        "gap_pct": gap_pct,
        "available": available,
        "sample_count": sample_count,
        "unavailable_reason": None if available else "insufficient_sample",
    }


def _industry_comparison(**overrides: dict) -> dict:
    payload = {
        "status": "ready",
        "industry_code": "BK0001",
        "industry_name": "制造业",
        "source": "eastmoney_yjbb",
        "period": "2025FY",
        "metrics": {
            "gross_margin": _industry_metric(company_value=32.0, leader_benchmark=22.0, gap=10.0),
            "ar_turnover": _industry_metric(company_value=2.2, leader_benchmark=4.0, gap=-1.8, gap_pct=-0.45),
            "debt_ratio": _industry_metric(company_value=62.0, leader_benchmark=58.0, gap=4.0),
            "expense_ratio": _industry_metric(company_value=9.0, leader_benchmark=10.0, gap=-1.0),
        },
    }
    payload.update(overrides)
    return payload


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


def test_industry_deviation_risk_triggers_when_two_metrics_hit():
    service = FinancialDataRiskService()

    risks = service.evaluate_rows([], industry_comparison=_industry_comparison())
    industry_risk = next(risk for risk in risks if risk["rule_code"] == "FIN_DATA_INDUSTRY_DEVIATION")

    assert industry_risk["risk_name"] == "行业对比偏离"
    assert industry_risk["risk_score"] == 78.0
    assert "毛利率高于龙头基准" in industry_risk["evidence"]
    assert "应收账款周转率低于龙头基准" in industry_risk["evidence"]
    assert "龙头基准 22.00" in industry_risk["evidence"]


def test_industry_deviation_risk_scores_88_when_three_metrics_hit():
    service = FinancialDataRiskService()

    risks = service.evaluate_rows(
        [],
        industry_comparison=_industry_comparison(
            metrics={
                **_industry_comparison()["metrics"],
                "debt_ratio": _industry_metric(company_value=72.0, leader_benchmark=58.0, gap=14.0),
            },
        ),
    )
    industry_risk = next(risk for risk in risks if risk["rule_code"] == "FIN_DATA_INDUSTRY_DEVIATION")

    assert industry_risk["risk_score"] == 88.0
    assert "资产负债率高于龙头基准" in industry_risk["evidence"]


def test_industry_deviation_risk_ignores_unavailable_metrics():
    service = FinancialDataRiskService()
    unavailable = _industry_metric(available=False, company_value=None, leader_benchmark=None, gap=None, gap_pct=None, sample_count=2)

    risks = service.evaluate_rows(
        [],
        industry_comparison=_industry_comparison(
            metrics={
                **_industry_comparison()["metrics"],
                "gross_margin": unavailable,
                "ar_turnover": unavailable,
                "debt_ratio": unavailable,
            },
        ),
    )

    assert "FIN_DATA_INDUSTRY_DEVIATION" not in {risk["rule_code"] for risk in risks}
