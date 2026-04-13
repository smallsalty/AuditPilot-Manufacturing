from __future__ import annotations

import re

from app.models import DocumentMeta, ReviewOverride


class DocumentClassifyService:
    CLASSIFICATION_VERSION = "document-classifier:v1"
    TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("internal_control_report", ("内部控制", "内控评价", "内控审计", "缺陷整改")),
        ("audit_report", ("审计报告", "关键审计事项", "保留意见", "无法表示意见", "强调事项")),
        ("annual_summary", ("年度报告摘要", "年报摘要")),
        ("annual_report", ("年度报告", "年报全文", "合并资产负债表", "利润表", "现金流量表")),
        ("announcement_event", ("回购", "可转债", "担保", "诉讼", "处罚", "问询", "关联交易", "高管", "董事会", "监事会")),
    ]

    def classify(self, document: DocumentMeta, text: str, override: ReviewOverride | None = None) -> tuple[str, str]:
        if override and override.override_value.get("classified_type"):
            return str(override.override_value["classified_type"]), "manual"

        existing = (document.classified_type or document.document_type or "").strip()
        if existing in {"annual_report", "annual_summary", "audit_report", "internal_control_report", "announcement_event", "general"}:
            return existing, "metadata"

        haystack = " ".join(
            [
                document.document_name or "",
                document.document_type or "",
                "\n".join(text.splitlines()[:30]),
            ]
        )
        normalized = re.sub(r"\s+", "", haystack).lower()
        for classified_type, keywords in self.TYPE_KEYWORDS:
            if any(keyword.lower() in normalized for keyword in keywords):
                return classified_type, "rule"
        return "general", "rule"
