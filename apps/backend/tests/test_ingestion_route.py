from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import ingestion as ingestion_route
from app.core.db import get_db
from app.models import EnterpriseProfile
from app.models.base import Base
from app.services.ingestion_service import IngestionService


def _build_app():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as seed_db:
        seed_db.add(
            EnterpriseProfile(
                name="Test Enterprise",
                ticker="000001",
                report_year=2024,
                industry_tag="Manufacturing",
                exchange="SSE",
            )
        )
        seed_db.commit()

    app = FastAPI()
    app.include_router(ingestion_route.router, prefix="/api")

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


def test_ingestion_financial_returns_200_when_provider_has_no_data(monkeypatch) -> None:
    app = _build_app()

    monkeypatch.setattr(IngestionService, "ingest_financials", lambda self, *args, **kwargs: (0, "akshare"))

    client = TestClient(app)
    response = client.post(
        "/api/ingestion/financial",
        json={
            "enterprise_id": 1,
            "provider": "akshare",
            "include_quarterly": True,
            "force_seed_fallback": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["provider"] == "akshare"
    assert payload["inserted"] == 0
    assert payload["message"]


def test_ingestion_financial_keeps_invalid_provider_as_400(monkeypatch) -> None:
    app = _build_app()

    def _raise_value_error(self, *args, **kwargs):
        raise ValueError("未知财务 provider: bad")

    monkeypatch.setattr(IngestionService, "ingest_financials", _raise_value_error)

    client = TestClient(app)
    response = client.post(
        "/api/ingestion/financial",
        json={
            "enterprise_id": 1,
            "provider": "bad",
            "include_quarterly": True,
            "force_seed_fallback": False,
        },
    )

    assert response.status_code == 400
    assert "未知财务 provider" in response.json()["detail"]
