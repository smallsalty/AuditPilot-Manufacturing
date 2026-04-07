import json
from typing import Any

from app.core.config import settings
from app.providers.risk.base import BaseCorporateRiskProvider


class MockCorporateRiskProvider(BaseCorporateRiskProvider):
    provider_name = "mock"

    def fetch_risk_events(self, ticker: str) -> list[dict[str, Any]]:
        path = settings.data_root / "mock" / "corporate" / "risk_events.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in data if item["ticker"] == ticker]

