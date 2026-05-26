from __future__ import annotations

from app.services.ingestion_service import IngestionService


def test_ingest_financials_releases_session_before_provider_fetch():
    events: list[str] = []

    class Enterprise:
        expired = False

        @property
        def id(self):
            if self.expired:
                raise AssertionError("enterprise.id was accessed after rollback")
            return 7

        @property
        def ticker(self):
            if self.expired:
                raise AssertionError("enterprise.ticker was accessed after rollback")
            return "300750.SZ"

    enterprise = Enterprise()

    class FakeDb:
        def rollback(self):
            events.append("rollback")
            enterprise.expired = True

        def execute(self, statement):
            del statement
            events.append("execute")

        def add(self, item):
            assert item.enterprise_id == 7
            events.append("add")

        def commit(self):
            events.append("commit")

    class FakeProvider:
        provider_name = "fake"

        def fetch_financials(self, ticker, include_quarterly):
            assert ticker == "300750.SZ"
            assert include_quarterly is True
            assert events == ["rollback"]
            events.append("fetch")
            return [
                {
                    "period_type": "annual",
                    "report_period": "20251231",
                    "report_year": 2025,
                    "report_quarter": None,
                    "indicator_code": "revenue",
                    "indicator_name": "revenue",
                    "value": 1.0,
                    "unit": "cny",
                    "source": "fake",
                }
            ]

    service = IngestionService()
    service.financial_providers = {"fake": FakeProvider()}

    inserted, provider = service.ingest_financials(
        FakeDb(),
        enterprise,
        provider_name="fake",
        include_quarterly=True,
    )

    assert inserted == 1
    assert provider == "fake"
    assert events == ["rollback", "fetch", "execute", "add", "commit"]
