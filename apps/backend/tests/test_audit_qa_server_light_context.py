from __future__ import annotations

import sys
import types


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


def test_chat_completion_uses_light_context_and_small_token_budget() -> None:
    captured: dict[str, object] = {}

    class FakeLLM:
        def chat_completion(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            return {"summary": "ok"}

    server = AuditQAServer(llm_client=FakeLLM())
    result = server._run_chat_completion(
        enterprise_id=2,
        system_prompt="system",
        user_prompt="user",
        context_variant="risk_summary",
        candidate_count=3,
    )

    assert result == {"summary": "ok"}
    assert captured["kwargs"]["max_tokens"] == 512
    assert captured["kwargs"]["metadata"]["context_variant"] == "risk_summary"
