from datetime import date
from typing import Any

from app.providers.audit.base import BaseAuditProvider


class TushareFastProvider(BaseAuditProvider):
    provider_name = "tushare_fast"
    priority = 0
    is_official_source = False

    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        raise RuntimeError("tushare_fast is disabled in phase 1. Use akshare_fast + cninfo instead.")

    def fetch_announcements(self, ticker: str, date_from: date, date_to: date) -> list[dict[str, Any]]:
        raise RuntimeError("tushare_fast is disabled in phase 1. Use cninfo for announcements.")
