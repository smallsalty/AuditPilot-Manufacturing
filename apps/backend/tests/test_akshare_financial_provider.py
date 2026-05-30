from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from app.providers.financial.akshare_provider import AkshareFinancialProvider


def test_fetch_financials_uses_ths_abstract_when_analysis_indicator_is_empty(monkeypatch):
    class FakeAkshare:
        @staticmethod
        def stock_financial_analysis_indicator(symbol: str):
            return pd.DataFrame()

        @staticmethod
        def stock_financial_abstract_ths(symbol: str, indicator: str):
            if indicator == "按年度":
                return pd.DataFrame(
                    [
                        {
                            "报告期": "2025",
                            "营业总收入": "4237.02亿",
                            "营业总收入同比增长率": "15.5%",
                            "净利润": "722.01亿",
                            "扣非净利润": "607.4亿",
                            "销售毛利率": "26.27%",
                            "销售净利率": "18.12%",
                            "资产负债率": "61.94%",
                            "净资产收益率": "24.91%",
                            "基本每股收益": "14.82",
                        }
                    ]
                )
            return pd.DataFrame(
                [
                    {
                        "报告期": "2025-03-31",
                        "净利润": "40",
                        "销售毛利率": "24.41%",
                        "销售净利率": "17.55%",
                        "资产负债率": "64.74%",
                        "净资产收益率": "5.49%",
                    },
                    {
                        "报告期": "2025-12-31",
                        "净利润": "200",
                        "销售毛利率": "28.21%",
                        "销售净利率": "19.30%",
                        "资产负债率": "61.94%",
                        "净资产收益率": "7.15%",
                    },
                ]
            )

        @staticmethod
        def stock_profit_sheet_by_report_em(symbol: str):
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2025-03-31",
                        "REPORT_TYPE": "一季报",
                        "TOTAL_OPERATE_INCOME": 1000.0,
                        "OPERATE_COST": 600.0,
                        "SALE_EXPENSE": 10.0,
                        "MANAGE_EXPENSE": 20.0,
                        "RESEARCH_EXPENSE": 5.0,
                        "FINANCE_EXPENSE": 0.0,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "REPORT_TYPE": "年报",
                        "TOTAL_OPERATE_INCOME": 5000.0,
                        "OPERATE_COST": 3000.0,
                        "SALE_EXPENSE": 100.0,
                        "MANAGE_EXPENSE": 200.0,
                        "RESEARCH_EXPENSE": 50.0,
                        "FINANCE_EXPENSE": -10.0,
                    },
                ]
            )

        @staticmethod
        def stock_cash_flow_sheet_by_report_em(symbol: str):
            return pd.DataFrame(
                [
                    {"REPORT_DATE": "2025-03-31", "REPORT_TYPE": "一季报", "NETCASH_OPERATE": 100.0},
                    {"REPORT_DATE": "2025-06-30", "REPORT_TYPE": "中报", "NETCASH_OPERATE": 250.0},
                    {"REPORT_DATE": "2025-09-30", "REPORT_TYPE": "三季报", "NETCASH_OPERATE": 450.0},
                    {"REPORT_DATE": "2025-12-31", "REPORT_TYPE": "年报", "NETCASH_OPERATE": 700.0},
                ]
            )

        @staticmethod
        def stock_balance_sheet_by_report_em(symbol: str):
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2025-03-31",
                        "REPORT_TYPE": "一季报",
                        "FIXED_ASSET": 800.0,
                        "ACCOUNTS_RECE": 100.0,
                        "INVENTORY": 50.0,
                        "TOTAL_ASSETS": 1000.0,
                        "SHORT_LOAN": 100.0,
                        "LONG_LOAN": 50.0,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "REPORT_TYPE": "年报",
                        "FIXED_ASSET": 900.0,
                        "ACCOUNTS_RECE": 200.0,
                        "INVENTORY": 100.0,
                        "TOTAL_ASSETS": 2000.0,
                        "SHORT_LOAN": 100.0,
                        "NONCURRENT_LIAB_1YEAR": 20.0,
                        "LONG_LOAN": 200.0,
                        "BOND_PAYABLE": 40.0,
                        "SHORT_BOND_PAYABLE": 10.0,
                        "LEASE_LIAB": 30.0,
                    },
                ]
            )

    provider = AkshareFinancialProvider()
    provider._profile_provider = SimpleNamespace(
        resolve_company_profile=lambda ticker: {
            "name": "宁德时代",
            "raw_payload": {"symbol": "300750"},
        }
    )
    monkeypatch.setitem(sys.modules, "akshare", FakeAkshare)

    rows = provider.fetch_financials("300750.SZ", include_quarterly=True)
    annual = {
        row["indicator_code"]: row
        for row in rows
        if row["period_type"] == "annual" and row["report_period"] == "20251231"
    }
    quarterly = {
        row["indicator_code"]: row
        for row in rows
        if row["period_type"] == "quarterly" and row["report_period"] == "20250331"
    }
    quarter_four = {
        row["indicator_code"]: row
        for row in rows
        if row["period_type"] == "quarterly" and row["report_period"] == "20251231"
    }

    assert annual["gross_margin"]["value"] == 26.27
    assert annual["net_margin"]["value"] == 18.12
    assert annual["debt_ratio"]["value"] == 61.94
    assert annual["roe"]["value"] == 24.91
    assert annual["revenue"]["value"] == pytest.approx(423702000000.0)
    assert annual["revenue_growth"]["value"] == pytest.approx(15.5)
    assert annual["ar_turnover"]["value"] == pytest.approx(5000.0 / 150.0)
    assert annual["inventory_turnover"]["value"] == pytest.approx(3000.0 / 75.0)
    assert quarterly["gross_margin"]["value"] == 24.41
    assert quarterly["net_margin"]["value"] == 17.55
    assert quarterly["debt_ratio"]["value"] == 64.74
    assert quarterly["roe"]["value"] == 5.49
    assert quarterly["ar_turnover"]["value"] == pytest.approx(10.0)
    assert quarterly["inventory_turnover"]["value"] == pytest.approx(12.0)
    assert quarter_four["gross_margin"]["report_quarter"] == 4
    assert quarter_four["gross_margin"]["value"] == 28.21
    assert annual["operating_cash_flow"]["value"] == 700.0
    assert annual["fixed_assets"]["value"] == 900.0
    assert annual["expense_ratio"]["value"] == pytest.approx(6.8)
    assert annual["interest_bearing_debt_ratio"]["value"] == pytest.approx(20.0)
    assert annual["profit_cash_content"]["value"] == pytest.approx(700.0 / 72201000000.0)
    assert quarterly["operating_cash_flow"]["value"] == 100.0
    assert quarterly["fixed_assets"]["value"] == 800.0
    assert quarterly["expense_ratio"]["value"] == pytest.approx(3.5)
    assert quarterly["interest_bearing_debt_ratio"]["value"] == pytest.approx(15.0)
    assert quarterly["profit_cash_content"]["value"] == pytest.approx(100.0 / 40.0)
    assert quarter_four["operating_cash_flow"]["report_quarter"] == 4
    assert quarter_four["operating_cash_flow"]["value"] == 250.0
    assert quarter_four["fixed_assets"]["value"] == 900.0


def test_interest_bearing_debt_ratio_requires_assets_and_at_least_one_debt_field():
    provider = AkshareFinancialProvider()

    assert provider._interest_bearing_debt_ratio_from_balance_record(
        pd.Series({"TOTAL_ASSETS": 1000.0, "SHORT_LOAN": 100.0, "LEASE_LIAB": 50.0})
    ) == pytest.approx(15.0)
    assert provider._interest_bearing_debt_ratio_from_balance_record(pd.Series({"TOTAL_ASSETS": 1000.0})) is None
    assert provider._interest_bearing_debt_ratio_from_balance_record(
        pd.Series({"TOTAL_ASSETS": 0.0, "SHORT_LOAN": 100.0})
    ) is None


def test_profit_cash_content_skips_zero_net_profit():
    provider = AkshareFinancialProvider()
    base = {
        "ticker": "300750.SZ",
        "period_type": "quarterly",
        "report_period": "20250331",
        "report_year": 2025,
        "report_quarter": 1,
        "unit": "cny",
        "source": "akshare",
    }

    rows = [
        {**base, "indicator_code": "operating_cash_flow", "indicator_name": "经营现金流", "value": 100.0},
        {**base, "indicator_code": "net_profit", "indicator_name": "归母净利润", "value": 0.0},
    ]

    assert provider._derive_profit_cash_content_rows(rows) == []
