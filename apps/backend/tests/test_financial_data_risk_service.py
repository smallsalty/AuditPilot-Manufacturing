from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.feature_engineering_service import FeatureEngineeringService
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


def test_profit_cash_mismatch_prefers_derived_content_and_falls_back_to_aggregate_ratio():
    service = FinancialDataRiskService()
    rows = [
        {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "net_profit": 100.0, "ocf": 100.0, "profit_cash_content": 0.5},
        {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "net_profit": 100.0, "ocf": 100.0, "profit_cash_content": 1.0},
    ]

    derived_risk = service._profit_cash_mismatch(rows)
    aggregate_risk = service._profit_cash_mismatch(
        [
            {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "net_profit": 100.0, "ocf": 50.0},
            {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "net_profit": 100.0, "ocf": 50.0},
        ]
    )

    assert derived_risk is not None
    assert "净利润现金含量为 0.50" in derived_risk["evidence"]
    assert aggregate_risk is not None
    assert "近4季经营现金流/净利为 0.50" in aggregate_risk["evidence"]


@pytest.mark.parametrize(
    ("rows", "rule_code"),
    [
        (
            [
                {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "net_profit": 100.0, "deduct_net_profit": 100.0},
                {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "net_profit": 100.0, "deduct_net_profit": 70.0},
            ],
            "FIN_DATA_DEDUCT_PROFIT_DEPENDENCE",
        ),
        (
            [
                {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "ar_turnover": 10.0},
                {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "ar_turnover": 7.0},
            ],
            "FIN_DATA_AR_TURNOVER_DECLINE",
        ),
        (
            [
                {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "inventory_turnover": 10.0},
                {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "inventory_turnover": 7.0},
            ],
            "FIN_DATA_INVENTORY_TURNOVER_DECLINE",
        ),
        (
            [
                {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "interest_bearing_debt_ratio": 20.0},
                {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "interest_bearing_debt_ratio": 30.0},
            ],
            "FIN_DATA_INTEREST_DEBT_PRESSURE",
        ),
        (
            [
                {"year": 2025, "quarter": "Q1", "report_period": "2025Q1", "expense_ratio": 6.0},
                {"year": 2025, "quarter": "Q2", "report_period": "2025Q2", "expense_ratio": 9.0},
            ],
            "FIN_DATA_EXPENSE_RATIO_INCREASE",
        ),
    ],
)
def test_current_company_rules_trigger_at_stable_thresholds(rows: list[dict], rule_code: str):
    codes = {risk["rule_code"] for risk in FinancialDataRiskService().evaluate_rows(rows)}

    assert rule_code in codes


def test_current_company_rules_do_not_trigger_inside_stable_thresholds():
    rows = [
        {
            "year": 2025,
            "quarter": "Q1",
            "report_period": "2025Q1",
            "net_profit": 100.0,
            "deduct_net_profit": 100.0,
            "ar_turnover": 10.0,
            "inventory_turnover": 10.0,
            "interest_bearing_debt_ratio": 20.0,
            "expense_ratio": 6.0,
        },
        {
            "year": 2025,
            "quarter": "Q2",
            "report_period": "2025Q2",
            "net_profit": 100.0,
            "deduct_net_profit": 80.0,
            "ar_turnover": 7.01,
            "inventory_turnover": 7.01,
            "interest_bearing_debt_ratio": 24.99,
            "expense_ratio": 8.99,
        },
    ]

    codes = {risk["rule_code"] for risk in FinancialDataRiskService().evaluate_rows(rows)}

    assert "FIN_DATA_DEDUCT_PROFIT_DEPENDENCE" not in codes
    assert "FIN_DATA_AR_TURNOVER_DECLINE" not in codes
    assert "FIN_DATA_INVENTORY_TURNOVER_DECLINE" not in codes
    assert "FIN_DATA_INTEREST_DEBT_PRESSURE" not in codes
    assert "FIN_DATA_EXPENSE_RATIO_INCREASE" not in codes


def test_evaluate_indicators_normalizes_new_financial_fields():
    financials = [
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=1, report_period="20250331", indicator_code="net_profit", value=100.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=1, report_period="20250331", indicator_code="deduct_net_profit", value=100.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=1, report_period="20250331", indicator_code="expense_ratio", value=6.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=1, report_period="20250331", indicator_code="roe", value=5.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=2, report_period="20250630", indicator_code="net_profit", value=100.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=2, report_period="20250630", indicator_code="deduct_net_profit", value=70.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=2, report_period="20250630", indicator_code="expense_ratio", value=9.0),
        SimpleNamespace(period_type="quarterly", report_year=2025, report_quarter=2, report_period="20250630", indicator_code="roe", value=4.0),
    ]

    codes = {risk["rule_code"] for risk in FinancialDataRiskService().evaluate_indicators(financials)}

    assert "FIN_DATA_DEDUCT_PROFIT_DEPENDENCE" in codes
    assert "FIN_DATA_EXPENSE_RATIO_INCREASE" in codes


@pytest.mark.parametrize(
    ("metric_name", "metric", "expected_text"),
    [
        ("revenue_growth", _industry_metric(company_value=10.0, leader_benchmark=35.0, gap=-25.0), "营收增长率低于龙头基准"),
        ("gross_margin", _industry_metric(company_value=14.0, leader_benchmark=22.0, gap=-8.0), "毛利率低于龙头基准"),
        ("net_margin", _industry_metric(company_value=14.0, leader_benchmark=8.0, gap=6.0), "净利率高于龙头基准"),
        ("net_margin", _industry_metric(company_value=3.0, leader_benchmark=8.0, gap=-5.0), "净利率低于龙头基准"),
        ("inventory_turnover", _industry_metric(company_value=2.8, leader_benchmark=4.0, gap=-1.2, gap_pct=-0.30), "存货周转率低于龙头基准"),
        ("debt_ratio", _industry_metric(company_value=70.0, leader_benchmark=58.0, gap=12.0), "资产负债率高于龙头基准"),
        ("expense_ratio", _industry_metric(company_value=13.0, leader_benchmark=10.0, gap=3.0), "期间费用率高于龙头基准"),
    ],
)
def test_industry_deviation_supports_extended_leader_metrics(metric_name: str, metric: dict, expected_text: str):
    metrics = {
        "ar_turnover": _industry_metric(company_value=2.2, leader_benchmark=4.0, gap=-1.8, gap_pct=-0.45),
        metric_name: metric,
    }

    risks = FinancialDataRiskService().evaluate_rows([], industry_comparison=_industry_comparison(metrics=metrics))
    industry_risk = next(risk for risk in risks if risk["rule_code"] == "FIN_DATA_INDUSTRY_DEVIATION")

    assert expected_text in industry_risk["evidence"]
    assert "2025FY" in industry_risk["evidence"]


def test_industry_deviation_does_not_treat_revenue_scale_as_risk():
    comparison = _industry_comparison(
        metrics={
            "revenue": _industry_metric(company_value=1000.0, leader_benchmark=100.0, gap=900.0, gap_pct=9.0),
        }
    )

    codes = {risk["rule_code"] for risk in FinancialDataRiskService().evaluate_rows([], industry_comparison=comparison)}

    assert "FIN_DATA_INDUSTRY_DEVIATION" not in codes


def test_feature_engineering_keeps_all_leader_metric_snapshots():
    comparison = _industry_comparison(
        metrics={
            "revenue_growth": _industry_metric(company_value=10.0, leader_benchmark=8.0, gap=2.0),
            "gross_margin": _industry_metric(company_value=20.0, leader_benchmark=18.0, gap=2.0),
            "net_margin": _industry_metric(company_value=8.0, leader_benchmark=7.0, gap=1.0),
            "revenue": _industry_metric(company_value=1000.0, leader_benchmark=900.0, gap=100.0),
            "ar_turnover": _industry_metric(company_value=3.0, leader_benchmark=4.0, gap=-1.0, gap_pct=-0.25),
            "inventory_turnover": _industry_metric(company_value=3.0, leader_benchmark=4.0, gap=-1.0, gap_pct=-0.25),
            "debt_ratio": _industry_metric(company_value=50.0, leader_benchmark=55.0, gap=-5.0),
            "expense_ratio": _industry_metric(company_value=8.0, leader_benchmark=9.0, gap=-1.0),
        }
    )
    features: dict = {}

    FeatureEngineeringService()._merge_industry_comparison(features, comparison)

    assert features["industry_benchmark_available"] == 1.0
    assert features["revenue_growth_available"] == 1.0
    assert features["inventory_turnover_leader_benchmark"] == 4.0
    assert features["expense_ratio_gap"] == -1.0
