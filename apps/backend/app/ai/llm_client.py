import json
import logging
import re
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.provider = (settings.llm_provider or "minimax").lower().strip()
        self.model = (settings.llm_model or "MiniMax-M2.5").strip()
        self.base_url = (settings.llm_base_url or "").strip()
        self.api_key = (settings.llm_api_key or "").strip()
        self.mock_mode = not self.api_key
        self.client = None

        if not self.mock_mode:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=120.0,
            )

    @retry(
        retry=retry_if_exception_type((APITimeoutError, APIConnectionError, InternalServerError)),
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
        if self.mock_mode:
            return self._mock_response(user_prompt, json_mode)

        response_format = {"type": "json_object"} if json_mode else None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
                timeout=timeout,
            )

            content = response.choices[0].message.content or ""
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
            raise RuntimeError("模型服务不可连接，请检查 LLM_BASE_URL 和云端网络连通性。") from exc
        except Exception as exc:
            logger.warning(
                "LLM request failed for provider=%s model=%s: %s",
                self.provider,
                self.model or "<unset>",
                exc.__class__.__name__,
            )
            raise

    def _clean_content(self, content: str) -> str:
        if not content:
            return ""

        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S | re.I)
        content = content.strip()

        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.I)
            content = re.sub(r"\s*```$", "", content)

        return content.strip()

    def _mock_response(self, user_prompt: str, json_mode: bool) -> Any:
        if json_mode:
            return {
                "summary": f"系统当前处于 {self.provider} Mock 推理模式，基于规则和文档依据生成了解释。",
                "explanation": user_prompt[:300],
                "audit_focus": ["主营业务收入", "应收账款", "存货"],
                "procedures": ["执行截止测试", "复核回款情况", "实施存货监盘"],
            }
        return f"Mock 回答：{user_prompt[:400]}"
