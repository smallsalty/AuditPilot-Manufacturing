import csv
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.financial.base import BaseFinancialProvider


class MockFinancialProvider(BaseFinancialProvider):
    provider_name = "mock"

    def fetch_financials(self, ticker: str, include_quarterly: bool = True) -> list[dict[str, Any]]:
        seed_file = settings.data_root / "seeds" / "backend" / "financial_indicators.csv"
        rows: list[dict[str, Any]] = []
        with seed_file.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row["ticker"] != ticker:
                    continue
                if not include_quarterly and row["period_type"] == "quarterly":
                    continue
                rows.append(row)
        return rows

