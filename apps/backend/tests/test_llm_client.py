import app.ai.llm_client as llm_client_module
from app.ai.llm_client import LLMClient
from app.core.config import Settings


def test_llm_client_falls_back_to_mock_mode() -> None:
    client = LLMClient()
    result = client.chat_completion("system", "请解释存货风险", json_mode=True)
    assert "summary" in result
    assert "procedures" in result


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


def test_llm_client_uses_generic_openai_compatible_init(monkeypatch) -> None:
    captured = {}

    class DummyOpenAI:
        def __init__(self, api_key: str, base_url: str) -> None:
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr(llm_client_module.settings, "llm_provider", "minimax")
    monkeypatch.setattr(llm_client_module.settings, "llm_api_key", "mini-key")
    monkeypatch.setattr(llm_client_module.settings, "llm_base_url", "https://api.minimax.io/v1")
    monkeypatch.setattr(llm_client_module.settings, "llm_model", "MiniMax-M2.5")
    monkeypatch.setattr(llm_client_module, "OpenAI", DummyOpenAI)

    client = llm_client_module.LLMClient()

    assert client.mock_mode is False
    assert client.provider == "minimax"
    assert client.model == "MiniMax-M2.5"
    assert captured == {"api_key": "mini-key", "base_url": "https://api.minimax.io/v1"}
