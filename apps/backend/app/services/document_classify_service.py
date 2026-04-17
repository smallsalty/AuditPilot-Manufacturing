from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from app.models import DocumentMeta, ReviewOverride


@dataclass(frozen=True)
class ClassificationSignal:
    signal_source: str
    matched_value: str
    weight: float


@dataclass(frozen=True)
class DocumentClassificationResult:
    classified_type: str
    classification_source: str
    classification_reason: str
    classification_signals: list[dict[str, Any]]

    @classmethod
    def from_signals(
        cls,
        *,
        classified_type: str,
        classification_source: str,
        classification_reason: str,
        classification_signals: list[ClassificationSignal],
    ) -> "DocumentClassificationResult":
        return cls(
            classified_type=classified_type,
            classification_source=classification_source,
            classification_reason=classification_reason,
            classification_signals=[asdict(signal) for signal in classification_signals],
        )


class DocumentClassifyService:
    CLASSIFICATION_VERSION = "document-classifier:v2"
    RECLASSIFY_THRESHOLD = 2.4
    SUPPORTED_TYPES = {
        "annual_report",
        "annual_summary",
        "audit_report",
        "internal_control_report",
        "announcement_event",
        "general",
    }
    SYNC_TYPE_ALIASES = {
        "interim_report": "general",
        "quarter_report": "general",
        "special_report": "general",
    }
    TITLE_MATCH_TO_TYPE = {
        "regulatory_litigation": "announcement_event",
        "accounting_audit": "announcement_event",
        "fund_occupation_related_party_guarantee": "announcement_event",
        "debt_liquidity_default": "announcement_event",
        "equity_control_pledge": "announcement_event",
        "performance_revision_impairment": "announcement_event",
        "major_transactions_financing": "announcement_event",
        "governance_personnel_internal_control": "announcement_event",
    }
    TYPE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
        "internal_control_report": {
            "title": (
                "内部控制审计报告",
                "内部控制评价报告",
                "内部控制自我评价报告",
                "内控审计报告",
                "内控评价报告",
            ),
            "body": (
                "内部控制审计意见",
                "内部控制缺陷",
                "重大缺陷",
                "重要缺陷",
                "缺陷整改",
                "内部控制有效",
                "内部控制无效",
            ),
        },
        "audit_report": {
            "title": (
                "审计报告",
                "非标准审计意见",
                "保留意见",
                "否定意见",
                "无法表示意见",
            ),
            "body": (
                "审计意见",
                "关键审计事项",
                "强调事项",
                "持续经营重大不确定性",
                "保留意见",
                "否定意见",
                "无法表示意见",
            ),
        },
        "annual_summary": {
            "title": (
                "年度报告摘要",
                "年报摘要",
            ),
            "body": (
                "主要会计数据",
                "主要财务指标",
                "年度报告摘要",
            ),
        },
        "annual_report": {
            "title": (
                "年度报告",
                "年报全文",
            ),
            "body": (
                "合并资产负债表",
                "合并利润表",
                "合并现金流量表",
                "财务报表附注",
                "年度报告全文",
            ),
        },
        "announcement_event": {
            "title": (
                "问询函",
                "关注函",
                "警示函",
                "监管函",
                "处罚",
                "立案调查",
                "诉讼",
                "仲裁",
                "担保",
                "资金占用",
                "关联交易",
                "股权质押",
                "股份冻结",
                "实际控制人变更",
                "减持",
                "增持",
                "回购",
                "业绩预告修正",
                "计提减值准备",
                "商誉减值",
                "董事辞职",
                "高级管理人员辞职",
                "内部控制缺陷",
            ),
            "body": (
                "问询函",
                "关注函",
                "处罚决定",
                "立案调查",
                "重大诉讼",
                "违规担保",
                "非经营性资金占用",
                "关联交易",
                "债务逾期",
                "股权质押",
                "股份冻结",
                "控制权变更",
                "业绩预告修正",
                "计提减值准备",
                "商誉减值",
                "高管变动",
                "内部控制缺陷",
            ),
        },
    }

    def classify(
        self,
        document: DocumentMeta,
        text: str,
        override: ReviewOverride | None = None,
    ) -> DocumentClassificationResult:
        if override and override.override_value.get("classified_type"):
            classified_type = self._normalize_type(str(override.override_value["classified_type"]))
            return DocumentClassificationResult.from_signals(
                classified_type=classified_type,
                classification_source="manual_override",
                classification_reason="使用人工修正的文档分类结果。",
                classification_signals=[
                    ClassificationSignal(
                        signal_source="manual",
                        matched_value=classified_type,
                        weight=10.0,
                    )
                ],
            )

        title = str(document.document_name or "").strip()
        sync_type = self._normalize_type(document.classified_type or document.document_type)
        body_head_lines = self._body_head_lines(text)
        body_head = "\n".join(body_head_lines)
        title_matches = self._extract_title_matches(document)

        scores: dict[str, float] = {}
        signals_by_type: dict[str, list[ClassificationSignal]] = {}

        self._collect_keyword_signals(scores, signals_by_type, title, signal_source="title", weight=1.6, use_title_rules=True)
        self._collect_keyword_signals(scores, signals_by_type, body_head, signal_source="body_head", weight=1.0, use_title_rules=False)

        for match in title_matches:
            category_code = str(match.get("category_code") or "").strip()
            mapped_type = self.TITLE_MATCH_TO_TYPE.get(category_code)
            if not mapped_type:
                continue
            signal = ClassificationSignal(
                signal_source="title_matches",
                matched_value=category_code,
                weight=1.2,
            )
            scores[mapped_type] = scores.get(mapped_type, 0.0) + signal.weight
            signals_by_type.setdefault(mapped_type, []).append(signal)

        best_type = None
        best_score = 0.0
        for candidate_type, score in scores.items():
            if score > best_score:
                best_type = candidate_type
                best_score = score

        if best_type and best_score >= self.RECLASSIFY_THRESHOLD:
            signals = signals_by_type.get(best_type, [])
            return DocumentClassificationResult.from_signals(
                classified_type=best_type,
                classification_source="reclassified_from_title_and_body",
                classification_reason=self._build_reason(best_type, signals, sync_type),
                classification_signals=signals,
            )

        if sync_type and sync_type in self.SUPPORTED_TYPES:
            return DocumentClassificationResult.from_signals(
                classified_type=sync_type,
                classification_source="synced_type_fallback",
                classification_reason=f"标题和正文信号不足，回退为同步阶段类型 {sync_type}。",
                classification_signals=[
                    ClassificationSignal(
                        signal_source="sync_type",
                        matched_value=sync_type,
                        weight=1.0,
                    )
                ],
            )

        return DocumentClassificationResult.from_signals(
            classified_type="general",
            classification_source="default_general",
            classification_reason="未命中足够的标题或正文信号，默认归为 general。",
            classification_signals=[],
        )

    def _collect_keyword_signals(
        self,
        scores: dict[str, float],
        signals_by_type: dict[str, list[ClassificationSignal]],
        source_text: str,
        *,
        signal_source: str,
        weight: float,
        use_title_rules: bool,
    ) -> None:
        normalized = self._normalize_text(source_text)
        if not normalized:
            return
        field_name = "title" if use_title_rules else "body"
        for classified_type, rules in self.TYPE_RULES.items():
            for keyword in rules.get(field_name, ()):
                if self._normalize_text(keyword) not in normalized:
                    continue
                signal = ClassificationSignal(
                    signal_source=signal_source,
                    matched_value=keyword,
                    weight=weight,
                )
                scores[classified_type] = scores.get(classified_type, 0.0) + signal.weight
                signals_by_type.setdefault(classified_type, []).append(signal)

    def _extract_title_matches(self, document: DocumentMeta) -> list[dict[str, Any]]:
        metadata = dict(document.metadata_json or {})
        direct = metadata.get("title_matches")
        if isinstance(direct, list):
            return [item for item in direct if isinstance(item, dict)]
        sync_diagnostics = metadata.get("sync_diagnostics") or {}
        if isinstance(sync_diagnostics, dict):
            matches = sync_diagnostics.get("title_matches")
            if isinstance(matches, list):
                return [item for item in matches if isinstance(item, dict)]
        return []

    def _body_head_lines(self, text: str, limit: int = 40) -> list[str]:
        lines = []
        for raw in str(text or "").splitlines():
            item = raw.strip()
            if not item:
                continue
            lines.append(item)
            if len(lines) >= limit:
                break
        return lines

    def _build_reason(
        self,
        classified_type: str,
        signals: list[ClassificationSignal],
        sync_type: str | None,
    ) -> str:
        signal_values = [signal.matched_value for signal in signals[:4]]
        signal_text = "、".join(signal_values) if signal_values else "无明确信号"
        if sync_type and sync_type != classified_type:
            return f"根据标题/正文信号重新判定为 {classified_type}，主要命中：{signal_text}；同步类型为 {sync_type}。"
        return f"根据标题/正文信号判定为 {classified_type}，主要命中：{signal_text}。"

    def _normalize_type(self, value: str | None) -> str:
        item = str(value or "").strip()
        if not item:
            return ""
        item = self.SYNC_TYPE_ALIASES.get(item, item)
        if item not in self.SUPPORTED_TYPES:
            return "general"
        return item

    def _normalize_text(self, value: str | None) -> str:
        normalized = re.sub(r"\s+", "", str(value or "")).lower()
        return normalized
