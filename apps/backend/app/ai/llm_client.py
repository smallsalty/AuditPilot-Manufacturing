import json
import logging
import re
from typing import Any

from anthropic import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, Anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.provider = (settings.llm_provider or "minimax").lower().strip()
        self.model = (settings.llm_model or "MiniMax-M2.7").strip()
        self.base_url = (settings.llm_base_url or "").strip()
        self.api_key = (settings.llm_api_key or "").strip()
        self.config_error: str | None = None

        logger.info(
            "llm configuration loaded provider=%s model=%s base_url=%s api_key_set=%s",
            self.provider or "<unset>",
            self.model or "<unset>",
            self.base_url or "<unset>",
            bool(self.api_key),
        )

        if not self.api_key:
            self.config_error = "模型配置未加载：缺少 API Key，请检查 ANTHROPIC_API_KEY 或兼容的 LLM_API_KEY。"
        elif not self.base_url:
            self.config_error = "模型配置未加载：缺少 base URL，请检查 ANTHROPIC_BASE_URL。"

        self.client = None
        if not self.config_error:
            self.client = Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=120.0,
            )

    @retry(
        retry=retry_if_exception_type((APITimeoutError, APIConnectionError, APIStatusError, APIResponseValidationError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True,
    )
    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        timeout: float = 120.0,
    ) -> Any:
        if self.config_error:
            raise RuntimeError(self.config_error)

        try:
            prompt = user_prompt
            if json_mode:
                prompt = f"{user_prompt}\n请严格返回一个合法 JSON 对象，不要输出 Markdown 代码块。"

            response = self.client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                timeout=timeout,
            )

            content = self._extract_text(response)
            content = self._clean_content(content)

            if json_mode:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    logger.warning("LLM returned non-JSON content in json_mode: %s", content[:500])
                    return {"raw": content}

            return content
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning(
                "LLM request failed for provider=%s model=%s base_url=%s error=%s",
                self.provider,
                self.model or "<unset>",
                self.base_url or "<unset>",
                exc.__class__.__name__,
            )
            raise RuntimeError("模型服务不可连接，请检查 ANTHROPIC_BASE_URL 和云端网络连通性。") from exc
        except APIStatusError as exc:
            logger.warning(
                "LLM request rejected provider=%s model=%s status=%s",
                self.provider,
                self.model or "<unset>",
                exc.status_code,
            )
            raise RuntimeError(
                f"模型服务返回错误：HTTP {exc.status_code}，请检查 MiniMax 模型名、鉴权和兼容接口配置。"
            ) from exc
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning(
                "LLM request failed for provider=%s model=%s: %s",
                self.provider,
                self.model or "<unset>",
                exc.__class__.__name__,
            )
            raise

    def _extract_text(self, response) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    def _clean_content(self, content: str) -> str:
        if not content:
            return ""

        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S | re.I)
        content = content.strip()

        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
            content = re.sub(r"\s*```$", "", content)

        return content.strip()
