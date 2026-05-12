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
                        "销售毛利率": "24.41%",
                        "销售净利率": "17.55%",
                        "资产负债率": "64.74%",
                        "净资产收益率": "5.49%",
                    },
                    {
                        "报告期": "2025-12-31",
                        "销售毛利率": "28.21%",
                        "销售净利率": "19.30%",
                        "资产负债率": "61.94%",
                        "净资产收益率": "7.15%",
                    },
                ]
            )

        @staticmethod
        def stock_profit_sheet_by_report_em(symbol: str):
            return pd.DataFrame()

        @staticmethod
        def stock_cash_flow_sheet_by_report_em(symbol: str):
            return pd.DataFrame()

        @staticmethod
        def stock_balance_sheet_by_report_em(symbol: str):
            return pd.DataFrame()

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
    assert quarterly["gross_margin"]["value"] == 24.41
    assert quarterly["net_margin"]["value"] == 17.55
    assert quarterly["debt_ratio"]["value"] == 64.74
    assert quarterly["roe"]["value"] == 5.49
    assert quarter_four["gross_margin"]["report_quarter"] == 4
    assert quarter_four["gross_margin"]["value"] == 28.21
