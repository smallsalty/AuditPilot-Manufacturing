# AuditPilot 规则与资源摘要

这是一份当前正式运行口径的规则与资源摘要。

## 规则（公式）

规则引擎当前支持 `>`、`>=`、`<`、`<=`、`==`。  
规则命中后的风险分数按当前实现计算：`min(100, weight * 20 + 命中条件数 * 10)`。

| 规则主题 | 公式 / 阈值 | 用途 |
| --- | --- | --- |
| 收入确认风险 | `q4_revenue_ratio > 0.35` | 识别四季度收入占比异常偏高，关注期末集中确认收入。 |
| 收入确认风险 | `ar_revenue_growth_gap > 0.10` | 识别应收增速显著高于营收增速，关注信用放宽和收入质量。 |
| 收入确认风险 | `operating_cf_profit_ratio < 0.50` | 识别经营现金流与利润背离，关注利润真实性。 |
| 存货减值/积压风险 | `inventory_revenue_growth_gap > 0.10` 且 `inventory_turnover_delta < -0.20` | 识别存货积压和跌价风险。 |
| 存货减值/积压风险 | `industry_demand_down_inventory_up >= 1` | 识别行业走弱时库存仍上升的异常。 |
| 应收账款回款风险 | `ar_turnover_delta < -0.30` 且 `accounts_receivable_growth_rate > 0.10` | 识别回款周期拉长和坏账压力。 |
| 合规与外部事件风险 | `major_litigation_count > 0` 或 `penalty_count > 0` 或 `negative_sentiment_count > 0` | 识别诉讼、处罚、负面舆情带来的合规压力。 |
| 关联交易/内控风险 | `related_party_complexity_score > 0` 或 `executive_change_count > 0` | 识别关联结构复杂和高管频繁变动带来的内控风险。 |

## 资源

| 资源 | 作用 | 当前口径 |
| --- | --- | --- |
| `AkShare` | 企业检索、企业主数据、结构化财务数据 | 企业引入支持股票代码和公司名。 |
| `巨潮资讯（cninfo）` | 官方公告、年报、审计报告、处罚类公告同步 | 首次同步按审计年度抓取，后续按短窗口增量同步。 |
| `上传文档` | 补充企业私有材料和额外审计证据 | 与官方文档一起进入文档中心和知识检索。 |
| `MiniMax-M2.7（Anthropic 兼容）` | 文档抽取、问答总结、解释增强 | 当前通过 `ANTHROPIC_*` 配置，兼容 `LLM_*`。 |
| `本地轻量 RAG / KnowledgeChunk` | 文档片段、抽取结果、规则证据检索 | 用于问答、抽取回显和证据组织。 |

当前正式来源是 `akshare_fast`、`cninfo`、`upload`。  
`seed`、`mock` 不算正式运行来源。

## 文档抽取与问答

- 文档先解析，再生成抽取结果和知识块。
- 抽取结果当前主字段包括：`problem_summary`、`applied_rules`、`evidence_excerpt`、`detail_level`。
- 年报、审计报告等财报类文档可进入更细的财报深析。
- 风险结果当前主口径包含：`source_mode`、`source_rules`、`source_documents`。
- 企业 readiness 当前主口径包含：`risk_analysis_ready`、`risk_analysis_reason`、`risk_analysis_message`。
- 问答优先基于官方文档、规则证据和风险结果组织回答。

## 后续方向

- 提升文档抽取质量，减少封面、目录、重复片段。
- 让风险清单进一步以文档抽取结果为主，而不是只依赖结构化规则结果。
- 继续提升问答速度和证据引用质量。
