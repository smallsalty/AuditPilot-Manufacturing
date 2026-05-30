from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


CANONICAL_RISK_KEYS = (
    "revenue_recognition",
    "receivable_recoverability",
    "inventory_impairment",
    "cashflow_quality",
    "financing_pressure",
    "governance_instability",
    "litigation_compliance",
    "internal_control_effectiveness",
    "related_party_transaction",
    "audit_opinion_issue",
    "market_signal_conflict",
)


@dataclass(frozen=True)
class RiskAgentSkill:
    key: str
    role: str
    input_format: str
    output_format: str
    classification_rules: str
    summary_format: str
    required_top_level_keys: tuple[str, ...] = ()
    required_item_keys: tuple[str, ...] = ()
    required_any_of: tuple[str, ...] = ()
    fixed_item_fields: tuple[tuple[str, Any], ...] = ()
    forbidden_item_fields: tuple[str, ...] = ()
    forbidden_item_values: tuple[tuple[str, Any], ...] = ()

    def output_contract(self) -> dict[str, Any]:
        return {
            "required_top_level_keys": list(self.required_top_level_keys),
            "required_item_keys": list(self.required_item_keys),
            "required_any_of": list(self.required_any_of),
            "fixed_item_fields": dict(self.fixed_item_fields),
            "forbidden_item_fields": list(self.forbidden_item_fields),
            "forbidden_item_values": dict(self.forbidden_item_values),
        }

    def prompt_contract(self) -> str:
        return (
            f"agent_skill={self.key}\n"
            f"role={self.role}\n"
            f"input_format={self.input_format}\n"
            f"output_format={self.output_format}\n"
            f"required_output_contract={json.dumps(self.output_contract(), ensure_ascii=False, sort_keys=True)}\n"
            f"classification_rules={self.classification_rules}\n"
            f"summary_format={self.summary_format}"
        )


class RiskAgentSkillRegistry:
    SKILLS: dict[str, RiskAgentSkill] = {
        "data_risk_analysis": RiskAgentSkill(
            key="data_risk_analysis",
            role="结构化财务数据风险分析 agent",
            input_format="输入为近4季或多期结构化指标行，字段至少包含 report_period、revenue、net_profit、deduct_net_profit、gross_margin、net_margin、profit_cash_content、ar_turnover、inventory_turnover、debt_ratio、interest_bearing_debt_ratio、expense_ratio、ocf、fixed_assets、roe，以及可用的龙头基准对比。",
            output_format="输出风险项数组；每项包含 rule_code、risk_name、risk_level、risk_score、judgment、evidence、periods、agent_skill。",
            classification_rules=f"只能映射到当前 canonical risk keys：{', '.join(CANONICAL_RISK_KEYS)}；数据波动优先归入 revenue_recognition、cashflow_quality、financing_pressure。",
            summary_format="judgment 使用“风险名称：高/中/低风险”；evidence 用一句具体指标证据，不写泛泛判断。",
            required_item_keys=("rule_code", "risk_name", "risk_level", "risk_score", "judgment", "evidence", "periods", "agent_skill"),
            fixed_item_fields=(("agent_skill", "data_risk_analysis"),),
        ),
        "document_risk_analysis": RiskAgentSkill(
            key="document_risk_analysis",
            role="非财报正文文档风险分析 agent",
            input_format="输入为清洗后的候选片段；年度报告或季度报告的财务报表、附注、指标片段不得进入本 agent。",
            output_format="输出 JSON 对象，顶层唯一 key 为 items；每项包含 title、summary、evidence_excerpt、extract_type、extract_family、risk_points、parameters。",
            classification_rules=f"只能基于候选片段事实判断；优先归入当前 canonical risk keys：{', '.join(CANONICAL_RISK_KEYS)}；不得把财报指标异常算作文档风险。",
            summary_format="summary 必须是一句话，只写风险点；不要复述背景，不要输出没有审计关注意义的常规经营亮点。",
            required_top_level_keys=("items",),
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("event_type", "opinion_type", "risk_points"),
            fixed_item_fields=(("parameters.analysis_stage", "core"),),
            forbidden_item_fields=("metric_name", "financial_topics", "note_refs"),
            forbidden_item_values=(
                ("extract_family", "financial_statement"),
                ("detail_level", "financial_deep_dive"),
                ("parameters.analysis_stage", "financial_subanalysis"),
            ),
        ),
        "announcement_risk_analysis": RiskAgentSkill(
            key="announcement_risk_analysis",
            role="公告风险分析 agent",
            input_format="输入为公告标题、标题分类、命中关键词、原摘要和公告正文。",
            output_format="输出严格 JSON 对象；包含 summary、key_facts、risk_points、audit_focus、involved_parties、amounts、dates、evidence_excerpt、severity、confidence。",
            classification_rules="key_facts 只能写正文事实；risk_points 只能写审计风险判断；不得凭标题或正文外信息补事实。",
            summary_format="summary 等于最核心风险点，最多100字；数组最多3条，每条不超过40字。",
            required_top_level_keys=("summary", "key_facts", "risk_points", "audit_focus", "evidence_excerpt"),
            required_item_keys=("summary", "evidence_excerpt"),
            required_any_of=("risk_points", "key_facts"),
        ),
        "financial_report_risk_analysis": RiskAgentSkill(
            key="financial_report_risk_analysis",
            role="财报风险分析 agent",
            input_format="输入只包含年报、季报、审计报告或内控报告中的财务报表、附注、关键审计事项、指标异常片段。",
            output_format="抽取阶段输出 items；每项包含 title、summary、evidence_excerpt、extract_family=financial_statement、metric_name、financial_topics、note_refs、detail_level=financial_deep_dive。",
            classification_rules=f"财报内容只进入财报专项分析；可映射到当前 canonical risk keys：{', '.join(CANONICAL_RISK_KEYS)}；不得反向计入文档风险。",
            summary_format="摘要必须做聚合判断，用2-3句说明异常集中指标、可能含义和审计关注点；不要逐条复制输入。",
            required_top_level_keys=("items",),
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("metric_name", "financial_topics", "note_refs"),
            fixed_item_fields=(
                ("extract_family", "financial_statement"),
                ("detail_level", "financial_deep_dive"),
                ("parameters.analysis_stage", "financial_subanalysis"),
            ),
        ),
    }

    @classmethod
    def get(cls, key: str) -> RiskAgentSkill:
        return cls.SKILLS[key]
