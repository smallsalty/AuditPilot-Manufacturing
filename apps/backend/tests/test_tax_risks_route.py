from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import enterprises as enterprises_route
from app.core.db import get_db
from app.models import EnterpriseProfile
from app.models.base import Base
from app.services.tax_risk_service import TaxRiskService


def _build_app():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add(
            EnterpriseProfile(
                name="测试企业",
                ticker="600000.SH",
                report_year=2024,
                industry_tag="制造业",
                exchange="SSE",
            )
        )
        db.commit()

    app = FastAPI()
    app.include_router(enterprises_route.router, prefix="/api")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


def test_tax_risks_route_returns_payload(monkeypatch) -> None:
    app = _build_app()
    monkeypatch.setattr(
        TaxRiskService,
        "build_tax_risks",
        lambda self, db, enterprise_id: {
            "enterprise_id": enterprise_id,
            "as_of_period": "20241231",
            "evaluation_basis": "latest_annual",
            "diagnostics": {"evaluated_rules": ["TAX_ETR_ABNORMAL"], "skipped_rules": [], "missing_indicators": []},
            "tax_risks": [{"rule_code": "TAX_ETR_ABNORMAL", "risk_name": "企业所得税有效税率异常"}],
        },
    )

    response = TestClient(app).get("/api/enterprises/1/tax-risks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enterprise_id"] == 1
    assert payload["tax_risks"][0]["rule_code"] == "TAX_ETR_ABNORMAL"


def test_tax_risks_route_returns_404_for_missing_enterprise(monkeypatch) -> None:
    app = _build_app()
    monkeypatch.setattr(TaxRiskService, "build_tax_risks", lambda self, db, enterprise_id: (_ for _ in ()).throw(ValueError("企业不存在。")))

    response = TestClient(app).get("/api/enterprises/999/tax-risks")

    assert response.status_code == 404
