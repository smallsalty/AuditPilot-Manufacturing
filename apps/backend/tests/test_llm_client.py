import app.ai.llm_client as llm_client_module
from app.ai.llm_client import LLMClient, LLMRequestError
from app.core.config import Settings


def test_settings_support_legacy_glm_env_names(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "legacy-key")
    monkeypatch.setenv("GLM_BASE_URL", "https://legacy.example.com/v1")
    monkeypatch.setenv("GLM_MODEL", "legacy-model")

    settings = Settings(_env_file=None)

    assert settings.llm_api_key == "legacy-key"
    assert settings.llm_base_url == "https://legacy.example.com/v1"
    assert settings.llm_model == "legacy-model"


def test_llm_client_uses_anthropic_compatible_init(monkeypatch) -> None:
    captured = {}

    class DummyAnthropic:
        def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["timeout"] = timeout

    monkeypatch.setattr(llm_client_module.settings, "llm_provider", "minimax")
    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)

    client = llm_client_module.LLMClient()

    assert client.config_error is None
    assert client.provider == "minimax"
    assert client.model == "MiniMax-M2.5"
    assert captured == {
        "api_key": "mini-key",
        "base_url": "https://api.minimax.io/anthropic",
        "timeout": 120.0,
    }


def test_llm_client_maps_401_without_retry(monkeypatch) -> None:
    class DummyStatusError(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__(f"status {status_code}")
            self.status_code = status_code
            self.response = type("Resp", (), {"headers": {}, "text": "unauthorized"})()

    class DummyMessages:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: object) -> object:
            self.calls += 1
            raise DummyStatusError(401)

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)
    monkeypatch.setattr(llm_client_module, "APIStatusError", DummyStatusError)

    client = llm_client_module.LLMClient()

    try:
        client.chat_completion("system", "user", max_attempts=3)
    except LLMRequestError as exc:
        assert exc.status_code == 401
        assert exc.error_type == "auth_error"
        assert exc.retryable is False
        assert "HTTP 401" in str(exc)
    else:
        raise AssertionError("expected LLMRequestError")

    assert client.client.messages.calls == 1


def test_llm_client_retries_529_then_succeeds(monkeypatch) -> None:
    class DummyStatusError(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__(f"status {status_code}")
            self.status_code = status_code
            self.response = type("Resp", (), {"headers": {}, "text": "busy"})()

    class DummyMessages:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: object) -> object:
            self.calls += 1
            if self.calls < 3:
                raise DummyStatusError(529)
            block = type("Block", (), {"text": '{"summary": "ok"}'})()
            return type("Response", (), {"content": [block]})()

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)
    monkeypatch.setattr(llm_client_module, "APIStatusError", DummyStatusError)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = llm_client_module.LLMClient()
    result = client.chat_completion("system", "user", json_mode=True, max_attempts=3)

    assert result["summary"] == "ok"
    assert result["parsed_ok"] is True
    assert result["payload_mode"] == "dict"
    assert client.client.messages.calls == 3


def test_llm_client_marks_transport_errors_with_fixed_error_type(monkeypatch) -> None:
    class DummyConnectionError(Exception):
        pass

    class DummyMessages:
        def create(self, **_: object) -> object:
            raise DummyConnectionError("network down")

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)
    monkeypatch.setattr(llm_client_module, "APIConnectionError", DummyConnectionError)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = llm_client_module.LLMClient()

    try:
        client.chat_completion("system", "user", max_attempts=1)
    except LLMRequestError as exc:
        assert exc.error_type == "transport_error"
        assert exc.retryable is True
    else:
        raise AssertionError("expected LLMRequestError")


def test_llm_client_extracts_top_level_list_from_wrapped_text(monkeypatch) -> None:
    class DummyMessages:
        def create(self, **_: object) -> object:
            block = type("Block", (), {"text": '说明如下：\n[{"summary":"ok"}]\n请查收'})()
            return type("Response", (), {"content": [block]})()

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)

    client = llm_client_module.LLMClient()
    result = client.chat_completion("system", "user", json_mode=True)

    assert result["parsed_ok"] is True
    assert result["payload_mode"] == "extracted_list"
    assert result["items"] == [{"summary": "ok"}]


def test_llm_client_partially_recovers_truncated_array(monkeypatch) -> None:
    class DummyMessages:
        def create(self, **_: object) -> object:
            text = '[{"summary":"one","event_type":"executive_change"},{"summary":"two"'
            block = type("Block", (), {"text": text})()
            return type("Response", (), {"content": [block]})()

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)

    client = llm_client_module.LLMClient()
    result = client.chat_completion("system", "user", json_mode=True)

    assert result["parsed_ok"] is True
    assert result["payload_mode"] == "partial_list"
    assert result["truncated_json_prefix"] is True
    assert result["items"] == [{"summary": "one", "event_type": "executive_change"}]


def test_llm_client_returns_raw_payload_markers_when_json_is_unrecoverable(monkeypatch) -> None:
    class DummyMessages:
        def create(self, **_: object) -> object:
            block = type("Block", (), {"text": 'summary: ok "broken": [not-json'})()
            return type("Response", (), {"content": [block]})()

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)

    client = llm_client_module.LLMClient()
    result = client.chat_completion("system", "user", json_mode=True)

    assert result["parsed_ok"] is False
    assert result["payload_mode"] == "raw_text"
    assert "broken" in result["raw"]


def test_llm_client_retries_after_json_decode_failure(monkeypatch) -> None:
    class DummyMessages:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_: object) -> object:
            self.calls += 1
            text = 'summary: broken payload' if self.calls == 1 else '{"summary":"ok"}'
            block = type("Block", (), {"text": text})()
            return type("Response", (), {"content": [block]})()

    class DummyAnthropic:
        def __init__(self, **_: object) -> None:
            self.messages = DummyMessages()

    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/anthropic")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "Anthropic", DummyAnthropic)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = llm_client_module.LLMClient()
    result = client.chat_completion("system", "user", json_mode=True, max_attempts=2)

    assert result["parsed_ok"] is True
    assert result["summary"] == "ok"
    assert client.client.messages.calls == 2
