from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class BaseAuditProvider(ABC):
    provider_name = "base"
    priority = 0
    is_official_source = False

    @abstractmethod
    def fetch_company_profile(self, ticker: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def fetch_announcements(
        self,
        ticker: str,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
