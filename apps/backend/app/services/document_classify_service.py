from __future__ import annotations

import re

from app.models import DocumentMeta, ReviewOverride


class DocumentClassifyService:
    CLASSIFICATION_VERSION = "document-classifier:v1"
    STRONG_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
        "internal_control_report": (
            "内部控制评价报告",
            "内部控制审计报告",
            "内部控制自我评价",
            "内部控制有效性",
            "重大缺陷",
            "重要缺陷",
            "缺陷整改",
            "整改",
        ),
        "audit_report": (
            "审计报告",
            "关键审计事项",
            "强调事项",
            "保留意见",
            "无法表示意见",
            "否定意见",
            "持续经营",
        ),
        "annual_summary": ("年度报告摘要", "年报摘要"),
        "annual_report": ("年度报告", "年报全文", "合并资产负债表", "利润表", "现金流量表"),
        "announcement_event": ("回购", "可转债", "担保", "诉讼", "处罚", "问询", "关联交易", "高管变动", "董事会决议", "监事会决议"),
    }
    TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("internal_control_report", STRONG_TYPE_KEYWORDS["internal_control_report"]),
        ("audit_report", STRONG_TYPE_KEYWORDS["audit_report"]),
        ("annual_summary", STRONG_TYPE_KEYWORDS["annual_summary"]),
        ("annual_report", STRONG_TYPE_KEYWORDS["annual_report"]),
        ("announcement_event", STRONG_TYPE_KEYWORDS["announcement_event"]),
    ]

    def classify(self, document: DocumentMeta, text: str, override: ReviewOverride | None = None) -> tuple[str, str]:
        if override and override.override_value.get("classified_type"):
            return str(override.override_value["classified_type"]), "manual"

        haystack = " ".join(
            [
                document.document_name or "",
                document.document_type or "",
                "\n".join(text.splitlines()[:30]),
            ]
        )
        normalized = re.sub(r"\s+", "", haystack).lower()
        if self._matches_strong_type(normalized, "internal_control_report"):
            return "internal_control_report", "rule"
        if self._matches_strong_type(normalized, "audit_report"):
            return "audit_report", "rule"
        for classified_type, keywords in self.TYPE_KEYWORDS:
            if classified_type in {"internal_control_report", "audit_report"}:
                continue
            if any(keyword.lower() in normalized for keyword in keywords):
                return classified_type, "rule"
        return "general", "rule"

    def _matches_strong_type(self, normalized: str, classified_type: str) -> bool:
        keywords = self.STRONG_TYPE_KEYWORDS.get(classified_type, ())
        if not keywords:
            return False
        return any(keyword.lower() in normalized for keyword in keywords)
