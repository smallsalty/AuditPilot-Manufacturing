from __future__ import annotations

import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
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


def test_audit_qa_server_normalizes_list_payload() -> None:
    server = AuditQAServer()

    normalized = server._normalize_chat_result(
        [
            {"procedures": ["先看证据"]},
            {"summary": "这是回答", "procedures": ["复核收入"]},
        ]
    )

    assert normalized["answer"] == "这是回答"
    assert normalized["suggested_actions"] == ["复核收入"]
    assert normalized["payload_mode"] == "list_item"


def test_audit_qa_server_normalizes_raw_payload_to_fallback_answer() -> None:
    server = AuditQAServer()

    normalized = server._normalize_chat_result({"parsed_ok": False, "payload_mode": "raw_text", "raw": "  "})

    assert normalized["answer"]
    assert normalized["payload_mode"] == "raw_text"
    assert normalized["suggested_actions"]


def test_chat_route_returns_200_for_list_payload(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as seed_db:
        seed_db.add(
            EnterpriseProfile(
                name="测试企业",
                ticker="000001",
                report_year=2024,
                industry_tag="制造业",
                exchange="SSE",
            )
        )
        seed_db.commit()

    app = FastAPI()
    app.include_router(chat_route.router, prefix="/api")

    def override_get_db():
        db = TestingSessionLocal()
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
            [{"risk_name": "收入确认", "summary": "关注收入确认", "evidence": []}],
            [],
        ),
    )
    monkeypatch.setattr(LLMClient, "chat_completion", lambda self, *args, **kwargs: [{"summary": "统一回答", "procedures": ["查看收入凭证"]}])

    client = TestClient(app)
    response = client.post("/api/chat/1", json={"question": "有什么风险？"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "统一回答"
    assert payload["suggested_actions"] == ["查看收入凭证"]
