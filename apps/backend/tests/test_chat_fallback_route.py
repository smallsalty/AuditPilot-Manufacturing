from __future__ import annotations

import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


if "anthropic" not in sys.modules:
    anthropic = types.ModuleType("anthropic")

    class _DummyError(Exception):
        pass

    class _DummyAnthropic:
        def __init__(self, *args, **kwargs) -> None:
            pass

    anthropic.APIConnectionError = _DummyError
    anthropic.APIResponseValidationError = _DummyError
    anthropic.APIStatusError = _DummyError
    anthropic.APITimeoutError = _DummyError
    anthropic.Anthropic = _DummyAnthropic
    sys.modules["anthropic"] = anthropic


from app.ai.audit_qa_server import AuditQAServer
from app.ai.llm_client import LLMClient
from app.api.routes import chat as chat_route
from app.core.db import get_db
from app.models import EnterpriseProfile
from app.models.base import Base


def test_chat_route_returns_200_when_llm_fails(monkeypatch) -> None:
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
    app.include_router(chat_route.router, prefix="/api")

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr(
        AuditQAServer,
        "_collect_context",
        lambda self, db, enterprise, question: (
            [],
            [
                {
                    "risk_name": "Revenue recognition",
                    "summary": "Revenue requires review.",
                    "evidence": [{"source_label": "<em>2025年</em>半年度报告", "snippet": "Revenue section"}],
                }
            ],
            [],
        ),
    )

    def _raise_failure(self, *args, **kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(LLMClient, "chat_completion", _raise_failure)

    client = TestClient(app)
    response = client.post("/api/chat/1", json={"question": "What are the current risks?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert payload["suggested_actions"]
    assert payload["citations"][0]["title"]
    assert "<em>" not in payload["citations"][0]["title"]
