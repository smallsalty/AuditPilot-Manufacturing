from __future__ import annotations

from app.ai.llm_client import LLMClient


def main() -> None:
    client = LLMClient()
    print(
        {
            "provider": client.provider,
            "model": client.model,
            "base_url_set": bool(client.base_url),
            "api_key_set": bool(client.api_key),
            "config_error": client.config_error,
        }
    )


if __name__ == "__main__":
    main()
