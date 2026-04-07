from typing import Any

import pandas as pd

from app.core.config import settings
from app.providers.financial.base import BaseFinancialProvider
from app.providers.financial.mock_provider import MockFinancialProvider


class AkshareFinancialProvider(BaseFinancialProvider):
    provider_name = "akshare"

    def __init__(self) -> None:
        self._fallback = MockFinancialProvider()

    def fetch_financials(self, ticker: str, include_quarterly: bool = True) -> list[dict[str, Any]]:
        if not settings.akshare_enable:
            return self._fallback.fetch_financials(ticker, include_quarterly)
        try:
            import akshare as ak
        except Exception:
            return self._fallback.fetch_financials(ticker, include_quarterly)

        try:
            symbol = ticker.split(".")[0]
            stock_name = "三一重工" if symbol == "600031" else symbol
            annual = self._fetch_mockable_stock_data(ak, stock_name, "年度", "annual")
            quarterly = self._fetch_mockable_stock_data(ak, stock_name, "季度", "quarterly") if include_quarterly else []
            rows = annual + quarterly
            if not rows:
                return self._fallback.fetch_financials(ticker, include_quarterly)
            return rows
        except Exception:
            return self._fallback.fetch_financials(ticker, include_quarterly)

    def _fetch_mockable_stock_data(
        self,
        ak_module: Any,
        stock_name: str,
        indicator: str,
        period_type: str,
    ) -> list[dict[str, Any]]:
        try:
            df = ak_module.stock_financial_analysis_indicator(symbol=stock_name)
        except Exception:
            return []
        if df is None or df.empty:
            return []
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        if "日期" not in df.columns:
            return []

        mapping = {
            "营业总收入": ("revenue", "营业收入"),
            "净利润": ("net_profit", "净利润"),
            "经营活动产生的现金流量净额": ("operating_cash_flow", "经营现金流"),
            "应收账款": ("accounts_receivable", "应收账款"),
            "存货": ("inventory", "存货"),
            "销售毛利率": ("gross_margin", "毛利率"),
            "存货周转率": ("inventory_turnover", "存货周转率"),
            "应收账款周转率": ("ar_turnover", "应收账款周转率"),
            "资产负债率": ("debt_ratio", "资产负债率"),
            "期间费用率": ("expense_ratio", "期间费用率"),
        }
        rows: list[dict[str, Any]] = []
        for _, row in df.head(12).iterrows():
            report_period = str(row.get("日期", "")).strip()
            if not report_period:
                continue
            report_year = int(report_period[:4])
            report_quarter = None
            if period_type == "quarterly" and len(report_period) >= 7:
                month = int(report_period[5:7])
                report_quarter = max(1, min(4, month // 3))
            for source_name, (indicator_code, indicator_name) in mapping.items():
                value = row.get(source_name)
                if value is None or pd.isna(value):
                    continue
                rows.append(
                    {
                        "ticker": "600031.SH",
                        "period_type": period_type,
                        "report_period": report_period.replace("-", ""),
                        "report_year": report_year,
                        "report_quarter": report_quarter,
                        "indicator_code": indicator_code,
                        "indicator_name": indicator_name,
                        "value": float(str(value).replace("%", "")),
                        "unit": "pct" if "率" in source_name else "million_cny",
                        "source": "akshare",
                    }
                )
        return rows

