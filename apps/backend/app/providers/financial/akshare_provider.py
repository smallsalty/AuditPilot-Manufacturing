from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.config import settings
from app.providers.audit.akshare_fast_provider import AkshareFastProvider
from app.providers.financial.base import BaseFinancialProvider


class AkshareFinancialProvider(BaseFinancialProvider):
    provider_name = "akshare"

    def __init__(self) -> None:
        self._profile_provider = AkshareFastProvider()

    def fetch_financials(self, ticker: str, include_quarterly: bool = True) -> list[dict[str, Any]]:
        if not settings.akshare_enable:
            return []
        try:
            import akshare as ak
        except Exception:
            return []

        profile = self._profile_provider.resolve_company_profile(ticker=ticker)
        if not profile:
            return []

        stock_name = profile["name"]
        try:
            df = ak.stock_financial_analysis_indicator(symbol=stock_name)
        except Exception:
            return []
        if df is None or df.empty:
            return []

        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        if "日期" not in df.columns:
            return []

        indicator_mapping = {
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
            period_type = "annual"
            if len(report_period) >= 7:
                month = int(report_period[5:7])
                report_quarter = max(1, min(4, (month - 1) // 3 + 1))
                if include_quarterly:
                    period_type = "quarterly" if month in {3, 6, 9} else "annual"

            for source_name, (indicator_code, indicator_name) in indicator_mapping.items():
                value = row.get(source_name)
                if value is None or pd.isna(value):
                    continue
                rows.append(
                    {
                        "ticker": ticker.upper(),
                        "period_type": period_type,
                        "report_period": report_period.replace("-", ""),
                        "report_year": report_year,
                        "report_quarter": report_quarter if period_type == "quarterly" else None,
                        "indicator_code": indicator_code,
                        "indicator_name": indicator_name,
                        "value": float(str(value).replace("%", "")),
                        "unit": "pct" if "率" in source_name else "million_cny",
                        "source": "akshare",
                    }
                )

        if not include_quarterly:
            rows = [row for row in rows if row["period_type"] == "annual"]
        return rows
