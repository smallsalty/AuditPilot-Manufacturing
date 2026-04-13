from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.config import settings
from app.providers.audit.base import BaseAuditProvider


class AkshareFastProvider(BaseAuditProvider):
    provider_name = "akshare_fast"
    priority = 50
    is_official_source = False

    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        return self.resolve_company_profile(ticker=ticker)

    def resolve_company_profile(
        self,
        ticker: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        if not settings.akshare_enable:
            return None
        try:
            import akshare as ak
        except Exception:
            return None

        match = self._resolve_symbol(ak, ticker=ticker, name=name)
        if not match:
            return None

        symbol = match["symbol"]
        exchange = "SSE" if match["ticker"].endswith(".SH") else "SZSE"

        try:
            info_df = ak.stock_individual_info_em(symbol=symbol)
        except Exception:
            info_df = None

        mapping: dict[str, Any] = {}
        if info_df is not None and not info_df.empty:
            info_df = info_df.copy()
            info_df.columns = [str(column).strip() for column in info_df.columns]
            item_column = next(
                (column for column in info_df.columns if "item" in column.lower() or "\u9879\u76ee" in column),
                None,
            )
            value_column = next(
                (column for column in info_df.columns if "value" in column.lower() or "\u503c" in column),
                None,
            )
            if item_column and value_column:
                mapping = {
                    str(row[item_column]).strip(): row[value_column]
                    for _, row in info_df.iterrows()
                    if str(row.get(item_column, "")).strip()
                }

        aliases = [value for value in [match["name"], symbol, match["ticker"]] if value]
        return {
            "name": match["name"],
            "ticker": match["ticker"],
            "exchange": exchange,
            "province": self._pick(mapping, ["\u5730\u57df", "\u6240\u5728\u5730", "\u6240\u5c5e\u5730\u533a"]),
            "industry_tag": self._pick(mapping, ["\u884c\u4e1a", "\u6240\u5c5e\u884c\u4e1a"]) or "\u5236\u9020\u4e1a",
            "listed_date": self._normalize_date(self._pick(mapping, ["\u4e0a\u5e02\u65f6\u95f4", "\u4e0a\u5e02\u65e5\u671f"])),
            "company_name_aliases": aliases,
            "source_url": "https://akshare.akfamily.xyz/",
            "source_object_id": match["ticker"],
            "raw_payload": {
                "ticker": match["ticker"],
                "symbol": symbol,
                "name": match["name"],
                "akshare_profile": mapping,
            },
        }

    def fetch_announcements(self, ticker: str, date_from, date_to) -> list[dict[str, Any]]:
        return []

    def _resolve_symbol(self, ak_module: Any, ticker: str | None, name: str | None) -> dict[str, str] | None:
        query = (ticker or name or "").strip()
        if not query:
            return None

        try:
            code_name_df = ak_module.stock_info_a_code_name()
        except Exception:
            return None
        if code_name_df is None or code_name_df.empty:
            return None

        code_name_df = code_name_df.copy()
        code_name_df.columns = [str(column).strip() for column in code_name_df.columns]
        code_col = next((column for column in code_name_df.columns if column.lower() in {"code", "\u4ee3\u7801"}), None)
        name_col = next((column for column in code_name_df.columns if column.lower() in {"name", "\u540d\u79f0"}), None)
        if code_col is None or name_col is None:
            return None

        normalized_query = self._normalize_query(query)
        code_name_df["_code"] = code_name_df[code_col].astype(str).str.strip()
        code_name_df["_name"] = code_name_df[name_col].astype(str).str.strip()
        code_name_df["_name_norm"] = code_name_df["_name"].str.replace(" ", "", regex=False).str.upper()

        symbol = self._normalize_code(normalized_query)
        exact_code = code_name_df[code_name_df["_code"] == symbol]
        if exact_code.empty and ticker:
            exact_code = code_name_df[code_name_df["_code"] == self._normalize_code(ticker)]
        if exact_code.empty:
            exact_code = code_name_df[code_name_df["_name_norm"] == normalized_query]
        if exact_code.empty:
            exact_code = code_name_df[code_name_df["_name_norm"].str.contains(normalized_query, na=False)]
        if exact_code.empty:
            return None

        row = exact_code.iloc[0]
        raw_symbol = str(row["_code"]).strip()
        return {
            "symbol": raw_symbol,
            "ticker": f"{raw_symbol}.SH" if raw_symbol.startswith("6") else f"{raw_symbol}.SZ",
            "name": str(row["_name"]).strip(),
        }

    @staticmethod
    def _normalize_query(value: str) -> str:
        return value.replace(" ", "").upper()

    @staticmethod
    def _normalize_code(value: str) -> str:
        normalized = value.replace(" ", "").upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]
        normalized = normalized.replace("SH", "").replace("SZ", "")
        return normalized

    @staticmethod
    def _pick(mapping: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = mapping.get(key)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            text = str(value).strip()
            if text and text.lower() != "nan":
                return text
        return None

    @staticmethod
    def _normalize_date(value: str | None) -> str | None:
        if not value:
            return None
        raw = value.strip().replace("/", "-").replace(".", "-")
        digits = "".join(char for char in raw if char.isdigit())
        if len(digits) == 8:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
        if len(raw) == 10 and raw.count("-") == 2:
            return raw
        return None
