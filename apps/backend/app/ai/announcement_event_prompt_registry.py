from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnnouncementEventPromptSpec:
    prompt_template: str
    category_code: str
    category_label: str
    analysis_focus: str


class AnnouncementEventPromptRegistry:
    DEFAULT_CATEGORY = "general"
    SPECS: dict[str, AnnouncementEventPromptSpec] = {
        "regulatory_litigation": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:regulatory_litigation",
            category_code="regulatory_litigation",
            category_label="监管处罚、问询与诉讼仲裁",
            analysis_focus="识别监管机构、处罚或问询事项、诉讼仲裁阶段、涉案金额、整改要求、预计负债和信息披露影响。",
        ),
        "accounting_audit": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:accounting_audit",
            category_code="accounting_audit",
            category_label="会计差错、审计意见与财务报告可靠性",
            analysis_focus="识别会计差错更正、审计意见异常、内控缺陷、受影响报表项目、追溯调整和审计应对重点。",
        ),
        "fund_occupation_related_party_guarantee": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:fund_occupation_related_party_guarantee",
            category_code="fund_occupation_related_party_guarantee",
            category_label="资金占用、关联交易与担保",
            analysis_focus="识别关联方、资金占用或担保对象、交易/担保金额、审批程序、定价公允性、偿付或解除安排。",
        ),
        "debt_liquidity_default": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:debt_liquidity_default",
            category_code="debt_liquidity_default",
            category_label="债务逾期、违约与流动性风险",
            analysis_focus="识别债务规模、到期或违约状态、偿付安排、展期重组、持续经营风险和现金流压力。",
        ),
        "equity_control_pledge": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:equity_control_pledge",
            category_code="equity_control_pledge",
            category_label="股权控制、质押冻结与控制权变化",
            analysis_focus="识别控股股东/实控人变化、质押冻结比例、司法处置、控制权稳定性和治理影响。",
        ),
        "performance_revision_impairment": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:performance_revision_impairment",
            category_code="performance_revision_impairment",
            category_label="业绩修正、减值与非经常性损益",
            analysis_focus="识别业绩修正方向、减值资产、利润影响、非经常性损益、管理层估计和利润质量风险。",
        ),
        "governance_personnel_internal_control": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:governance_personnel_internal_control",
            category_code="governance_personnel_internal_control",
            category_label="治理异常、人员变动与内部控制",
            analysis_focus="识别关键岗位变动、辞任原因、交接安排、印章或资料失控、内控缺陷和治理稳定性影响。",
        ),
        "general": AnnouncementEventPromptSpec(
            prompt_template="announcement_event:general",
            category_code="general",
            category_label="公告事件",
            analysis_focus="识别公告披露的关键事实、涉及主体、金额日期、潜在财务报表影响和审计关注点。",
        ),
    }

    EVENT_TYPE_ALIASES = {
        "ANNOUNCEMENT_REGULATORY_LITIGATION": "regulatory_litigation",
        "ANNOUNCEMENT_ACCOUNTING_AUDIT": "accounting_audit",
        "ANNOUNCEMENT_FUND_OCCUPATION_GUARANTEE": "fund_occupation_related_party_guarantee",
        "ANNOUNCEMENT_DEBT_LIQUIDITY_DEFAULT": "debt_liquidity_default",
        "ANNOUNCEMENT_EQUITY_CONTROL_PLEDGE": "equity_control_pledge",
        "ANNOUNCEMENT_PERFORMANCE_IMPAIRMENT": "performance_revision_impairment",
        "ANNOUNCEMENT_GOVERNANCE_INTERNAL_CONTROL": "governance_personnel_internal_control",
        "regulatory_penalty": "regulatory_litigation",
    }

    @classmethod
    def resolve_category(cls, *, event_type: str | None, primary_match: dict[str, Any] | None) -> str:
        category = str((primary_match or {}).get("category_code") or "").strip()
        if category in cls.SPECS:
            return category
        event_name = str(event_type or "").strip()
        return cls.EVENT_TYPE_ALIASES.get(event_name, cls.EVENT_TYPE_ALIASES.get(event_name.upper(), cls.DEFAULT_CATEGORY))

    @classmethod
    def get_spec(cls, category_code: str) -> AnnouncementEventPromptSpec:
        return cls.SPECS.get(category_code, cls.SPECS[cls.DEFAULT_CATEGORY])

    @classmethod
    def build_prompts(
        cls,
        *,
        title: str,
        event_type: str,
        category_code: str,
        matched_keywords: list[str],
        body_text: str,
        fallback_summary: str,
    ) -> dict[str, Any]:
        spec = cls.get_spec(category_code)
        json_example = {
            "summary": "用一到两句话概括公告正文披露的核心事件和审计含义。",
            "key_facts": ["列出正文中的关键事实，不超过5条"],
            "risk_points": ["列出审计风险点，不超过5条"],
            "audit_focus": ["列出建议审计关注点或程序，不超过5条"],
            "involved_parties": ["涉及主体、监管机构、交易对手等"],
            "amounts": ["涉及金额、比例或数量"],
            "dates": ["关键日期"],
            "evidence_excerpt": "引用或转述最关键的一句正文证据。",
            "severity": "low|medium|high",
            "confidence": 0.0,
        }
        system_prompt = (
            "你是上市公司公告事件分析助手。只能基于给定公告标题和正文内容分析，不要编造正文外事实。"
            "请按事件类型提取结构化审计关注信息，返回严格 JSON 对象，不要输出 Markdown、代码块或额外解释。"
        )
        user_prompt = (
            f"公告标题：{title}\n"
            f"标题事件类型：{event_type}\n"
            f"标题分类：{spec.category_label}\n"
            f"命中关键词：{'、'.join(matched_keywords)}\n"
            f"分析重点：{spec.analysis_focus}\n"
            f"原摘要：{fallback_summary}\n"
            f"返回字段示例：{json.dumps(json_example, ensure_ascii=False)}\n"
            "要求：summary 必须是完整中文句子；key_facts、risk_points、audit_focus 必须基于正文；"
            "无法确认的字段返回空数组或 null。\n"
            f"公告正文：\n{body_text}"
        )
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_template": spec.prompt_template,
            "category_code": spec.category_code,
            "category_label": spec.category_label,
        }
