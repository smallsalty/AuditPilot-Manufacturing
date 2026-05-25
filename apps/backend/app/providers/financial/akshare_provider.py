from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.config import settings
from app.providers.audit.akshare_fast_provider import AkshareFastProvider
from app.providers.financial.base import BaseFinancialProvider


class AkshareFinancialProvider(BaseFinancialProvider):
    provider_name = "akshare"

    EM_ANALYSIS_INDICATOR_MAPPING = (
        {"columns": ("TOTALOPERATEREVE",), "indicator_code": "revenue", "indicator_name": "营业收入", "unit": "cny"},
        {"columns": ("TOTALOPERATEREVETZ", "TOTAL_OPERATE_REVE_TZ"), "indicator_code": "revenue_growth", "indicator_name": "营业收入增长率", "unit": "pct"},
        {"columns": ("PARENTNETPROFIT",), "indicator_code": "net_profit", "indicator_name": "归母净利润", "unit": "cny"},
        {"columns": ("DEDU_PARENT_PROFIT",), "indicator_code": "deduct_net_profit", "indicator_name": "扣非净利润", "unit": "cny"},
        {"columns": ("GROSS_PROFIT_RATIO", "XSMLL", "销售毛利率"), "indicator_code": "gross_margin", "indicator_name": "毛利率", "unit": "pct"},
        {"columns": ("NET_PROFIT_RATIO", "XSJLL", "销售净利率"), "indicator_code": "net_margin", "indicator_name": "净利率", "unit": "pct"},
        {"columns": ("ROE_DILUTED", "JROE", "净资产收益率"), "indicator_code": "roe", "indicator_name": "ROE", "unit": "pct"},
        {"columns": ("EPSJB", "BASIC_EPS", "基本每股收益"), "indicator_code": "eps", "indicator_name": "EPS", "unit": "cny_per_share"},
        {"columns": ("YSZKZZL", "应收账款周转率"), "indicator_code": "ar_turnover", "indicator_name": "应收账款周转率", "unit": "ratio"},
        {"columns": ("ZCFZL", "DEBT_ASSET_RATIO", "资产负债率"), "indicator_code": "debt_ratio", "indicator_name": "资产负债率", "unit": "pct"},
    )
    ANALYSIS_INDICATOR_MAPPING = (
        {"aliases": ("营业总收入", "营业收入"), "indicator_code": "revenue", "indicator_name": "营业收入", "unit": "million_cny"},
        {"aliases": ("营业收入同比增长率(%)", "营业总收入同比增长率(%)", "营业收入增长率"), "indicator_code": "revenue_growth", "indicator_name": "营业收入增长率", "unit": "pct"},
        {"aliases": ("归属于母公司股东的净利润", "归母净利润", "净利润"), "indicator_code": "net_profit", "indicator_name": "归母净利润", "unit": "million_cny"},
        {"aliases": ("扣除非经常性损益后的净利润", "扣非净利润"), "indicator_code": "deduct_net_profit", "indicator_name": "扣非净利润", "unit": "million_cny"},
        {"aliases": ("经营活动产生的现金流量净额",), "indicator_code": "operating_cash_flow", "indicator_name": "经营现金流", "unit": "million_cny"},
        {"aliases": ("应收账款",), "indicator_code": "accounts_receivable", "indicator_name": "应收账款", "unit": "million_cny"},
        {"aliases": ("存货",), "indicator_code": "inventory", "indicator_name": "存货", "unit": "million_cny"},
        {"aliases": ("销售毛利率(%)", "销售毛利率", "毛利率"), "indicator_code": "gross_margin", "indicator_name": "毛利率", "unit": "pct"},
        {"aliases": ("销售净利率(%)", "销售净利率", "净利率"), "indicator_code": "net_margin", "indicator_name": "净利率", "unit": "pct"},
        {"aliases": ("净资产收益率(%)", "净资产收益率", "净资产收益率-摊薄", "加权净资产收益率(%)", "加权净资产收益率"), "indicator_code": "roe", "indicator_name": "ROE", "unit": "pct"},
        {"aliases": ("基本每股收益", "每股收益", "摊薄每股收益", "摊薄每股收益(元)", "加权每股收益(元)"), "indicator_code": "eps", "indicator_name": "EPS", "unit": "cny_per_share"},
        {"aliases": ("存货周转率(次)", "存货周转率"), "indicator_code": "inventory_turnover", "indicator_name": "存货周转率", "unit": "ratio"},
        {"aliases": ("应收账款周转率(次)", "应收账款周转率"), "indicator_code": "ar_turnover", "indicator_name": "应收账款周转率", "unit": "ratio"},
        {"aliases": ("资产负债率(%)", "资产负债率"), "indicator_code": "debt_ratio", "indicator_name": "资产负债率", "unit": "pct"},
        {"aliases": ("期间费用率", "三项费用比重"), "indicator_code": "expense_ratio", "indicator_name": "期间费用率", "unit": "pct"},
    )
    THS_INDICATOR_MAPPING = (
        {"aliases": ("营业总收入",), "indicator_code": "revenue", "indicator_name": "营业收入", "unit": "cny"},
        {"aliases": ("营业总收入同比增长率", "营业收入同比增长率"), "indicator_code": "revenue_growth", "indicator_name": "营业收入增长率", "unit": "pct"},
        {"aliases": ("净利润",), "indicator_code": "net_profit", "indicator_name": "归母净利润", "unit": "cny"},
        {"aliases": ("扣非净利润",), "indicator_code": "deduct_net_profit", "indicator_name": "扣非净利润", "unit": "cny"},
        {"aliases": ("销售毛利率", "毛利率"), "indicator_code": "gross_margin", "indicator_name": "毛利率", "unit": "pct"},
        {"aliases": ("销售净利率", "净利率"), "indicator_code": "net_margin", "indicator_name": "净利率", "unit": "pct"},
        {"aliases": ("资产负债率",), "indicator_code": "debt_ratio", "indicator_name": "资产负债率", "unit": "pct"},
        {"aliases": ("净资产收益率", "净资产收益率-摊薄"), "indicator_code": "roe", "indicator_name": "ROE", "unit": "pct"},
        {"aliases": ("基本每股收益",), "indicator_code": "eps", "indicator_name": "EPS", "unit": "cny_per_share"},
        {"aliases": ("应收账款周转率",), "indicator_code": "ar_turnover", "indicator_name": "应收账款周转率", "unit": "ratio"},
        {"aliases": ("存货周转率",), "indicator_code": "inventory_turnover", "indicator_name": "存货周转率", "unit": "ratio"},
    )
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
        raw_payload = (profile or {}).get("raw_payload") or {}
        base_symbol = str(raw_payload.get("symbol") or self._ticker_symbol(ticker)).strip()
        if not base_symbol:
            return []
        exchange_symbol = self._exchange_symbol(ticker=ticker, base_symbol=base_symbol)
        company_name = str((profile or {}).get("name") or "").strip()

        rows: list[dict[str, Any]] = []
        rows.extend(self._fetch_em_analysis_indicator_rows(ak, ticker, exchange_symbol, include_quarterly))
        rows.extend(self._fetch_analysis_indicator_rows(ak, ticker, base_symbol, company_name, include_quarterly))
        rows.extend(self._fetch_ths_abstract_rows(ak, ticker, base_symbol, include_quarterly))
        rows.extend(self._fetch_tax_report_rows(ak, ticker, exchange_symbol, include_quarterly))
        rows.extend(self._fetch_operating_cash_flow_rows(ak, ticker, exchange_symbol, include_quarterly))
        rows.extend(self._fetch_fixed_asset_rows(ak, ticker, exchange_symbol, include_quarterly))
        rows.extend(self._fetch_expense_ratio_rows(ak, ticker, exchange_symbol, include_quarterly))
        rows.extend(self._fetch_turnover_rows(ak, ticker, exchange_symbol, include_quarterly))
        return self._dedupe_rows(rows, include_quarterly=include_quarterly)

    def _fetch_em_analysis_indicator_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol or not hasattr(ak_module, "stock_financial_analysis_indicator_em"):
            return []

        symbol = f"{exchange_symbol[2:]}.{exchange_symbol[:2]}" if exchange_symbol[:2] in {"SH", "SZ"} else exchange_symbol
        try:
            df = ak_module.stock_financial_analysis_indicator_em(symbol=symbol, indicator="按报告期")
        except Exception:
            return []
        if df is None or df.empty:
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "日期", "报告期"])
        if not date_column:
            return []

        rows: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            period_meta = self._build_period_meta(record.get(date_column), include_quarterly=include_quarterly)
            if not period_meta:
                continue
            for indicator_meta in self.EM_ANALYSIS_INDICATOR_MAPPING:
                source_name = self._first_existing_column(normalized, list(indicator_meta["columns"]))
                if not source_name:
                    continue
                value = self._coerce_number(record.get(source_name))
                if value is None:
                    continue
                rows.append(
                    {
                        "ticker": ticker.upper(),
                        **period_meta,
                        "indicator_code": indicator_meta["indicator_code"],
                        "indicator_name": indicator_meta["indicator_name"],
                        "value": value,
                        "unit": indicator_meta["unit"],
                        "source": self.provider_name,
                    }
                )
        return rows

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
            for indicator_meta in self.ANALYSIS_INDICATOR_MAPPING:
                source_name = self._first_existing_column(normalized, list(indicator_meta["aliases"]))
                if not source_name:
                    continue
                value = self._coerce_number(record.get(source_name))
                if value is None:
                    continue
                rows.append(
                    {
                        "ticker": ticker.upper(),
                        **period_meta,
                        "indicator_code": indicator_meta["indicator_code"],
                        "indicator_name": indicator_meta["indicator_name"],
                        "value": value,
                        "unit": indicator_meta["unit"],
                        "source": self.provider_name,
                    }
                )
        return rows

    def _fetch_ths_abstract_rows(
        self,
        ak_module: Any,
        ticker: str,
        base_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not base_symbol:
            return []

        datasets = [("按年度", "annual")]
        if include_quarterly:
            datasets.append(("按单季度", "quarterly"))

        rows: list[dict[str, Any]] = []
        for indicator, period_type in datasets:
            try:
                df = ak_module.stock_financial_abstract_ths(symbol=base_symbol, indicator=indicator)
            except Exception:
                continue
            if df is None or df.empty:
                continue

            normalized = df.copy()
            normalized.columns = [str(column).strip() for column in normalized.columns]
            date_column = self._first_existing_column(normalized, ["报告期"])
            if not date_column:
                continue

            for _, record in normalized.iterrows():
                period_meta = self._build_ths_period_meta(record.get(date_column), period_type=period_type)
                if not period_meta:
                    continue
                for indicator_meta in self.THS_INDICATOR_MAPPING:
                    source_name = self._first_existing_column(normalized, list(indicator_meta["aliases"]))
                    if not source_name:
                        continue
                    value = self._coerce_number(record.get(source_name))
                    if value is None:
                        continue
                    rows.append(
                        {
                            "ticker": ticker.upper(),
                            **period_meta,
                            "indicator_code": indicator_meta["indicator_code"],
                            "indicator_name": indicator_meta["indicator_name"],
                            "value": value,
                            "unit": indicator_meta["unit"],
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

    def _fetch_operating_cash_flow_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol:
            return []
        try:
            df = ak_module.stock_cash_flow_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return []
        if df is None or df.empty:
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME"])
        if not date_column or "NETCASH_OPERATE" not in normalized.columns:
            return []

        cumulative: dict[int, dict[int, tuple[str, float]]] = {}
        annual_rows: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            timestamp = self._to_timestamp(record.get(date_column))
            value = self._coerce_number(record.get("NETCASH_OPERATE"))
            if timestamp is None or value is None:
                continue
            quarter = max(1, min(4, (int(timestamp.month) - 1) // 3 + 1))
            year = int(timestamp.year)
            report_period = timestamp.strftime("%Y%m%d")
            cumulative.setdefault(year, {})[quarter] = (report_period, value)
            if quarter == 4:
                annual_rows.append(
                    self._financial_row(
                        ticker=ticker,
                        period_type="annual",
                        report_period=report_period,
                        report_year=year,
                        report_quarter=None,
                        indicator_code="operating_cash_flow",
                        indicator_name="经营现金流",
                        value=value,
                        unit="cny",
                    )
                )

        quarterly_rows: list[dict[str, Any]] = []
        if include_quarterly:
            for year, periods in cumulative.items():
                previous_value = 0.0
                for quarter in range(1, 5):
                    item = periods.get(quarter)
                    if item is None:
                        continue
                    report_period, cumulative_value = item
                    quarterly_rows.append(
                        self._financial_row(
                            ticker=ticker,
                            period_type="quarterly",
                            report_period=report_period,
                            report_year=year,
                            report_quarter=quarter,
                            indicator_code="operating_cash_flow",
                            indicator_name="经营现金流",
                            value=cumulative_value - previous_value,
                            unit="cny",
                        )
                    )
                    previous_value = cumulative_value

        return [*annual_rows, *quarterly_rows]

    def _fetch_fixed_asset_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol:
            return []
        try:
            df = ak_module.stock_balance_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return []
        if df is None or df.empty:
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME"])
        if not date_column or "FIXED_ASSET" not in normalized.columns:
            return []

        rows: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            timestamp = self._to_timestamp(record.get(date_column))
            value = self._coerce_number(record.get("FIXED_ASSET"))
            if timestamp is None or value is None:
                continue
            quarter = max(1, min(4, (int(timestamp.month) - 1) // 3 + 1))
            year = int(timestamp.year)
            report_period = timestamp.strftime("%Y%m%d")
            if quarter == 4:
                rows.append(
                    self._financial_row(
                        ticker=ticker,
                        period_type="annual",
                        report_period=report_period,
                        report_year=year,
                        report_quarter=None,
                        indicator_code="fixed_assets",
                        indicator_name="固定资产",
                        value=value,
                        unit="cny",
                    )
                )
            if include_quarterly:
                rows.append(
                    self._financial_row(
                        ticker=ticker,
                        period_type="quarterly",
                        report_period=report_period,
                        report_year=year,
                        report_quarter=quarter,
                        indicator_code="fixed_assets",
                        indicator_name="固定资产",
                        value=value,
                        unit="cny",
                    )
                )
        return rows

    def _fetch_expense_ratio_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol:
            return []
        try:
            df = ak_module.stock_profit_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return []
        if df is None or df.empty:
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME"])
        if not date_column:
            return []
        type_column = self._first_existing_column(normalized, ["REPORT_TYPE", "REPORT_TYPE_NAME"])

        rows: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            period_meta = self._build_period_meta(
                record.get(date_column),
                report_type=record.get(type_column) if type_column else None,
                include_quarterly=include_quarterly,
            )
            if not period_meta:
                continue
            value = self._expense_ratio_from_profit_record(record)
            if value is None:
                continue
            rows.append(
                self._financial_row(
                    ticker=ticker,
                    **period_meta,
                    indicator_code="expense_ratio",
                    indicator_name="期间费用率",
                    value=value,
                    unit="pct",
                )
            )
        return rows

    def _fetch_turnover_rows(
        self,
        ak_module: Any,
        ticker: str,
        exchange_symbol: str,
        include_quarterly: bool,
    ) -> list[dict[str, Any]]:
        if not exchange_symbol:
            return []
        try:
            profit_df = ak_module.stock_profit_sheet_by_report_em(symbol=exchange_symbol)
            balance_df = ak_module.stock_balance_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return []
        if profit_df is None or getattr(profit_df, "empty", True) or balance_df is None or getattr(balance_df, "empty", True):
            return []

        profit = profit_df.copy()
        profit.columns = [str(column).strip() for column in profit.columns]
        balance = balance_df.copy()
        balance.columns = [str(column).strip() for column in balance.columns]
        profit_date_column = self._first_existing_column(profit, ["REPORT_DATE", "REPORT_DATE_NAME"])
        balance_date_column = self._first_existing_column(balance, ["REPORT_DATE", "REPORT_DATE_NAME"])
        if not profit_date_column or not balance_date_column:
            return []

        balance_records = self._balance_records_by_period(balance, balance_date_column)
        rows: list[dict[str, Any]] = []
        type_column = self._first_existing_column(profit, ["REPORT_TYPE", "REPORT_TYPE_NAME"])
        for _, record in profit.iterrows():
            period_meta = self._build_period_meta(
                record.get(profit_date_column),
                report_type=record.get(type_column) if type_column else None,
                include_quarterly=include_quarterly,
            )
            if not period_meta:
                continue
            report_period = period_meta["report_period"]
            revenue = self._first_number(record, ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME"])
            cost = self._first_number(record, ["OPERATE_COST", "TOTAL_OPERATE_COST"])
            current_balance = balance_records.get(report_period)
            previous_balance = self._previous_balance_record(balance_records, report_period)
            if current_balance is None:
                continue

            ar_turnover = self._turnover_value(
                numerator=revenue,
                current_balance=self._first_number(current_balance, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"]),
                previous_balance=self._first_number(previous_balance, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"]) if previous_balance is not None else None,
            )
            if ar_turnover is not None:
                rows.append(
                    self._financial_row(
                        ticker=ticker,
                        **period_meta,
                        indicator_code="ar_turnover",
                        indicator_name="应收账款周转率",
                        value=ar_turnover,
                        unit="ratio",
                    )
                )

            inventory_turnover = self._turnover_value(
                numerator=cost,
                current_balance=self._first_number(current_balance, ["INVENTORY"]),
                previous_balance=self._first_number(previous_balance, ["INVENTORY"]) if previous_balance is not None else None,
            )
            if inventory_turnover is not None:
                rows.append(
                    self._financial_row(
                        ticker=ticker,
                        **period_meta,
                        indicator_code="inventory_turnover",
                        indicator_name="存货周转率",
                        value=inventory_turnover,
                        unit="ratio",
                    )
                )
        return rows

    def _balance_records_by_period(self, df: pd.DataFrame, date_column: str) -> dict[str, pd.Series]:
        records: dict[str, pd.Series] = {}
        for _, record in df.iterrows():
            timestamp = self._to_timestamp(record.get(date_column))
            if timestamp is None:
                continue
            records[timestamp.strftime("%Y%m%d")] = record
        return records

    def _previous_balance_record(self, records: dict[str, pd.Series], report_period: str) -> pd.Series | None:
        previous_periods = sorted(period for period in records if period < report_period)
        return records[previous_periods[-1]] if previous_periods else None

    def _turnover_value(
        self,
        *,
        numerator: float | None,
        current_balance: float | None,
        previous_balance: float | None,
    ) -> float | None:
        if numerator is None or numerator <= 0 or current_balance is None or current_balance <= 0:
            return None
        denominator = (
            (current_balance + previous_balance) / 2.0
            if previous_balance is not None and previous_balance > 0
            else current_balance
        )
        if denominator <= 0:
            return None
        return numerator / denominator

    def _expense_ratio_from_profit_record(self, record: pd.Series) -> float | None:
        revenue = self._first_number(record, ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME"])
        if revenue in (None, 0):
            return None

        sales = self._first_number(record, ["SALE_EXPENSE"])
        management = self._first_number(record, ["MANAGE_EXPENSE"])
        research = self._first_number(record, ["RESEARCH_EXPENSE", "ME_RESEARCH_EXPENSE"])
        finance = self._first_number(record, ["FINANCE_EXPENSE"])
        expenses = [value for value in (sales, management, research, finance) if value is not None]
        if not expenses:
            return None
        return (sum(expenses) / abs(revenue)) * 100.0

    def _first_number(self, record: pd.Series, candidates: list[str]) -> float | None:
        for candidate in candidates:
            if candidate not in record.index:
                continue
            value = self._coerce_number(record.get(candidate))
            if value is not None:
                return value
        return None

    def _financial_row(
        self,
        *,
        ticker: str,
        period_type: str,
        report_period: str,
        report_year: int,
        report_quarter: int | None,
        indicator_code: str,
        indicator_name: str,
        value: float,
        unit: str,
    ) -> dict[str, Any]:
        return {
            "ticker": ticker.upper(),
            "period_type": period_type,
            "report_period": report_period,
            "report_year": report_year,
            "report_quarter": report_quarter,
            "indicator_code": indicator_code,
            "indicator_name": indicator_name,
            "value": value,
            "unit": unit,
            "source": self.provider_name,
        }

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
    def _ticker_symbol(ticker: str) -> str:
        normalized = str(ticker or "").strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]
        normalized = normalized.replace("SH", "").replace("SZ", "")
        return normalized if normalized.isdigit() else ""

    def _build_ths_period_meta(self, raw_period: Any, *, period_type: str) -> dict[str, Any] | None:
        raw_text = str(raw_period or "").strip()
        if not raw_text:
            return None

        if period_type == "annual" and raw_text.isdigit() and len(raw_text) == 4:
            timestamp = self._to_timestamp(f"{raw_text}-12-31")
        else:
            timestamp = self._to_timestamp(raw_text)
        if timestamp is None:
            return None

        quarter = max(1, min(4, (int(timestamp.month) - 1) // 3 + 1))
        return {
            "period_type": period_type,
            "report_period": timestamp.strftime("%Y%m%d"),
            "report_year": int(timestamp.year),
            "report_quarter": None if period_type == "annual" else quarter,
        }

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
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "false", "--", "-"}:
            return None
        multiplier = 1.0
        if text.endswith("%"):
            text = text[:-1]
        if text.endswith("亿"):
            multiplier = 100000000.0
            text = text[:-1]
        elif text.endswith("万"):
            multiplier = 10000.0
            text = text[:-1]
        try:
            return float(text) * multiplier
        except ValueError:
            return None
