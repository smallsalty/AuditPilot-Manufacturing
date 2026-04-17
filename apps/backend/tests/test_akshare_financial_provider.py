from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from app.providers.financial.akshare_provider import AkshareFinancialProvider


def test_akshare_financial_provider_adds_tax_metrics(monkeypatch) -> None:
    provider = AkshareFinancialProvider()
    monkeypatch.setattr("app.providers.financial.akshare_provider.settings.akshare_enable", True)
    monkeypatch.setattr(
        provider._profile_provider,
        "resolve_company_profile",
        lambda ticker: {"name": "测试企业", "raw_payload": {"symbol": "600519"}},
    )

    fake_ak = SimpleNamespace(
        stock_financial_analysis_indicator=lambda symbol: pd.DataFrame(
            [
                {
                    "日期": "2024-12-31",
                    "营业总收入": 100.0,
                    "净利润": 20.0,
                }
            ]
        ),
        stock_profit_sheet_by_report_em=lambda symbol: pd.DataFrame(
            [{"REPORT_DATE": "2024-12-31", "TOTAL_PROFIT": 80.0, "INCOME_TAX": 24.0, "OPERATE_TAX_ADD": 6.0}]
        ),
        stock_cash_flow_sheet_by_report_em=lambda symbol: pd.DataFrame(
            [{"REPORT_DATE": "2024-12-31", "PAY_ALL_TAX": 18.0, "DEFER_TAX": 4.0}]
        ),
        stock_balance_sheet_by_report_em=lambda symbol: pd.DataFrame(
            [{"REPORT_DATE": "2024-12-31", "DEFER_TAX_ASSET": 12.0, "DEFER_TAX_LIAB": 3.0, "TAX_PAYABLE": 8.0, "TOTAL_ASSETS": 900.0}]
        ),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    rows = provider.fetch_financials("600519.SH")

    by_code = {row["indicator_code"]: row for row in rows}
    assert by_code["total_profit"]["unit"] == "cny"
    assert by_code["income_tax_expense"]["value"] == 24.0
    assert by_code["pay_all_tax_cash"]["value"] == 18.0
    assert by_code["deferred_tax_asset"]["value"] == 12.0
    assert by_code["total_assets"]["value"] == 900.0
    assert by_code["revenue"]["value"] == 100.0


def test_akshare_financial_provider_skips_missing_tax_columns_without_failing(monkeypatch) -> None:
    provider = AkshareFinancialProvider()
    monkeypatch.setattr("app.providers.financial.akshare_provider.settings.akshare_enable", True)
    monkeypatch.setattr(
        provider._profile_provider,
        "resolve_company_profile",
        lambda ticker: {"name": "测试企业", "raw_payload": {"symbol": "000001"}},
    )

    fake_ak = SimpleNamespace(
        stock_financial_analysis_indicator=lambda symbol: pd.DataFrame([{"日期": "2024-09-30", "营业总收入": 50.0}]),
        stock_profit_sheet_by_report_em=lambda symbol: pd.DataFrame([{"REPORT_DATE": "2024-09-30", "TOTAL_PROFIT": 10.0}]),
        stock_cash_flow_sheet_by_report_em=lambda symbol: pd.DataFrame([{"REPORT_DATE": "2024-09-30"}]),
        stock_balance_sheet_by_report_em=lambda symbol: pd.DataFrame([{"REPORT_DATE": "2024-09-30", "TOTAL_ASSETS": 300.0}]),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    rows = provider.fetch_financials("000001.SZ")

    codes = {row["indicator_code"] for row in rows}
    assert "revenue" in codes
    assert "total_profit" in codes
    assert "total_assets" in codes
    assert "pay_all_tax_cash" not in codes
