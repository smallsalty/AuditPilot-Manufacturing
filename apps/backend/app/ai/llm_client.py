from __future__ import annotations

import json
import logging
import random
import re
import time
from json import JSONDecodeError
from typing import Any

try:
    from anthropic import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, Anthropic
except ImportError:  # pragma: no cover
    APIConnectionError = RuntimeError
    APIResponseValidationError = RuntimeError
    APIStatusError = RuntimeError
    APITimeoutError = RuntimeError
    Anthropic = None

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        provider_response_text: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.provider_response_text = provider_response_text
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "status_code": self.status_code,
            "error_type": self.error_type,
            "provider_response_text": self.provider_response_text,
            "retryable": self.retryable,
        }


class LLMClient:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}

    def __init__(self) -> None:
        self.provider = (settings.llm_provider or "minimax").lower().strip()
        self.model = (settings.llm_model or "MiniMax-M2.7").strip()
        self.base_url = (settings.llm_base_url or "").strip()
        self.api_key = (settings.llm_api_key or "").strip()
        self.config_error: str | None = None

        logger.info(
            "llm configuration loaded provider=%s model=%s base_url=%s api_key_set=%s sdk_installed=%s",
            self.provider or "<unset>",
            self.model or "<unset>",
            self.base_url or "<unset>",
            bool(self.api_key),
            Anthropic is not None,
        )

        if Anthropic is None:
            self.config_error = "模型配置未加载：后端环境缺少 anthropic SDK。"
        elif not self.api_key:
            self.config_error = "模型配置未加载：缺少 API Key，请检查 ANTHROPIC_API_KEY 或兼容的 LLM_API_KEY。"
        elif not self.base_url:
            self.config_error = "模型配置未加载：缺少 base URL，请检查 ANTHROPIC_BASE_URL 或兼容的 LLM_BASE_URL。"

        self.client = None
        if not self.config_error and Anthropic is not None:
            self.client = Anthropic(api_key=self.api_key, base_url=self.base_url, timeout=120.0)

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
            raise LLMRequestError(self.config_error, error_type="config_error", retryable=False)

        metadata = dict(metadata or {})
        prompt = user_prompt
        if json_mode and strict_json_instruction:
            prompt = (
                f"{user_prompt}\n"
                "请严格返回一个合法 JSON 对象或 JSON 数组，不要输出 Markdown 代码块。"
            )

        base_log_fields = {
            "request_kind": request_kind,
            "enterprise_id": metadata.get("enterprise_id"),
            "document_id": metadata.get("document_id"),
            "classified_type": metadata.get("classified_type"),
            "prompt_template": metadata.get("prompt_template"),
            "schema_name": metadata.get("schema_name"),
            "model": self.model or "<unset>",
            "base_url": self.base_url or "<unset>",
            "status_code": None,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
            "strict_json_instruction": strict_json_instruction,
            "retry_attempt": None,
            "candidate_count": metadata.get("candidate_count"),
            "context_variant": metadata.get("context_variant"),
            "llm_input_chars": metadata.get("llm_input_chars") or len(system_prompt or "") + len(prompt or ""),
            "provider_response_text": None,
        }
        logger.info("llm request start %s", self._format_log_fields(base_log_fields))

        last_error: LLMRequestError | None = None
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
                content = self._clean_content(self._extract_text(response))
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
                    parsed = self._parse_json_response(content)
                    if parsed.get("parsed_ok"):
                        parsed["retry_attempts"] = attempt
                        parsed["response_chars"] = len(content)
                        if parsed.get("payload_mode") in {"extracted_dict", "extracted_list"}:
                            logger.info(
                                "llm json extract recovered %s",
                                self._format_log_fields(
                                    {
                                        **attempt_fields,
                                        "payload_mode": parsed.get("payload_mode"),
                                    }
                                ),
                            )
                        if parsed.get("payload_mode") in {"partial_dict", "partial_list"}:
                            logger.info(
                                "llm json partial recovered %s",
                                self._format_log_fields(
                                    {
                                        **attempt_fields,
                                        "payload_mode": parsed.get("payload_mode"),
                                        "raw_prefix_kind": parsed.get("raw_prefix_kind"),
                                        "recovered_count": len(parsed.get("items") or []) if isinstance(parsed.get("items"), list) else 1,
                                    }
                                ),
                            )
                        return parsed
                    logger.warning(
                        "llm json decode failed %s",
                        self._format_log_fields(
                            {
                                **attempt_fields,
                                "error_type": "json_decode_error",
                                "payload_mode": parsed.get("payload_mode"),
                                "provider_response_text": self._truncate_text(str(parsed.get("raw") or content)),
                            }
                        ),
                    )
                    if attempt < max_attempts:
                        time.sleep(self._backoff_seconds(attempt))
                        continue
                    parsed["retry_attempts"] = attempt
                    parsed["response_chars"] = len(content)
                    return parsed

                return content
            except (APIConnectionError, APITimeoutError, APIResponseValidationError) as exc:
                last_error = LLMRequestError(
                    "模型服务连接失败，请检查 Anthropic 兼容接口地址和网络连通性。",
                    error_type="transport_error",
                    provider_response_text=self._truncate_text(str(exc)),
                    retryable=True,
                )
                logger.warning(
                    "llm request transport failure %s",
                    self._format_log_fields(
                        {
                            **attempt_fields,
                            "error_type": last_error.error_type,
                            "provider_response_text": last_error.provider_response_text,
                        }
                    ),
                )
                if attempt < max_attempts:
                    time.sleep(self._backoff_seconds(attempt))
                    continue
                raise last_error from exc
            except APIStatusError as exc:
                error_fields = dict(attempt_fields)
                error_fields.update(self._extract_status_error_fields(exc))
                logger.warning("llm request rejected %s", self._format_log_fields(error_fields))

                status_code = error_fields.get("status_code")
                retryable = self._should_retry_status(status_code)
                if status_code == 401:
                    message = "模型服务返回错误：HTTP 401，请检查 MiniMax 模型名、鉴权和 Anthropic 兼容接口配置。"
                    error_type = "auth_error"
                elif retryable:
                    message = f"模型服务暂时不可用：HTTP {status_code}。"
                    error_type = "upstream_unavailable"
                else:
                    message = f"模型服务返回错误：HTTP {status_code}，请检查 MiniMax 模型名、鉴权和兼容接口配置。"
                    error_type = "request_rejected"

                last_error = LLMRequestError(
                    message,
                    status_code=status_code,
                    error_type=error_type,
                    provider_response_text=error_fields.get("provider_response_text"),
                    retryable=retryable,
                )
                if attempt < max_attempts and retryable:
                    time.sleep(self._backoff_seconds(attempt))
                    continue
                raise last_error from exc
            except LLMRequestError:
                raise
            except Exception as exc:  # pragma: no cover
                last_error = LLMRequestError(
                    "模型请求失败。",
                    error_type="unexpected_error",
                    provider_response_text=self._truncate_text(str(exc)),
                    retryable=False,
                )
                logger.warning(
                    "llm request failed %s",
                    self._format_log_fields(
                        {
                            **attempt_fields,
                            "error_type": last_error.error_type,
                            "provider_response_text": last_error.provider_response_text,
                        }
                    ),
                )
                break

        if last_error is not None:
            raise last_error
        raise LLMRequestError("模型请求失败。", error_type="unknown", retryable=False)

    def _extract_text(self, response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    def _clean_content(self, content: str) -> str:
        if not content:
            return ""

        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S | re.I).strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
            content = re.sub(r"\s*```$", "", content)
        return content.strip()

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        direct = self._build_json_result(self._try_json_load(content), payload_mode=None)
        if direct is not None:
            return direct

        extracted_source = self._extract_first_json_block(content)
        if extracted_source:
            extracted = self._build_json_result(self._try_json_load(extracted_source), payload_mode="extracted")
            if extracted is not None:
                return extracted

        partial = self._recover_partial_json_payload(content)
        if partial is not None:
            return partial

        raw_prefix_kind = self._detect_json_prefix_kind(content)

        return {
            "parsed_ok": False,
            "payload_mode": "raw_text",
            "raw": content,
            "raw_prefix_kind": raw_prefix_kind,
            "truncated_json_prefix": raw_prefix_kind is not None,
        }

    def _build_json_result(self, payload: Any, payload_mode: str | None) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            result = dict(payload)
            result["parsed_ok"] = True
            result["payload_mode"] = f"{payload_mode}_dict" if payload_mode else "dict"
            return result
        if isinstance(payload, list):
            return {
                "items": payload,
                "parsed_ok": True,
                "payload_mode": f"{payload_mode}_list" if payload_mode else "list",
            }
        return None

    def _try_json_load(self, content: str) -> Any:
        if not content:
            return None
        try:
            return json.loads(content)
        except JSONDecodeError:
            return None

    def _recover_partial_json_payload(self, content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if not text:
            return None

        raw_prefix_kind = self._detect_json_prefix_kind(text)
        first_array = text.find("[")
        first_object = text.find("{")
        if first_array != -1 and (first_object == -1 or first_array < first_object):
            items = self._recover_partial_json_array_items(text[first_array:])
            if items:
                return {
                    "items": items,
                    "parsed_ok": True,
                    "payload_mode": "partial_list",
                    "raw_prefix_kind": raw_prefix_kind or "array_prefix",
                    "truncated_json_prefix": True,
                }

        if first_object != -1:
            try:
                payload, _ = json.JSONDecoder().raw_decode(text, first_object)
            except JSONDecodeError:
                return None
            if isinstance(payload, dict):
                result = dict(payload)
                result["parsed_ok"] = True
                result["payload_mode"] = "partial_dict"
                result["raw_prefix_kind"] = raw_prefix_kind or "object_prefix"
                result["truncated_json_prefix"] = True
                return result
        return None

    def _recover_partial_json_array_items(self, raw: str) -> list[dict[str, Any]]:
        start = raw.find("[")
        if start == -1:
            return []

        decoder = json.JSONDecoder()
        items: list[dict[str, Any]] = []
        index = start + 1
        while index < len(raw):
            while index < len(raw) and raw[index] in " \r\n\t,":
                index += 1
            if index >= len(raw) or raw[index] == "]":
                break
            if raw[index] != "{":
                break
            try:
                payload, end = decoder.raw_decode(raw, index)
            except JSONDecodeError:
                break
            if not isinstance(payload, dict):
                break
            items.append(payload)
            index = end
        return items

    def _extract_first_json_block(self, content: str) -> str | None:
        start_index = None
        opening = None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(content):
            if start_index is None:
                if char in "{[":
                    start_index = index
                    opening = char
                    depth = 1
                continue

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char in "{[":
                depth += 1
                continue
            if char in "}]":
                depth -= 1
                if depth == 0:
                    candidate = content[start_index : index + 1].strip()
                    if opening == "[" and candidate.endswith("]"):
                        return candidate
                    if opening == "{" and candidate.endswith("}"):
                        return candidate
                    return None
        return None

    def _detect_json_prefix_kind(self, content: str) -> str | None:
        stripped = content.lstrip()
        if not stripped:
            return None
        if stripped[0] == "[":
            return "array_prefix"
        if stripped[0] == "{":
            return "object_prefix"
        first_array = stripped.find("[")
        first_object = stripped.find("{")
        if first_array == -1 and first_object == -1:
            return None
        if first_array != -1 and (first_object == -1 or first_array < first_object):
            return "array_prefix"
        return "object_prefix"

    def _backoff_seconds(self, attempt: int) -> float:
        base = min(10.0, 2.0 * (2 ** max(attempt - 1, 0)))
        return base + random.uniform(0.0, 1.0)

    def _should_retry_status(self, status_code: int | None) -> bool:
        return status_code in self.RETRYABLE_STATUS_CODES

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
            "status_code": getattr(exc, "status_code", None),
            "request_id": headers.get("x-request-id") or headers.get("request-id"),
            "provider_response_text": self._truncate_text(response_text or str(exc)),
        }

    def _truncate_text(self, value: str | None, limit: int = 600) -> str:
        if not value:
            return ""
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit]}..."

    def _format_log_fields(self, fields: dict[str, Any]) -> str:
        parts: list[str] = []
        for key, value in fields.items():
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={value}")
        return " ".join(parts)
