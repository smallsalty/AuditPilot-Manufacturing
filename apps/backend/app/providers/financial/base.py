from abc import ABC, abstractmethod
from typing import Any


class BaseFinancialProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def fetch_financials(
        self,
        ticker: str,
        include_quarterly: bool = True,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

