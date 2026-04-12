from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import settings
from app.providers.audit.base import BaseAuditProvider


class CninfoProvider(BaseAuditProvider):
    provider_name = "cninfo"
    priority = 100
    is_official_source = True
    stock_list_url = "https://www.cninfo.com.cn/new/data/szse_stock.json"

    DOCUMENT_KEYWORDS = ("年度报告", "年报", "审计报告", "内控审计", "审阅报告")
    PENALTY_KEYWORDS = ("处罚", "监管", "警示函", "问询函", "监管函", "纪律处分", "立案")

    def __init__(self) -> None:
        self.enabled = settings.cninfo_enable
        self.query_url = settings.cninfo_query_url
        self.static_base_url = settings.cninfo_static_base_url.rstrip("/")
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.cninfo.com.cn/",
        }

    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "ticker": ticker,
            "source_url": "https://www.cninfo.com.cn/",
            "source_object_id": ticker,
            "raw_payload": {"ticker": ticker},
        }

    def fetch_announcements(self, ticker: str, date_from: date, date_to: date) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        stock_param = self._build_stock_param(ticker)
        if not stock_param:
            raise ValueError(f"Unable to resolve cninfo stock mapping for {ticker}")

        payload = {
            "pageNum": 1,
            "pageSize": 50,
            "column": "sse" if ticker.upper().endswith(".SH") else "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": stock_param,
            "searchkey": "",
            "category": "",
            "seDate": f"{date_from.isoformat()}~{date_to.isoformat()}",
            "isHLtitle": "true",
        }
        with httpx.Client(timeout=20.0, headers=self.headers) as client:
            response = client.post(self.query_url, data=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get("announcements") or []
        total_record_num = int(data.get("totalRecordNum") or 0)
        announcements: list[dict[str, Any]] = []
        for row in rows:
            title = str(row.get("announcementTitle") or row.get("announcementTitleCn") or "").strip()
            if not title:
                continue
            document_url = self._build_document_url(row.get("adjunctUrl"))
            category = self._classify_title(title)
            announcements.append(
                {
                    "source": self.provider_name,
                    "source_object_id": str(row.get("announcementId") or "").strip() or None,
                    "title": title,
                    "announcement_date": self._normalize_announcement_time(row.get("announcementTime")),
                    "source_url": document_url or self.query_url,
                    "document_url": document_url,
                    "content_text": None,
                    "raw_payload": row,
                    "category": category,
                    "document_type": "annual_report" if category == "document" else None,
                    "event_type": "regulatory_penalty" if category == "penalty" else None,
                    "summary": title,
                    "regulator": "cninfo",
                    "diagnostics": {
                        "stock": stock_param,
                        "seDate": payload["seDate"],
                        "totalRecordNum": total_record_num,
                    },
                }
            )
        return announcements

    def _build_stock_param(self, ticker: str) -> str | None:
        code = ticker.split(".", 1)[0].strip()
        org_id = self._load_stock_mapping().get(code)
        if not org_id:
            return None
        return f"{code},{org_id}"

    def _build_document_url(self, adjunct_url: Any) -> str | None:
        value = str(adjunct_url or "").strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"{self.static_base_url}/{value.lstrip('/')}"

    def _normalize_announcement_time(self, raw_value: Any) -> str | None:
        if raw_value in (None, ""):
            return None
        try:
            return datetime.utcfromtimestamp(float(raw_value) / 1000).date().isoformat()
        except Exception:
            return None

    def _classify_title(self, title: str) -> str:
        if any(keyword in title for keyword in self.PENALTY_KEYWORDS):
            return "penalty"
        if any(keyword in title for keyword in self.DOCUMENT_KEYWORDS):
            return "document"
        return "other"

    @classmethod
    @lru_cache(maxsize=1)
    def _load_stock_mapping(cls) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Referer": "https://www.cninfo.com.cn/",
        }
        with httpx.Client(timeout=20.0, headers=headers) as client:
            response = client.get(cls.stock_list_url)
            response.raise_for_status()
            payload = response.json()
        rows = payload.get("stockList") or []
        mapping: dict[str, str] = {}
        for row in rows:
            code = str(row.get("code") or "").strip()
            org_id = str(row.get("orgId") or "").strip()
            if code and org_id:
                mapping[code] = org_id
        return mapping
