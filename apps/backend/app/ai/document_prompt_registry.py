from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentPromptSpec:
    prompt_template: str
    schema_name: str
    type_label: str
    type_rules: str
    json_example: dict[str, Any]
    required_item_keys: tuple[str, ...]
    required_any_of: tuple[str, ...] = ()


class DocumentPromptRegistry:
    COMMON_RULES = (
        "你是上市公司披露文件结构化抽取助手。"
        "只基于给出的候选片段抽取事实，不要补充候选片段之外的信息。"
        "只输出一个 JSON 对象，顶层唯一 key 为 items。"
        "不要输出 Markdown、代码块、解释、前后缀文字。"
        "字段缺失时使用 null、空字符串或空数组，不要编造。"
        "中文表达保持简洁，每条 summary 用一句话。"
    )

    SPECS: dict[str, DocumentPromptSpec] = {
        "annual_report": DocumentPromptSpec(
            prompt_template="document_extract:annual_report",
            schema_name="annual_report_extract_v1",
            type_label="年度报告",
            type_rules=(
                "聚焦经营变化、治理事项、异常事件、重大风险、审计重点。"
                "最多返回 3 条 items，只保留最高价值事项，不要重复输出相同事实。"
                "事项优先级依次为：重大资本动作、治理异常、审计与合规异常、明显财务异常。"
                "普通增长、常规盈利改善、常规分红、常规经营亮点不得进入结果；只有明确异常或具有审计关注意义时才允许保留。"
                "严禁为了凑满条数输出低价值事项，输出必须是完整闭合 JSON。"
            ),
            json_example={
                "items": [
                    {
                        "title": "管理层重大变动",
                        "summary": "公告披露财务负责人辞职，治理稳定性需关注。",
                        "evidence_excerpt": "公司财务负责人于报告期内辞职。",
                        "extract_type": "event_fact",
                        "extract_family": "announcement_event",
                        "event_type": "executive_change",
                        "severity": "medium",
                        "risk_points": ["治理稳定性", "关键岗位变动"],
                        "fact_tags": ["governance"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("event_type", "opinion_type", "metric_name", "risk_points"),
        ),
        "annual_summary": DocumentPromptSpec(
            prompt_template="document_extract:annual_summary",
            schema_name="annual_summary_extract_v1",
            type_label="年度报告摘要",
            type_rules=(
                "聚焦关键财务变化、异常事项和需要继续下钻的风险线索。"
                "尽量保留指标名称、数值和附注线索。"
            ),
            json_example={
                "items": [
                    {
                        "title": "盈利能力波动",
                        "summary": "摘要披露净利润明显下滑，需结合附注检查原因。",
                        "evidence_excerpt": "归属于上市公司股东的净利润同比下降 38.4%。",
                        "extract_type": "document_issue",
                        "extract_family": "financial_statement",
                        "event_type": "financial_anomaly",
                        "metric_name": "净利润",
                        "metric_value": -38.4,
                        "metric_unit": "%",
                        "financial_topics": ["净利润"],
                        "risk_points": ["盈利能力波动"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("event_type", "metric_name", "financial_topics", "risk_points"),
        ),
        "audit_report": DocumentPromptSpec(
            prompt_template="document_extract:audit_report",
            schema_name="audit_report_extract_v1",
            type_label="审计报告",
            type_rules=(
                "聚焦审计意见、关键审计事项、强调事项、持续经营不确定性。"
                "优先保留 opinion_type、结论和受影响范围。"
            ),
            json_example={
                "items": [
                    {
                        "title": "保留意见",
                        "summary": "审计报告出具保留意见，需针对受限事项追加程序。",
                        "evidence_excerpt": "我们对上述事项发表保留意见。",
                        "extract_type": "document_issue",
                        "extract_family": "opinion_conclusion",
                        "event_type": "audit_opinion_issue",
                        "opinion_type": "qualified_opinion",
                        "conclusion": "审计证据受限，形成保留意见。",
                        "affected_scope": "收入确认与相关往来",
                        "risk_points": ["审计意见异常"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("opinion_type", "event_type", "conclusion"),
        ),
        "internal_control_report": DocumentPromptSpec(
            prompt_template="document_extract:internal_control_report",
            schema_name="internal_control_extract_v1",
            type_label="内部控制报告",
            type_rules=(
                "聚焦重大缺陷、重要缺陷、整改进展和内部控制有效性结论。"
                "优先保留 defect_level、结论和影响范围。"
            ),
            json_example={
                "items": [
                    {
                        "title": "重大缺陷",
                        "summary": "内部控制报告披露重大缺陷，控制执行有效性不足。",
                        "evidence_excerpt": "公司识别出一项重大缺陷。",
                        "extract_type": "document_issue",
                        "extract_family": "internal_control_conclusion",
                        "event_type": "internal_control_issue",
                        "defect_level": "major",
                        "conclusion": "重大缺陷尚未完成整改。",
                        "affected_scope": "资金审批与关联交易管理",
                        "risk_points": ["内控重大缺陷"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("defect_level", "event_type", "conclusion"),
        ),
        "announcement_event": DocumentPromptSpec(
            prompt_template="document_extract:announcement_event",
            schema_name="announcement_event_extract_v1",
            type_label="公告事件",
            type_rules=(
                "聚焦处罚、问询、诉讼、担保、关联交易、股权质押、高管变动等事件。"
                "每条结果要尽量给出 event_type、subject、金额或对象。"
            ),
            json_example={
                "items": [
                    {
                        "title": "监管问询",
                        "summary": "公告披露收到监管问询函，信息披露与财务口径存在关注点。",
                        "evidence_excerpt": "公司收到证券交易所问询函。",
                        "extract_type": "event_fact",
                        "extract_family": "announcement_event",
                        "event_type": "penalty_or_inquiry",
                        "subject": "上市公司",
                        "severity": "high",
                        "risk_points": ["监管关注"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("event_type",),
        ),
        "general": DocumentPromptSpec(
            prompt_template="document_extract:general",
            schema_name="general_document_extract_v1",
            type_label="一般文档",
            type_rules=(
                "只保留有明确风险或异常信号的片段。"
                "如果候选片段缺乏风险信息，返回空 items。"
            ),
            json_example={
                "items": [
                    {
                        "title": "异常事项",
                        "summary": "文档披露存在需要进一步核查的异常事项。",
                        "evidence_excerpt": "公司披露相关事项存在不确定性。",
                        "extract_type": "document_issue",
                        "extract_family": "general",
                        "risk_points": ["异常事项"],
                        "parameters": {"analysis_stage": "core"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("risk_points", "event_type", "metric_name", "opinion_type"),
        ),
        "annual_financial_subanalysis": DocumentPromptSpec(
            prompt_template="document_extract:annual_financial_subanalysis",
            schema_name="annual_financial_subanalysis_v1",
            type_label="年度报告财报子分析",
            type_rules=(
                "只聚焦财务报表与附注，提取财务异常、关键指标波动、附注线索。"
                "每条结果都要尽量带 metric_name、financial_topics 和 note_refs。"
            ),
            json_example={
                "items": [
                    {
                        "title": "应收账款风险",
                        "summary": "应收账款余额较高且坏账准备变化明显，需要复核减值依据。",
                        "evidence_excerpt": "应收账款期末余额增加且坏账准备计提比例上升。",
                        "extract_type": "document_issue",
                        "extract_family": "financial_statement",
                        "event_type": "financial_anomaly",
                        "metric_name": "应收账款",
                        "metric_value": 1250000000.0,
                        "metric_unit": "元",
                        "financial_topics": ["应收账款"],
                        "note_refs": ["附注五"],
                        "risk_points": ["减值准备", "回款压力"],
                        "detail_level": "financial_deep_dive",
                        "parameters": {"analysis_stage": "financial_subanalysis"},
                    }
                ]
            },
            required_item_keys=("title", "summary", "evidence_excerpt"),
            required_any_of=("metric_name", "financial_topics", "note_refs"),
        ),
    }
    TYPE_ALIASES = {
        "interim_report": "general",
        "quarter_report": "general",
        "special_report": "general",
    }

    @classmethod
    def resolve_prompt_type(cls, classified_type: str) -> str:
        return cls.TYPE_ALIASES.get(classified_type, classified_type if classified_type in cls.SPECS else "general")

    @classmethod
    def get_spec(cls, prompt_type: str) -> DocumentPromptSpec:
        resolved = cls.resolve_prompt_type(prompt_type)
        return cls.SPECS[resolved]

    @classmethod
    def build_prompts(
        cls,
        *,
        document_name: str,
        classified_type: str,
        prompt_type: str,
        candidates: list[dict[str, Any]],
        report_period_label: str | None = None,
    ) -> dict[str, Any]:
        spec = cls.get_spec(prompt_type)
        candidate_blocks = []
        for index, item in enumerate(candidates, start=1):
            candidate_blocks.append(
                "\n".join(
                    [
                        f"[候选片段 {index}]",
                        f"section_title={item.get('section_title') or ''}",
                        f"event_hint={item.get('event_type') or item.get('opinion_type') or ''}",
                        f"risk_hint={item.get('canonical_risk_key') or ''}",
                        f"metric_hint={item.get('metric_name') or ''}",
                        f"summary_hint={item.get('summary') or ''}",
                        f"evidence_excerpt={item.get('evidence_excerpt') or ''}",
                    ]
                )
            )

        system_prompt = (
            f"{cls.COMMON_RULES}"
            f" 当前文档类型是{spec.type_label}。"
            f" {spec.type_rules}"
            f" 返回格式示例：{spec.json_example}"
        )
        user_prompt = (
            f"文档名称：{document_name}\n"
            f"分类类型：{classified_type}\n"
            f"提示模板：{spec.prompt_template}\n"
            f"报告期间：{report_period_label or ''}\n"
            "请从下面候选片段中抽取最重要的结构化结果。如果没有有效结果，返回 {\"items\": []}。\n"
            + "\n\n".join(candidate_blocks)
        )
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema_name": spec.schema_name,
            "prompt_template": spec.prompt_template,
            "required_item_keys": spec.required_item_keys,
            "required_any_of": spec.required_any_of,
        }
