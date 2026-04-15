from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import math
import re
import time
from typing import Any

import httpx

from app.core.config import settings
from app.providers.audit.base import BaseAuditProvider


class CninfoProvider(BaseAuditProvider):
    provider_name = "cninfo"
    priority = 100
    is_official_source = True
    stock_list_url = "https://www.cninfo.com.cn/new/data/szse_stock.json"
    max_retries = 3
    page_size = 50
    max_pages = 20

    DOCUMENT_KEYWORDS = (
        "\u5e74\u5ea6\u62a5\u544a",
        "\u5e74\u62a5",
        "\u5e74\u5ea6\u62a5\u544a\u6458\u8981",
        "\u5ba1\u8ba1\u62a5\u544a",
        "\u5185\u90e8\u63a7\u5236\u5ba1\u8ba1\u62a5\u544a",
        "\u5185\u90e8\u63a7\u5236\u8bc4\u4ef7\u62a5\u544a",
        "\u5185\u63a7\u5ba1\u8ba1\u62a5\u544a",
        "\u5185\u63a7\u8bc4\u4ef7\u62a5\u544a",
        "\u534a\u5e74\u5ea6\u62a5\u544a",
        "\u534a\u5e74\u62a5",
        "\u5b63\u5ea6\u62a5\u544a",
        "\u7b2c\u4e00\u5b63\u5ea6\u62a5\u544a",
        "\u7b2c\u4e09\u5b63\u5ea6\u62a5\u544a",
        "\u8d22\u52a1\u51b3\u7b97\u62a5\u544a",
        "\u52df\u96c6\u8d44\u91d1\u4e13\u9879\u5ba1\u6838",
        "\u975e\u7ecf\u8425\u6027\u8d44\u91d1\u5360\u7528\u4e13\u9879\u8bf4\u660e",
        "\u4e13\u9879\u5ba1\u6838\u62a5\u544a",
        "\u4e13\u9879\u5ba1\u8ba1\u62a5\u544a",
    )
    PENALTY_KEYWORDS = (
        "\u5904\u7f5a",
        "\u76d1\u7ba1",
        "\u8b66\u793a\u51fd",
        "\u95ee\u8be2\u51fd",
        "\u76d1\u7ba1\u51fd",
        "\u7eaa\u5f8b\u5904\u5206",
        "\u7acb\u6848",
    )
    ANNUAL_PACKAGE_KEYWORDS = (
        "{year}\u5e74\u5e74\u5ea6\u62a5\u544a",
        "{year}\u5e74\u5e74\u5ea6\u62a5\u544a\u6458\u8981",
        "{year}\u5e74\u5ea6\u5ba1\u8ba1\u62a5\u544a",
        "{year}\u5e74\u5ea6\u5185\u90e8\u63a7\u5236\u8bc4\u4ef7\u62a5\u544a",
        "{year}\u5e74\u5ea6\u5185\u90e8\u63a7\u5236\u5ba1\u8ba1\u62a5\u544a",
        "{year}\u5e74\u5ea6\u975e\u7ecf\u8425\u6027\u8d44\u91d1\u5360\u7528",
        "{year}\u5e74\u4e13\u9879\u5ba1\u8ba1\u62a5\u544a",
    )

    def __init__(self) -> None:
        self.enabled = settings.cninfo_enable
        self.query_url = settings.cninfo_query_url
        self.static_base_url = settings.cninfo_static_base_url.rstrip("/")
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.cninfo.com.cn/",
        }
        self.timeout = httpx.Timeout(connect=10.0, read=60.0, write=20.0, pool=20.0)

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
            raise ValueError(f"\u65e0\u6cd5\u89e3\u6790 {ticker} \u5bf9\u5e94\u7684\u5de8\u6f6e\u8bc1\u5238\u7f16\u7801\u3002")

        return self._fetch_with_search(ticker, stock_param, date_from, date_to, searchkey="")

    def fetch_annual_package(self, ticker: str, fiscal_year: int) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        stock_param = self._build_stock_param(ticker)
        if not stock_param:
            raise ValueError(f"\u65e0\u6cd5\u89e3\u6790 {ticker} \u5bf9\u5e94\u7684\u5de8\u6f6e\u8bc1\u5238\u7f16\u7801\u3002")

        date_from = date(fiscal_year, 1, 1)
        date_to = date(fiscal_year + 1, 12, 31)
        documents: dict[str, dict[str, Any]] = {}
        for template in self.ANNUAL_PACKAGE_KEYWORDS:
            keyword = template.format(year=fiscal_year)
            for item in self._fetch_with_search(ticker, stock_param, date_from, date_to, searchkey=keyword):
                if item.get("category") != "document":
                    continue
                item.setdefault("diagnostics", {})
                item["diagnostics"]["searchkey"] = keyword
                item["diagnostics"]["fiscal_year"] = fiscal_year
                item["diagnostics"]["sync_path"] = "annual_package"
                dedupe_key = str(item.get("source_object_id") or "") or self._dedupe_key_from_item(item)
                documents[dedupe_key] = item
        return list(documents.values())

    def _fetch_with_search(
        self,
        ticker: str,
        stock_param: str,
        date_from: date,
        date_to: date,
        *,
        searchkey: str,
    ) -> list[dict[str, Any]]:
        base_payload = {
            "pageSize": self.page_size,
            "column": "sse" if ticker.upper().endswith(".SH") else "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": stock_param,
            "searchkey": searchkey,
            "category": "",
            "seDate": f"{date_from.isoformat()}~{date_to.isoformat()}",
            "isHLtitle": "true",
        }

        announcements: list[dict[str, Any]] = []
        total_record_num = 0
        pages_fetched = 0
        for page_num in range(1, self.max_pages + 1):
            payload = {**base_payload, "pageNum": page_num}
            data = self._request_json_with_retry("POST", self.query_url, headers=self.headers, timeout=self.timeout, data=payload)
            rows = data.get("announcements") or []
            total_record_num = int(data.get("totalRecordNum") or total_record_num or 0)
            pages_fetched = page_num
            if not rows:
                break

            for row in rows:
                item = self._serialize_announcement_row(row, stock_param, base_payload["seDate"], page_num, total_record_num)
                if item is not None:
                    announcements.append(item)

            if total_record_num and len(announcements) >= total_record_num:
                break
            if len(rows) < self.page_size:
                break

        total_pages = math.ceil(total_record_num / self.page_size) if total_record_num else pages_fetched
        for item in announcements:
            item.setdefault("diagnostics", {})
            item["diagnostics"]["pages_fetched"] = pages_fetched
            item["diagnostics"]["total_pages"] = total_pages
            item["diagnostics"].setdefault("sync_path", "generic_window")
            if searchkey:
                item["diagnostics"]["searchkey"] = searchkey
        return announcements

    def _serialize_announcement_row(
        self,
        row: dict[str, Any],
        stock_param: str,
        se_date: str,
        page_num: int,
        total_record_num: int,
    ) -> dict[str, Any] | None:
        title = str(row.get("announcementTitle") or row.get("announcementTitleCn") or "").strip()
        if not title:
            return None
        normalized_title = self._normalize_title(title)
        category = self._classify_title(normalized_title)
        document_url = self._build_document_url(row.get("adjunctUrl"))
        return {
            "source": self.provider_name,
            "source_object_id": str(row.get("announcementId") or "").strip() or None,
            "title": title,
            "normalized_title": normalized_title,
            "announcement_date": self._normalize_announcement_time(row.get("announcementTime")),
            "source_url": document_url or self.query_url,
            "document_url": document_url,
            "content_text": None,
            "raw_payload": row,
            "category": category,
            "document_type": self._infer_document_type(normalized_title) if category == "document" else None,
            "event_type": "regulatory_penalty" if category == "penalty" else None,
            "summary": title,
            "regulator": "cninfo",
            "diagnostics": {
                "stock": stock_param,
                "page_num": page_num,
                "seDate": se_date,
                "totalRecordNum": total_record_num,
            },
        }

    def _dedupe_key_from_item(self, item: dict[str, Any]) -> str:
        return "|".join(
            [
                str(item.get("title") or ""),
                str(item.get("announcement_date") or ""),
                str(item.get("document_url") or ""),
            ]
        )

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

    def _normalize_title(self, title: str) -> str:
        normalized = title.strip().upper()
        normalized = normalized.replace("\uff08", "(").replace("\uff09", ")")
        normalized = normalized.replace("\u3010", "[").replace("\u3011", "]")
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def _classify_title(self, normalized_title: str) -> str:
        if any(keyword in normalized_title for keyword in self.PENALTY_KEYWORDS):
            return "penalty"
        if any(keyword in normalized_title for keyword in self.DOCUMENT_KEYWORDS):
            return "document"
        return "other"

    def _infer_document_type(self, normalized_title: str) -> str:
        if "\u5185\u90e8\u63a7\u5236\u5ba1\u8ba1\u62a5\u544a" in normalized_title or "\u5185\u63a7\u5ba1\u8ba1\u62a5\u544a" in normalized_title:
            return "internal_control_report"
        if "\u5185\u90e8\u63a7\u5236\u8bc4\u4ef7\u62a5\u544a" in normalized_title or "\u5185\u63a7\u8bc4\u4ef7\u62a5\u544a" in normalized_title:
            return "internal_control_report"
        if "\u5ba1\u8ba1\u62a5\u544a" in normalized_title:
            return "audit_report"
        if "\u534a\u5e74\u5ea6\u62a5\u544a" in normalized_title or "\u534a\u5e74\u62a5" in normalized_title:
            return "interim_report"
        if (
            "\u7b2c\u4e00\u5b63\u5ea6\u62a5\u544a" in normalized_title
            or "\u7b2c\u4e09\u5b63\u5ea6\u62a5\u544a" in normalized_title
            or "\u5b63\u5ea6\u62a5\u544a" in normalized_title
        ):
            return "quarter_report"
        if any(
            keyword in normalized_title
            for keyword in (
                "\u4e13\u9879\u5ba1\u6838",
                "\u4e13\u9879\u5ba1\u8ba1",
                "\u8d44\u91d1\u5360\u7528\u4e13\u9879\u8bf4\u660e",
                "\u8d22\u52a1\u51b3\u7b97\u62a5\u544a",
            )
        ):
            return "special_report"
        return "annual_report"

    @classmethod
    @lru_cache(maxsize=1)
    def _load_stock_mapping(cls) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cninfo.com.cn/",
        }
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=20.0, pool=20.0)
        payload = cls._request_json_with_retry("GET", cls.stock_list_url, headers=headers, timeout=timeout)
        rows = payload.get("stockList") or []
        mapping: dict[str, str] = {}
        for row in rows:
            code = str(row.get("code") or "").strip()
            org_id = str(row.get("orgId") or "").strip()
            if code and org_id:
                mapping[code] = org_id
        return mapping

    @classmethod
    def _request_json_with_retry(
        cls,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: httpx.Timeout,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, cls.max_retries + 1):
            try:
                with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
                    response = client.request(method, url, data=data)
                    response.raise_for_status()
                    return response.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.HTTPStatusError) as exc:
                retryable = True
                if isinstance(exc, httpx.HTTPStatusError):
                    retryable = exc.response.status_code >= 500
                last_error = exc
                if attempt >= cls.max_retries or not retryable:
                    break
                time.sleep(float(attempt))
            except Exception as exc:
                last_error = exc
                break
        if last_error is None:
            raise RuntimeError("cninfo request failed without an explicit error")
        raise last_error
