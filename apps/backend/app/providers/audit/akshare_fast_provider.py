from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.audit.base import BaseAuditProvider


class AkshareFastProvider(BaseAuditProvider):
    provider_name = "akshare_fast"
    priority = 50
    is_official_source = False

    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        if not settings.akshare_enable:
            return None
        try:
            import akshare as ak
        except Exception:
            return None

        symbol = ticker.split(".")[0]
        exchange = "SSE" if ticker.upper().endswith(".SH") else "SZSE"

        try:
            info_df = ak.stock_individual_info_em(symbol=symbol)
        except Exception:
            info_df = None

        if info_df is None or info_df.empty:
            return {
                "ticker": ticker,
                "exchange": exchange,
                "source_url": "https://akshare.akfamily.xyz/",
                "source_object_id": ticker,
                "raw_payload": {"ticker": ticker},
            }

        info_df = info_df.copy()
        info_df.columns = [str(column).strip() for column in info_df.columns]
        item_column = next((column for column in info_df.columns if "item" in column.lower() or "项目" in column), None)
        value_column = next((column for column in info_df.columns if "value" in column.lower() or "value" == column.lower() or "值" in column), None)
        if item_column is None or value_column is None:
            return {
                "ticker": ticker,
                "exchange": exchange,
                "source_url": "https://akshare.akfamily.xyz/",
                "source_object_id": ticker,
                "raw_payload": info_df.to_dict(orient="records"),
            }

        mapping = {
            str(row[item_column]).strip(): row[value_column]
            for _, row in info_df.iterrows()
            if str(row.get(item_column, "")).strip()
        }

        return {
            "name": self._pick(mapping, ["股票简称", "简称"]),
            "ticker": ticker,
            "exchange": exchange,
            "province": self._pick(mapping, ["地域", "所在地域"]),
            "industry_tag": self._pick(mapping, ["行业", "所属行业"]) or "Manufacturing",
            "listed_date": self._normalize_date(self._pick(mapping, ["上市时间", "上市日期"])),
            "company_name_aliases": [value for value in [self._pick(mapping, ["股票简称", "简称"]), symbol, ticker] if value],
            "source_url": "https://akshare.akfamily.xyz/",
            "source_object_id": ticker,
            "raw_payload": mapping,
        }

    def fetch_announcements(self, ticker: str, date_from, date_to) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def _pick(mapping: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = mapping.get(key)
            if value is None:
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
