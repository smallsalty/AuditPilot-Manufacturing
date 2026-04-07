from abc import ABC, abstractmethod
from typing import Any


class BaseCorporateRiskProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def fetch_risk_events(self, ticker: str) -> list[dict[str, Any]]:
        raise NotImplementedError

