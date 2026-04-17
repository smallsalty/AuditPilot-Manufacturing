from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.config import settings
from app.providers.audit.akshare_fast_provider import AkshareFastProvider
from app.providers.financial.base import BaseFinancialProvider


class AkshareFinancialProvider(BaseFinancialProvider):
    provider_name = "akshare"

    ANALYSIS_INDICATOR_MAPPING = {
        "营业总收入": ("revenue", "营业收入", "million_cny"),
        "净利润": ("net_profit", "净利润", "million_cny"),
        "经营活动产生的现金流量净额": ("operating_cash_flow", "经营现金流", "million_cny"),
        "应收账款": ("accounts_receivable", "应收账款", "million_cny"),
        "存货": ("inventory", "存货", "million_cny"),
        "销售毛利率": ("gross_margin", "毛利率", "pct"),
        "存货周转率": ("inventory_turnover", "存货周转率", "ratio"),
        "应收账款周转率": ("ar_turnover", "应收账款周转率", "ratio"),
        "资产负债率": ("debt_ratio", "资产负债率", "pct"),
        "期间费用率": ("expense_ratio", "期间费用率", "pct"),
    }
    TAX_PROFIT_MAPPING = {
        "TOTAL_PROFIT": ("total_profit", "利润总额"),
        "INCOME_TAX": ("income_tax_expense", "所得税费用"),
        "OPERATE_TAX_ADD": ("operate_tax_surcharge", "税金及附加"),
    }
    TAX_CASHFLOW_MAPPING = {
        "PAY_ALL_TAX": ("pay_all_tax_cash", "支付各项税费的现金"),
        "DEFER_TAX": ("deferred_tax_cash_adjustment", "递延所得税调整"),
    }
    TAX_BALANCE_MAPPING = {
        "DEFER_TAX_ASSET": ("deferred_tax_asset", "递延所得税资产"),
        "DEFER_TAX_LIAB": ("deferred_tax_liability", "递延所得税负债"),
        "TAX_PAYABLE": ("tax_payable", "应交税费"),
        "TOTAL_ASSETS": ("total_assets", "资产总计"),
    }

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

        raw_payload = profile.get("raw_payload") or {}
        base_symbol = str(raw_payload.get("symbol") or "").strip()
        exchange_symbol = self._exchange_symbol(ticker=ticker, base_symbol=base_symbol)
        company_name = str(profile.get("name") or "").strip()

        rows: list[dict[str, Any]] = []
        rows.extend(self._fetch_analysis_indicator_rows(ak, ticker, base_symbol, company_name, include_quarterly))
        rows.extend(self._fetch_tax_report_rows(ak, ticker, exchange_symbol, include_quarterly))
        return self._dedupe_rows(rows, include_quarterly=include_quarterly)

    def _fetch_analysis_indicator_rows(
        self,
        ak_module: Any,
        ticker: str,
        base_symbol: str,
        company_name: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        candidates = [value for value in [base_symbol, company_name] if value]
        df = None
        for candidate in candidates:
            try:
                df = ak_module.stock_financial_analysis_indicator(symbol=candidate)
                if df is not None and not df.empty:
                    break
            except Exception:
                df = None
        if df is None or df.empty:
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = next((column for column in normalized.columns if "日期" in column or column.lower() == "date"), None)
        if not date_column:
            return []

        rows: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            period_meta = self._build_period_meta(record.get(date_column), include_quarterly=include_quarterly)
            if not period_meta:
                continue
            for source_name, (indicator_code, indicator_name, unit) in self.ANALYSIS_INDICATOR_MAPPING.items():
                if source_name not in normalized.columns:
                    continue
                value = self._coerce_number(record.get(source_name))
                if value is None:
                    continue
                rows.append(
                    {
                        "ticker": ticker.upper(),
                        **period_meta,
                        "indicator_code": indicator_code,
                        "indicator_name": indicator_name,
                        "value": value,
                        "unit": unit,
                        "source": self.provider_name,
                    }
                )
        return rows

    def _fetch_tax_report_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol:
            return []

        datasets = [
            (ak_module.stock_profit_sheet_by_report_em, self.TAX_PROFIT_MAPPING),
            (ak_module.stock_cash_flow_sheet_by_report_em, self.TAX_CASHFLOW_MAPPING),
            (ak_module.stock_balance_sheet_by_report_em, self.TAX_BALANCE_MAPPING),
        ]

        rows: list[dict[str, Any]] = []
        for fetcher, mapping in datasets:
            try:
                df = fetcher(symbol=exchange_symbol)
            except Exception:
                continue
            if df is None or df.empty:
                continue

            normalized = df.copy()
            normalized.columns = [str(column).strip() for column in normalized.columns]
            date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME", "REPORT_DATE_NAME"])
            if not date_column:
                continue
            type_column = self._first_existing_column(normalized, ["REPORT_TYPE", "REPORT_TYPE_NAME"])

            for _, record in normalized.iterrows():
                period_meta = self._build_period_meta(
                    record.get(date_column),
                    report_type=record.get(type_column) if type_column else None,
                    include_quarterly=include_quarterly,
                )
                if not period_meta:
                    continue
                for source_name, (indicator_code, indicator_name) in mapping.items():
                    if source_name not in normalized.columns:
                        continue
                    value = self._coerce_number(record.get(source_name))
                    if value is None:
                        continue
                    rows.append(
                        {
                            "ticker": ticker.upper(),
                            **period_meta,
                            "indicator_code": indicator_code,
                            "indicator_name": indicator_name,
                            "value": value,
                            "unit": "cny",
                            "source": self.provider_name,
                        }
                    )
        return rows

    def _dedupe_rows(self, rows: list[dict[str, Any]], *, include_quarterly: bool) -> list[dict[str, Any]]:
        deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            if not include_quarterly and row["period_type"] != "annual":
                continue
            key = (row["report_period"], row["period_type"], row["indicator_code"])
            deduped[key] = row
        return list(deduped.values())

    def _build_period_meta(
        self,
        raw_period: Any,
        *,
        report_type: Any = None,
        include_quarterly: bool = True,
    ) -> dict[str, Any] | None:
        timestamp = self._to_timestamp(raw_period)
        if timestamp is None:
            return None

        month = int(timestamp.month)
        quarter = max(1, min(4, (month - 1) // 3 + 1))
        period_type = "annual" if month == 12 else "quarterly"
        if not include_quarterly and period_type != "annual":
            return None

        report_type_text = str(report_type or "").strip()
        if report_type_text and "年报" in report_type_text:
            period_type = "annual"

        return {
            "period_type": period_type,
            "report_period": timestamp.strftime("%Y%m%d"),
            "report_year": int(timestamp.year),
            "report_quarter": None if period_type == "annual" else quarter,
        }

    def _exchange_symbol(self, *, ticker: str, base_symbol: str) -> str:
        normalized = str(ticker or "").strip().upper()
        if normalized.endswith(".SH"):
            return f"SH{normalized.split('.', 1)[0]}"
        if normalized.endswith(".SZ"):
            return f"SZ{normalized.split('.', 1)[0]}"
        if base_symbol.startswith("6"):
            return f"SH{base_symbol}"
        if base_symbol:
            return f"SZ{base_symbol}"
        return ""

    @staticmethod
    def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        return None

    @staticmethod
    def _to_timestamp(value: Any) -> pd.Timestamp | None:
        if value is None:
            return None
        try:
            timestamp = pd.to_datetime(value)
        except Exception:
            return None
        if pd.isna(timestamp):
            return None
        return timestamp

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text or text.lower() == "nan":
            return None
        try:
            return float(text)
        except ValueError:
            return None
