from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.core.config import settings
from app.providers.audit.base import BaseAuditProvider


class TushareFastProvider(BaseAuditProvider):
    provider_name = "tushare_fast"
    priority = 40
    is_official_source = False

    def __init__(self) -> None:
        self.base_url = settings.tushare_base_url.rstrip("/")
        self.token = settings.tushare_token
        self.enabled = settings.tushare_enable and bool(self.token)

    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        rows = self._call(
            "stock_basic",
            params={"ts_code": ticker},
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        if not rows:
            return None
        row = rows[0]
        listed_date = None
        raw_list_date = str(row.get("list_date") or "").strip()
        if len(raw_list_date) == 8 and raw_list_date.isdigit():
            listed_date = f"{raw_list_date[:4]}-{raw_list_date[4:6]}-{raw_list_date[6:]}"
        exchange = "SSE" if ticker.upper().endswith(".SH") else "SZSE"
        return {
            "name": row.get("name"),
            "ticker": row.get("ts_code") or ticker,
            "exchange": exchange,
            "province": row.get("area"),
            "industry_tag": row.get("industry") or "Manufacturing",
            "listed_date": listed_date,
            "source_url": self.base_url,
            "source_object_id": row.get("ts_code") or ticker,
            "raw_payload": row,
        }

    def fetch_announcements(self, ticker: str, date_from: date, date_to: date) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            rows = self._call(
                "anns_d",
                params={
                    "ts_code": ticker,
                    "start_date": date_from.strftime("%Y%m%d"),
                    "end_date": date_to.strftime("%Y%m%d"),
                },
                fields="ann_date,ts_code,name,title,url",
            )
        except Exception:
            return []
        announcements: list[dict[str, Any]] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            ann_date = self._normalize_tushare_date(row.get("ann_date"))
            if not title or not ann_date:
                continue
            announcements.append(
                {
                    "source": self.provider_name,
                    "source_object_id": None,
                    "title": title,
                    "announcement_date": ann_date,
                    "source_url": row.get("url"),
                    "document_url": row.get("url"),
                    "content_text": None,
                    "raw_payload": row,
                }
            )
        return announcements

    def _call(self, api_name: str, params: dict[str, Any], fields: str) -> list[dict[str, Any]]:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params,
            "fields": fields,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self.base_url, json=payload)
            response.raise_for_status()
            data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"Tushare request failed: {data.get('msg', 'unknown error')}")
        payload_data = data.get("data") or {}
        fields_list = payload_data.get("fields") or []
        items = payload_data.get("items") or []
        return [dict(zip(fields_list, item)) for item in items]

    @staticmethod
    def _normalize_tushare_date(value: Any) -> str | None:
        raw = str(value or "").strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        return None
