from __future__ import annotations

import logging
import re
from typing import Any

from app.ai.llm_client import LLMClient


logger = logging.getLogger(__name__)


class EvidenceSummaryService:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def summarize_evidence(
        self,
        *,
        title: str | None,
        text: str | None,
        evidence_type: str | None = None,
        report_period: str | None = None,
        context: str | None = None,
    ) -> str:
        raw_text = self._clean_text(text)
        if not raw_text:
            return ""
        if not self._needs_model_summary(raw_text):
            return self._to_single_sentence(raw_text)
        if self.llm_client.config_error:
            return self._fallback(raw_text)

        system_prompt = (
            "你是上市公司审计证据摘要助手。"
            "请把输入证据压缩成一句中文摘要，保留关键事实，不要抄整行表格，"
            "不要输出“证据摘要”这类标签，不要分点，不要超过60字。"
        )
        user_prompt = (
            f"标题：{self._clean_text(title)}\n"
            f"证据类型：{self._clean_text(evidence_type)}\n"
            f"期间：{self._clean_text(report_period)}\n"
            f"上下文：{self._clean_text(context)}\n"
            f"原始证据：{raw_text}\n"
            "请只返回一句摘要。"
        )
        try:
            result = self.llm_client.chat_completion(
                system_prompt,
                user_prompt,
                json_mode=False,
                request_kind="evidence_summary",
                metadata={
                    "evidence_type": evidence_type or "",
                    "context_variant": "single_sentence_summary",
                },
                max_tokens=120,
                max_attempts=1,
            )
            summarized = self._clean_text(result)
            if summarized:
                return self._to_single_sentence(summarized)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "evidence summary generation failed evidence_type=%s title=%s error=%s",
                evidence_type,
                self._clean_text(title),
                exc,
            )
        return self._fallback(raw_text)

    def _needs_model_summary(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return False
        if len(compact) <= 28 and re.search(r"[。！？；]", compact):
            return False
        digit_chars = sum(1 for char in compact if char.isdigit())
        digit_ratio = digit_chars / max(len(compact), 1)
        if "\n" in text or "\t" in text:
            return True
        if digit_ratio >= 0.28:
            return True
        if len(compact) >= 42 and not re.search(r"[。！？；]", compact):
            return True
        if re.search(r"[%％]|(?=.*\d)(?=.*[,，])|[()（）]|[-]{2,}|[|/]{2,}", text):
            return True
        return False

    def _fallback(self, text: str) -> str:
        return self._to_single_sentence(text)

    def _to_single_sentence(self, text: str) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return ""
        cleaned = re.sub(r"^(证据摘要|摘要|说明)[:：]\s*", "", cleaned, flags=re.I)
        parts = re.split(r"[。！？；\n\r]+", cleaned)
        first = next((part.strip(" ，,;；") for part in parts if part.strip(" ，,;；")), cleaned)
        first = re.sub(r"\s+", " ", first).strip(" ，,;；。！？")
        if not first:
            return ""
        if len(first) > 60:
            first = first[:60].rstrip(" ，,;；")
        return first

    def _clean_text(self, value: Any) -> str:
        text = str(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
