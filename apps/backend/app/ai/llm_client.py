import json
import logging
import random
import re
import time
from typing import Any

from anthropic import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, Anthropic

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

    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        timeout: float = 120.0,
        *,
        request_kind: str = "generic",
        metadata: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        max_attempts: int = 3,
        strict_json_instruction: bool = True,
    ) -> Any:
        if self.config_error:
            raise RuntimeError(self.config_error)

        metadata = dict(metadata or {})
        prompt = user_prompt
        if json_mode and strict_json_instruction:
            prompt = f"{user_prompt}\n请严格返回一个合法 JSON 对象，不要输出 Markdown 代码块。"

        base_log_fields = {
            "request_kind": request_kind,
            "enterprise_id": metadata.get("enterprise_id"),
            "document_id": metadata.get("document_id"),
            "classified_type": metadata.get("classified_type"),
            "model": self.model or "<unset>",
            "base_url": self.base_url or "<unset>",
            "max_tokens": max_tokens,
            "json_mode": json_mode,
            "strict_json_instruction": strict_json_instruction,
            "prompt_chars_system": len(system_prompt or ""),
            "prompt_chars_user": len(prompt or ""),
            "candidate_count": metadata.get("candidate_count"),
            "llm_input_chars": metadata.get("llm_input_chars"),
            "context_variant": metadata.get("context_variant"),
        }
        logger.info("llm request start %s", self._format_log_fields(base_log_fields))

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            attempt_fields = dict(base_log_fields)
            attempt_fields["retry_attempt"] = attempt
            try:
                response = self.client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

                content = self._extract_text(response)
                content = self._clean_content(content)

                logger.info(
                    "llm request success %s",
                    self._format_log_fields(
                        {
                            **attempt_fields,
                            "response_chars": len(content),
                        }
                    ),
                )

                if json_mode:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        logger.warning(
                            "llm json decode failed %s",
                            self._format_log_fields(
                                {
                                    **attempt_fields,
                                    "provider_response_text": self._truncate_text(content),
                                }
                            ),
                        )
                        return {"raw": content}

                return content
            except (APIConnectionError, APITimeoutError, APIResponseValidationError) as exc:
                last_error = exc
                logger.warning(
                    "llm request transport failure %s",
                    self._format_log_fields(
                        {
                            **attempt_fields,
                            "error_type": exc.__class__.__name__,
                        }
                    ),
                )
                if attempt < max_attempts:
                    time.sleep(self._backoff_seconds(attempt))
                    continue
                raise RuntimeError("模型服务不可连接，请检查 ANTHROPIC_BASE_URL 和云端网络连通性。") from exc
            except APIStatusError as exc:
                last_error = exc
                error_fields = dict(attempt_fields)
                error_fields.update(self._extract_status_error_fields(exc))
                logger.warning("llm request rejected %s", self._format_log_fields(error_fields))
                if attempt < max_attempts and self._should_retry_status(exc.status_code):
                    time.sleep(self._backoff_seconds(attempt))
                    continue
                raise RuntimeError(
                    f"模型服务返回错误：HTTP {exc.status_code}，请检查 MiniMax 模型名、鉴权和兼容接口配置。"
                ) from exc
            except RuntimeError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm request failed %s",
                    self._format_log_fields(
                        {
                            **attempt_fields,
                            "error_type": exc.__class__.__name__,
                            "provider_response_text": self._truncate_text(str(exc)),
                        }
                    ),
                )
                break

        if last_error is not None:
            raise last_error
        raise RuntimeError("模型请求失败。")

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

    def _backoff_seconds(self, attempt: int) -> float:
        base = min(10.0, 2.0 * (2 ** max(attempt - 1, 0)))
        return base + random.uniform(0.0, 1.0)

    def _should_retry_status(self, status_code: int | None) -> bool:
        return status_code in {429, 500, 502, 503, 504, 529}

    def _extract_status_error_fields(self, exc: APIStatusError) -> dict[str, Any]:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) or {}
        response_text = None
        if response is not None:
            text_attr = getattr(response, "text", None)
            if isinstance(text_attr, str):
                response_text = text_attr
            elif callable(text_attr):
                try:
                    response_text = text_attr()
                except Exception:
                    response_text = None
            if response_text is None:
                content_attr = getattr(response, "content", None)
                if isinstance(content_attr, (bytes, bytearray)):
                    response_text = bytes(content_attr).decode("utf-8", errors="replace")
                elif isinstance(content_attr, str):
                    response_text = content_attr
        return {
            "provider_status_code": getattr(exc, "status_code", None),
            "request_id": headers.get("x-request-id") or headers.get("request-id"),
            "provider_response_text": self._truncate_text(response_text or str(exc)),
        }

    def _truncate_text(self, value: str | None, limit: int = 600) -> str:
        if not value:
            return ""
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit]}…"

    def _format_log_fields(self, fields: dict[str, Any]) -> str:
        parts = []
        for key, value in fields.items():
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={value}")
        return " ".join(parts)
