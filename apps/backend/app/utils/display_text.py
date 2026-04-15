from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"^[\s\-_/|:：;,，。]+|[\s\-_/|:：;,，。]+$")
REPORT_TITLE_RE = re.compile(r"(20\d{2}年?(?:半年度|年度)?报告(?:摘要)?)")


def clean_display_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_RE.sub("", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    text = _collapse_duplicate_report_text(text)
    text = PUNCT_RE.sub("", text).strip()
    return text


def clean_document_title(value: Any) -> str:
    text = clean_display_text(value)
    if not text:
        return ""
    match = REPORT_TITLE_RE.search(text)
    if match:
        suffix = text[match.end() :].strip(" -_/|:：;,，。")
        if suffix and suffix not in {match.group(1), "摘要"}:
            return f"{match.group(1)} {suffix}".strip()
        return match.group(1)
    return text


def clean_file_name_like(value: Any, fallback_suffix: str = ".pdf") -> str:
    raw = clean_document_title(value)
    if not raw:
        return f"document{fallback_suffix}"
    suffix = Path(raw).suffix
    if suffix:
        stem = clean_document_title(Path(raw).stem)
        return f"{stem}{suffix}" if stem else Path(raw).name
    return f"{raw}{fallback_suffix}"


def _collapse_duplicate_report_text(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) < 4:
        return cleaned
    for size in range(min(len(cleaned) // 2, 80), 3, -1):
        prefix = cleaned[:size]
        if prefix and cleaned == prefix * (len(cleaned) // len(prefix)) and len(cleaned) % len(prefix) == 0:
            return prefix
    match = re.match(r"^(.{3,80}?)(?:\1)+$", cleaned)
    if match:
        return match.group(1).strip()
    report_match = REPORT_TITLE_RE.search(cleaned)
    if report_match:
        report_text = report_match.group(1)
        occurrences = cleaned.count(report_text)
        if occurrences > 1:
            return report_text + cleaned.split(report_text)[-1]
    return cleaned
