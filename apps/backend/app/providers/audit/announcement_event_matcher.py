from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.providers.audit.cninfo_keywords import CNINFO_TITLE_ONLY_KEYWORDS


@dataclass(frozen=True)
class AnnouncementEventDefinition:
    category_code: str
    category_name: str
    event_code: str
    event_name: str
    canonical_risk_key: str
    risk_category: str
    default_risk_level: str
    base_weight: float
    priority: int
    focus_accounts: tuple[str, ...]
    focus_processes: tuple[str, ...]
    recommended_procedures: tuple[str, ...]
    evidence_types: tuple[str, ...]
    rationale: str


class AnnouncementEventMatcher:
    SUPPORTED_RISK_CATEGORY_CODES = {
        "regulatory_litigation",
        "accounting_audit",
        "fund_occupation_related_party_guarantee",
        "debt_liquidity_default",
        "equity_control_pledge",
        "performance_revision_impairment",
        "governance_personnel_internal_control",
    }

    CATEGORY_DEFINITIONS = {
        "regulatory_litigation": AnnouncementEventDefinition(
            category_code="regulatory_litigation",
            category_name="监管处罚与诉讼仲裁",
            event_code="ANNOUNCEMENT_REGULATORY_LITIGATION",
            event_name="监管处罚与诉讼仲裁风险",
            canonical_risk_key="announcement_regulatory_litigation",
            risk_category="合规风险",
            default_risk_level="high",
            base_weight=1.18,
            priority=100,
            focus_accounts=("营业收入", "预计负债", "其他应付款"),
            focus_processes=("收入确认", "信息披露", "法务合规"),
            recommended_procedures=(
                "复核监管函件、诉讼文件与公司披露的一致性",
                "检查重大诉讼、处罚事项是否完整计提和披露",
                "结合管理层访谈评估舞弊动机与重大错报风险",
            ),
            evidence_types=("announcement_event", "penalty_event", "management_interview"),
            rationale="监管处罚、立案和诉讼事项通常指向信息披露合规、收入确认口径或管理层舞弊风险，需要提高实质性程序强度。",
        ),
        "accounting_audit": AnnouncementEventDefinition(
            category_code="accounting_audit",
            category_name="会计差错与审计意见",
            event_code="ANNOUNCEMENT_ACCOUNTING_AUDIT",
            event_name="会计差错与审计意见风险",
            canonical_risk_key="announcement_accounting_audit",
            risk_category="合规风险",
            default_risk_level="high",
            base_weight=1.12,
            priority=95,
            focus_accounts=("期初余额", "营业收入", "资产减值"),
            focus_processes=("会计估计", "期初审计衔接", "内部控制"),
            recommended_procedures=(
                "复核差错更正口径及追溯调整依据",
                "检查非标审计意见涉及事项是否已在本期整改",
                "针对内控缺陷增加穿行测试和控制测试",
            ),
            evidence_types=("announcement_event", "risk_rule", "uploaded_document"),
            rationale="会计差错更正和非标审计意见通常意味着财务报告可靠性下降，需要重估期初余额、会计估计和持续经营判断。",
        ),
        "fund_occupation_related_party_guarantee": AnnouncementEventDefinition(
            category_code="fund_occupation_related_party_guarantee",
            category_name="资金占用、关联交易与担保",
            event_code="ANNOUNCEMENT_FUND_OCCUPATION_GUARANTEE",
            event_name="资金占用、关联交易与担保风险",
            canonical_risk_key="announcement_related_party_guarantee",
            risk_category="合规风险",
            default_risk_level="high",
            base_weight=1.14,
            priority=90,
            focus_accounts=("其他应收款", "其他应付款", "预计负债"),
            focus_processes=("关联方识别", "资金往来", "担保管理"),
            recommended_procedures=(
                "核对关联方名单与资金往来台账",
                "检查担保合同、董事会审批和信息披露是否完整",
                "对异常往来执行函证和穿透核查",
            ),
            evidence_types=("announcement_event", "risk_rule", "bank_statement"),
            rationale="资金占用、关联交易和违规担保会直接影响关联方披露、或有负债完整性以及资金真实流向，应提高关联方和担保程序覆盖率。",
        ),
        "debt_liquidity_default": AnnouncementEventDefinition(
            category_code="debt_liquidity_default",
            category_name="债务逾期、违约与流动性风险",
            event_code="ANNOUNCEMENT_DEBT_LIQUIDITY_DEFAULT",
            event_name="债务逾期与流动性风险",
            canonical_risk_key="announcement_debt_liquidity",
            risk_category="财务风险",
            default_risk_level="high",
            base_weight=1.08,
            priority=85,
            focus_accounts=("短期借款", "长期借款", "应付债券"),
            focus_processes=("持续经营评估", "债务管理", "现金流预测"),
            recommended_procedures=(
                "复核债务到期结构及续贷安排",
                "测试资产负债表日后偿债情况和违约条款触发情况",
                "重新评估持续经营假设和资产减值迹象",
            ),
            evidence_types=("announcement_event", "financial_indicator", "bank_statement"),
            rationale="债务逾期和流动性风险会直接影响持续经营假设、债务分类和减值测试，需要结合偿债安排重新评估关键判断。",
        ),
        "equity_control_pledge": AnnouncementEventDefinition(
            category_code="equity_control_pledge",
            category_name="股权变动、质押冻结与控制权风险",
            event_code="ANNOUNCEMENT_EQUITY_CONTROL_PLEDGE",
            event_name="股权变动与控制权风险",
            canonical_risk_key="announcement_equity_control_pledge",
            risk_category="经营风险",
            default_risk_level="medium",
            base_weight=0.96,
            priority=80,
            focus_accounts=("资本公积", "长期股权投资", "其他权益工具"),
            focus_processes=("治理结构", "重大事项披露", "期后事项"),
            recommended_procedures=(
                "核查控制权变更、质押冻结及相关披露",
                "复核是否触发期后事项、持续经营或治理层变更影响",
                "结合董事会、股东大会资料评估治理稳定性",
            ),
            evidence_types=("announcement_event", "uploaded_document", "management_interview"),
            rationale="控制权变动、股份质押冻结会影响治理稳定性和重大事项披露，需要审计上关注期后事项和管理层权责变化。",
        ),
        "performance_revision_impairment": AnnouncementEventDefinition(
            category_code="performance_revision_impairment",
            category_name="业绩修正、减值与非经常性损益",
            event_code="ANNOUNCEMENT_PERFORMANCE_IMPAIRMENT",
            event_name="业绩修正与减值风险",
            canonical_risk_key="announcement_performance_revision_impairment",
            risk_category="财务风险",
            default_risk_level="medium",
            base_weight=0.94,
            priority=70,
            focus_accounts=("资产减值损失", "商誉", "营业外收入"),
            focus_processes=("减值测试", "利润分析", "非经常性损益识别"),
            recommended_procedures=(
                "复核业绩修正口径及关键假设变化",
                "检查减值测试模型、参数和管理层偏差",
                "分析政府补助、非经常性损益对利润质量的影响",
            ),
            evidence_types=("announcement_event", "financial_indicator", "uploaded_document"),
            rationale="业绩修正和减值公告往往指向利润质量不稳，需要重点复核减值测试、非经常性损益和业绩调节风险。",
        ),
        "governance_personnel_internal_control": AnnouncementEventDefinition(
            category_code="governance_personnel_internal_control",
            category_name="治理异常、人员变动与内控事件",
            event_code="ANNOUNCEMENT_GOVERNANCE_INTERNAL_CONTROL",
            event_name="治理异常与内控风险",
            canonical_risk_key="announcement_governance_internal_control",
            risk_category="合规风险",
            default_risk_level="medium",
            base_weight=0.92,
            priority=65,
            focus_accounts=("管理费用", "其他应收款", "印章及合同档案"),
            focus_processes=("治理层沟通", "内部控制", "关键岗位交接"),
            recommended_procedures=(
                "评估关键岗位变动对财务关闭和审批链的影响",
                "针对内控缺陷补充控制测试和管理层访谈",
                "检查印章、资料失控等事项是否影响凭证真实性",
            ),
            evidence_types=("announcement_event", "management_interview", "uploaded_document"),
            rationale="治理异常和关键人员变动会削弱控制执行，影响管理层声明可信度和关键业务流程的稳定性。",
        ),
    }

    KEYWORD_SEVERITY_OVERRIDES = {
        "regulatory_litigation": {
            "立案": "high",
            "行政处罚": "high",
            "处罚决定": "high",
            "处罚事先告知书": "high",
            "纪律处分": "high",
            "问询函": "medium",
            "监管措施": "medium",
        },
        "accounting_audit": {
            "非标审计意见": "high",
            "无法表示意见": "high",
            "否定意见": "high",
            "保留意见": "high",
            "会计差错更正": "high",
            "内部控制缺陷": "medium",
        },
        "fund_occupation_related_party_guarantee": {
            "资金占用": "high",
            "违规担保": "high",
            "担保": "medium",
            "关联交易": "medium",
        },
        "debt_liquidity_default": {
            "债务逾期": "high",
            "违约": "high",
            "未能清偿": "high",
            "重整": "high",
            "流动性风险": "medium",
        },
        "equity_control_pledge": {
            "控制权变更": "high",
            "实际控制人变更": "high",
            "控股股东变更": "high",
            "冻结": "high",
            "股权质押": "medium",
            "减持": "medium",
        },
        "performance_revision_impairment": {
            "业绩修正": "medium",
            "减值": "medium",
            "商誉减值": "high",
            "亏损": "medium",
        },
        "governance_personnel_internal_control": {
            "失控": "high",
            "拒绝配合审计": "high",
            "内控缺陷": "medium",
            "高管变动": "medium",
        },
    }

    def normalize_text(self, value: str) -> str:
        normalized = str(value or "").strip().upper()
        normalized = normalized.replace("\uff08", "(").replace("\uff09", ")")
        normalized = normalized.replace("\u3010", "[").replace("\u3011", "]")
        normalized = normalized.replace("-", "").replace("_", "")
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def match_title_categories(self, title: str) -> list[dict[str, Any]]:
        normalized_title = self.normalize_text(title)
        matches: list[dict[str, Any]] = []
        for category in self._prepared_categories():
            aliased_title = self._apply_aliases(normalized_title, category["alias_replacements"])
            if any(keyword in aliased_title for keyword in category["exclude_keywords_normalized"]):
                continue
            matched_keywords = [
                display_keyword
                for normalized_keyword, display_keyword in category["effective_keywords"]
                if normalized_keyword and normalized_keyword in aliased_title
            ]
            if not matched_keywords:
                continue
            matches.append(
                {
                    "category_code": category["category_code"],
                    "category_name": category["category_name"],
                    "matched_keywords": self._dedupe_strings(matched_keywords),
                    "title": title,
                }
            )
        return matches

    def select_primary_match(self, title: str, matches: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        matches = matches if matches is not None else self.match_title_categories(title)
        if not matches:
            return None
        enriched = []
        for match in matches:
            definition = self.CATEGORY_DEFINITIONS.get(match["category_code"])
            if definition is None:
                continue
            enriched.append((match, definition))
        if not enriched:
            return None
        enriched.sort(
            key=lambda item: (
                -len(item[0]["matched_keywords"]),
                -item[1].priority,
                item[1].category_name,
            )
        )
        primary_match, definition = enriched[0]
        risk_level = self._resolve_risk_level(definition, primary_match["matched_keywords"])
        secondary_categories = [item[1].category_name for item in enriched[1:]]
        return {
            "category_code": definition.category_code,
            "category_name": definition.category_name,
            "event_code": definition.event_code,
            "event_category": definition.category_name,
            "event_name": definition.event_name,
            "canonical_risk_key": definition.canonical_risk_key,
            "risk_category": definition.risk_category,
            "risk_level": risk_level,
            "matched_keywords": primary_match["matched_keywords"],
            "source_title": title,
            "secondary_categories": self._dedupe_strings(secondary_categories),
        }

    def category_definition(self, category_code: str) -> AnnouncementEventDefinition | None:
        return self.CATEGORY_DEFINITIONS.get(category_code)

    def _resolve_risk_level(self, definition: AnnouncementEventDefinition, matched_keywords: list[str]) -> str:
        overrides = self.KEYWORD_SEVERITY_OVERRIDES.get(definition.category_code, {})
        level_rank = {"low": 1, "medium": 2, "high": 3}
        highest = definition.default_risk_level
        for keyword in matched_keywords:
            override = overrides.get(keyword)
            if override and level_rank.get(override, 0) > level_rank.get(highest, 0):
                highest = override
        return highest

    @classmethod
    @lru_cache(maxsize=1)
    def _prepared_categories(cls) -> tuple[dict[str, Any], ...]:
        prepared: list[dict[str, Any]] = []
        for category in CNINFO_TITLE_ONLY_KEYWORDS:
            alias_replacements: list[tuple[str, str]] = []
            effective_keywords: list[tuple[str, str]] = []
            seen_keywords: set[str] = set()

            for alias_key, alias_values in category["aliases"].items():
                alias_key_normalized = cls._normalize_keyword(alias_key)
                if alias_key_normalized and alias_key_normalized not in seen_keywords:
                    effective_keywords.append((alias_key_normalized, alias_key))
                    seen_keywords.add(alias_key_normalized)
                for alias_value in sorted(alias_values, key=len, reverse=True):
                    alias_normalized = cls._normalize_keyword(alias_value)
                    if alias_normalized:
                        alias_replacements.append((alias_normalized, alias_key_normalized))

            for keyword in category["title_keywords"]:
                keyword_normalized = cls._normalize_keyword(keyword)
                if keyword_normalized and keyword_normalized not in seen_keywords:
                    effective_keywords.append((keyword_normalized, keyword))
                    seen_keywords.add(keyword_normalized)

            alias_replacements.sort(key=lambda item: len(item[0]), reverse=True)
            prepared.append(
                {
                    "category_code": category["category_code"],
                    "category_name": category["category_name"],
                    "alias_replacements": tuple(alias_replacements),
                    "effective_keywords": tuple(effective_keywords),
                    "exclude_keywords_normalized": tuple(
                        cls._normalize_keyword(keyword) for keyword in category["exclude_keywords"]
                    ),
                }
            )
        return tuple(prepared)

    @classmethod
    def _normalize_keyword(cls, value: str) -> str:
        return cls().normalize_text(value)

    @staticmethod
    def _apply_aliases(normalized_title: str, alias_replacements: tuple[tuple[str, str], ...]) -> str:
        canonical_title = normalized_title
        for alias_normalized, canonical_normalized in alias_replacements:
            canonical_title = canonical_title.replace(alias_normalized, canonical_normalized)
        return canonical_title

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return deduped
