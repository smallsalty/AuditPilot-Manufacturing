from abc import ABC, abstractmethod
from typing import Any


class BaseDocumentProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def fetch_documents(self, ticker: str) -> list[dict[str, Any]]:
        raise NotImplementedError

