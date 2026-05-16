from __future__ import annotations

import logging
import re
from typing import Any

from app.ai.llm_client import LLMClient


logger = logging.getLogger(__name__)


class EvidenceSummaryService:
    MAX_EVIDENCE_SUMMARY_CHARS = 120
    LOW_INFORMATION_UNITS = {"元", "万元", "亿元", "%", "％", "股", "天", "年"}
    KNOWN_EVIDENCE_KEYWORDS = (
        "股份回购",
        "回购",
        "诉讼",
        "仲裁",
        "担保",
        "关联交易",
        "资金占用",
        "营业收入",
        "应收账款",
        "存货",
        "信用减值",
        "资产减值",
        "净利润",
        "现金分红",
        "内部控制",
        "审计意见",
        "保留意见",
        "问询",
        "处罚",
    )

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
        keywords: list[str] | None = None,
    ) -> str:
        raw_text = self._clean_text(text)
        if not raw_text:
            return ""
        context_text = self._clean_text(context)
        evidence_keywords = self._build_keywords(
            raw_text=raw_text,
            title=title,
            evidence_type=evidence_type,
            report_period=report_period,
            context=context,
            keywords=keywords,
        )
        if (
            context_text
            and context_text != raw_text
            and self._is_low_information_summary(raw_text, context_text, evidence_keywords)
        ):
            raw_text = f"{raw_text}。{context_text}"
            evidence_keywords = self._build_keywords(
                raw_text=raw_text,
                title=title,
                evidence_type=evidence_type,
                report_period=report_period,
                context=context,
                keywords=keywords,
            )
        preferred_sentence = self._select_key_sentence(raw_text, evidence_keywords)
        if preferred_sentence and self._sentence_score(preferred_sentence, evidence_keywords) > 0:
            return self._shorten_preserving_keywords(preferred_sentence, evidence_keywords)
        if not self._needs_model_summary(raw_text):
            return self._fallback(raw_text, evidence_keywords)
        if self.llm_client.config_error:
            return self._fallback(raw_text, evidence_keywords)

        system_prompt = (
            "你是上市公司审计证据摘要助手。"
            "请把输入证据压缩成一句中文摘要，保留关键事实，不要抄整行表格，"
            "必须保留关键数字、单位、主体和事件关键词，"
            "不要输出“证据摘要”这类标签，不要分点，不要超过120字。"
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
            if summarized and not self._is_low_information_summary(summarized, raw_text, evidence_keywords):
                return self._to_single_sentence(summarized, max_length=self.MAX_EVIDENCE_SUMMARY_CHARS)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "evidence summary generation failed evidence_type=%s title=%s error=%s",
                evidence_type,
                self._clean_text(title),
                exc,
            )
        return self._fallback(raw_text, evidence_keywords)

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

    def _fallback(self, text: str, keywords: list[str] | None = None) -> str:
        sentence = self._select_key_sentence(text, keywords or [])
        return self._shorten_preserving_keywords(sentence or text, keywords or [])

    def _to_single_sentence(self, text: str, max_length: int = MAX_EVIDENCE_SUMMARY_CHARS) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return ""
        cleaned = re.sub(r"^(证据摘要|摘要|说明)[:：]\s*", "", cleaned, flags=re.I)
        parts = re.split(r"[。！？；\n\r]+", cleaned)
        first = next((part.strip(" ，,;；") for part in parts if part.strip(" ，,;；")), cleaned)
        first = re.sub(r"\s+", " ", first).strip(" ，,;；。！？")
        if not first:
            return ""
        if len(first) > max_length:
            first = first[:max_length].rstrip(" ，,;；")
        return first

    def _build_keywords(
        self,
        *,
        raw_text: str,
        title: str | None,
        evidence_type: str | None,
        report_period: str | None,
        context: str | None,
        keywords: list[str] | None,
    ) -> list[str]:
        candidates: list[str] = []
        candidates.extend(keywords or [])
        candidates.extend([str(title or ""), str(evidence_type or ""), str(report_period or ""), str(context or "")])
        candidates.extend(keyword for keyword in self.KNOWN_EVIDENCE_KEYWORDS if keyword in raw_text)
        candidates.extend(self._extract_numeric_terms(raw_text))
        extracted: list[str] = []
        for candidate in candidates:
            text = self._clean_text(candidate)
            if not text:
                continue
            extracted.append(text)
            extracted.extend(self._extract_numeric_terms(text))
            extracted.extend(self._extract_chinese_terms(text))
        return self._dedupe_keywords(extracted)

    def _extract_numeric_terms(self, text: str) -> list[str]:
        pattern = r"\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[-至到]\s*\d+(?:,\d{3})*(?:\.\d+)?)?\s*(?:亿元|万元|元|股|%|％|个百分点)?"
        return [item.strip() for item in re.findall(pattern, str(text or "")) if item.strip()]

    def _extract_chinese_terms(self, text: str) -> list[str]:
        terms: list[str] = []
        for chunk in re.findall(r"[\u3400-\u9fff]{2,16}", str(text or "")):
            terms.append(chunk)
            for keyword in self.KNOWN_EVIDENCE_KEYWORDS:
                if keyword in chunk:
                    terms.append(keyword)
        return terms

    def _dedupe_keywords(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            text = self._clean_text(value).strip(" ，,;；。！？")
            if len(text) < 2 and not text.isdigit():
                continue
            if text not in deduped:
                deduped.append(text)
        return sorted(deduped, key=len, reverse=True)

    def _select_key_sentence(self, text: str, keywords: list[str]) -> str:
        sentences = self._split_sentences(text)
        if not sentences:
            return ""
        return max(sentences, key=lambda sentence: (self._sentence_score(sentence, keywords), len(sentence)))

    def _split_sentences(self, text: str) -> list[str]:
        cleaned = self._clean_text(text)
        if not cleaned:
            return []
        parts = re.split(r"(?<=[。！？；;])\s*|[\n\r]+", cleaned)
        sentences = [part.strip(" ，,;；。！？") for part in parts if part.strip(" ，,;；。！？")]
        return sentences or [cleaned]

    def _sentence_score(self, sentence: str, keywords: list[str]) -> int:
        score = 0
        compact = self._clean_text(sentence)
        for keyword in keywords:
            if keyword and keyword in compact:
                score += 3 if re.search(r"[\u3400-\u9fff]", keyword) else 2
        if re.search(r"\d", compact):
            score += 2
        if re.search(r"\d[\d,]*(?:\.\d+)?\s*(亿元|万元|元|股|%|％|个百分点)", compact):
            score += 3
        return score

    def _shorten_preserving_keywords(
        self,
        sentence: str,
        keywords: list[str],
        max_length: int | None = None,
    ) -> str:
        limit = max_length or self.MAX_EVIDENCE_SUMMARY_CHARS
        cleaned = self._to_single_sentence(sentence, max_length=max(len(sentence), limit))
        if len(cleaned) <= limit:
            return cleaned
        anchors = self._anchor_terms(cleaned, keywords)
        if not anchors:
            return cleaned[:limit].rstrip(" ，,;；")
        spans: list[tuple[int, int]] = []
        for term in anchors[:6]:
            index = cleaned.find(term)
            if index < 0:
                continue
            spans.append((max(0, index - 18), min(len(cleaned), index + len(term) + 24)))
        merged: list[tuple[int, int]] = []
        for start, end in sorted(spans):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        fragments = [cleaned[start:end].strip(" ，,;；") for start, end in merged if cleaned[start:end].strip(" ，,;；")]
        shortened = "…".join(fragments)
        if len(shortened) <= limit:
            return shortened
        return shortened[:limit].rstrip(" ，,;；")

    def _anchor_terms(self, sentence: str, keywords: list[str]) -> list[str]:
        numeric_terms = [term for term in self._extract_numeric_terms(sentence) if term in sentence]
        keyword_terms = [
            keyword
            for keyword in keywords
            if keyword in sentence and 2 <= len(keyword) <= 24 and re.search(r"[\u3400-\u9fff]", keyword)
        ]
        return self._dedupe_keywords(numeric_terms + keyword_terms)

    def _is_low_information_summary(self, summary: str, raw_text: str, keywords: list[str]) -> bool:
        compact = re.sub(r"\s+", "", self._clean_text(summary))
        if not compact:
            return True
        if compact in self.LOW_INFORMATION_UNITS:
            return True
        if re.fullmatch(r"\d+(?:\.\d+)?(?:亿元|万元|元|股|%|％)?", compact):
            return True
        has_keyword = any(keyword in compact for keyword in keywords if len(keyword) >= 2)
        if len(compact) <= 4 and not has_keyword:
            return True
        raw_numbers = self._extract_numeric_terms(raw_text)
        if raw_numbers and not any(number in compact for number in raw_numbers[:5]) and not has_keyword:
            return True
        return False

    def _clean_text(self, value: Any) -> str:
        text = str(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
