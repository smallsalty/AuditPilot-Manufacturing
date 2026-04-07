import json
import logging
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower().strip() or "minimax"
        self.model = settings.llm_model.strip()
        self.base_url = settings.llm_base_url.strip()
        self.mock_mode = not settings.llm_api_key
        self.client = None
        if not self.mock_mode:
            self.client = OpenAI(api_key=settings.llm_api_key, base_url=self.base_url)

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=True)
    def chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        timeout: float = 30.0,
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
            if json_mode:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            return content
        except Exception as exc:
            logger.warning(
                "LLM request failed for provider=%s model=%s: %s",
                self.provider,
                self.model or "<unset>",
                exc.__class__.__name__,
            )
            raise

    def _mock_response(self, user_prompt: str, json_mode: bool) -> Any:
        if json_mode:
            return {
                "summary": f"系统当前处于 {self.provider} Mock 推理模式，基于规则和文档证据生成了解释。",
                "explanation": user_prompt[:300],
                "audit_focus": ["主营业务收入", "应收账款", "存货"],
                "procedures": ["执行截止测试", "复核回款情况", "实施存货监盘"],
            }
        return f"Mock 回答：{user_prompt[:400]}"
