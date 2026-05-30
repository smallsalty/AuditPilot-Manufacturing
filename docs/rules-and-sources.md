# AuditPilot 风险规则与来源规范

本文档描述当前系统已经落地的风险分析口径。重点是四类风险来源、命中规则、评分细节、证据层级和最终展示规则。

当前风险结果统一展示为四类来源：

| 来源标签 | 后端来源 | 主要入口 | 典型证据 |
| --- | --- | --- | --- |
| 文档 | `DocumentRiskService` | 已解析年报、审计报告、内控报告、上传文档 | 文档抽取片段、事件特征、页码、章节 |
| 公告 | `AnnouncementRiskService` | 巨潮公告事件正文分析 | 公告标题、公告正文摘要、风险点、审计关注 |
| 数据 | `RiskAnalysisService`、`RuleEvaluator`、`FinancialDataRiskService`、`TaxRiskService` | 结构化财务指标、行业对比、税务指标、规则引擎 | AkShare 指标、行业基准、税务指标、模型结果 |
| 财报 | `FinancialAnalysisService` | 财报深度抽取与财报聚合分析 | 财报异常项、财务指标、原文摘录、期间 |

补充说明：

- `source_type=model` 的 IsolationForest 结果归入“数据”。
- 税务风险当前也归入“数据”，因为它基于结构化财务指标计算。
- `baseline_observation` 只是兜底观察，不代表无风险结论。

## 1. 运行边界

### 1.1 可用数据

系统当前只把以下来源当成正式分析输入：

| source_name | 信任层级 | 用途 | 说明 |
| --- | --- | --- | --- |
| `cninfo` | 官方披露 | 公告、年报、审计报告、内控报告 | 风险证据优先级最高 |
| `upload` | 用户提供 | 补充文档、企业私有材料 | 可作为文档证据，但需保留上传来源 |
| `akshare` / `akshare_fast` | 半官方结构化数据 | 企业主数据、财务指标、行情数据 | 适合规则计算，不替代公告原文 |
| `industry_leader_benchmark` | 衍生龙头基准 | 所处行业龙头企业指标对比 | 只允许东方财富业绩报表来源 |
| `llm_output` | 派生结果 | 摘要、归纳、解释增强 | 不能替代原始证据 |

以下来源不得作为正式证据：

- `seed`
- `mock`
- 演示 CSV
- 未标明来源的模型总结

### 1.2 运行前置条件

风险分析满足以下任一条件即可运行：

- 已同步官方财务指标。
- 已同步官方公告事件。
- 已解析或上传可用文档。

如果企业处于 `syncing`，不运行风险分析。

如果企业处于 `failed`，需要先重新同步。

如果只有文档，没有财务指标和公告事件，则进入文档主导模式。

## 2. 标准风险键

所有风险应尽量归并到 `canonical_risk_key`。当前支持以下标准键。

### 2.1 通用风险键

| canonical_risk_key | 展示名称 | 关注点 |
| --- | --- | --- |
| `revenue_recognition` | 收入确认与收入真实性风险 | 截止、确认时点、期末冲量、信用放宽 |
| `receivable_recoverability` | 应收账款回收与收入真实性风险 | 应收增长、周转变慢、坏账准备 |
| `inventory_impairment` | 存货减值与积压风险 | 库存积压、周转下降、跌价准备 |
| `cashflow_quality` | 经营现金流与利润质量风险 | 利润和现金流背离 |
| `financing_pressure` | 融资与资金压力风险 | 债务、流动性、回购、可转债 |
| `related_party_transaction` | 关联交易与资金占用风险 | 关联方、非经营性往来、担保 |
| `litigation_compliance` | 诉讼处罚与合规风险 | 诉讼、处罚、问询、合规整改 |
| `internal_control_effectiveness` | 内部控制有效性风险 | 重大缺陷、控制失效、整改不到位 |
| `audit_opinion_issue` | 审计意见异常风险 | 非标意见、强调事项、关键审计事项 |
| `going_concern` | 持续经营与审计意见风险 | 亏损、债务压力、持续经营假设 |
| `governance_instability` | 治理结构与高管稳定性风险 | CFO、董事长、关键岗位变动 |
| `market_signal_conflict` | 市场信号背离风险 | 业绩表现和市场反应不一致 |
| `uncategorized` | 文档发现风险 | 暂未归类的文档风险 |

### 2.2 税务风险键

| canonical_risk_key | 展示名称 |
| --- | --- |
| `tax_effective_rate_anomaly` | 企业所得税有效税率异常风险 |
| `tax_cashflow_mismatch` | 税费现金流匹配异常风险 |
| `deferred_tax_volatility` | 递延所得税波动风险 |
| `tax_payable_accrual` | 应交税费挂账异常风险 |

### 2.3 公告风险键

| canonical_risk_key | 展示名称 |
| --- | --- |
| `announcement_regulatory_litigation` | 公告监管处罚与诉讼仲裁风险 |
| `announcement_accounting_audit` | 公告会计差错与审计意见风险 |
| `announcement_related_party_guarantee` | 公告资金占用、关联交易与担保风险 |
| `announcement_debt_liquidity` | 公告债务逾期与流动性风险 |
| `announcement_equity_control_pledge` | 公告股权变动与控制权风险 |
| `announcement_performance_revision_impairment` | 公告业绩修正与减值风险 |
| `announcement_governance_internal_control` | 公告治理异常与内控风险 |

## 3. 风险结果统一结构

每条风险结果至少应包含：

| 字段 | 含义 |
| --- | --- |
| `risk_name` | 风险名称 |
| `canonical_risk_key` | 标准风险键 |
| `risk_category` | 风险大类 |
| `risk_level` | `HIGH` / `MEDIUM` / `LOW` |
| `risk_score` | 0-100 分 |
| `summary` | 一句话风险说明 |
| `reasons` | 命中原因 |
| `evidence_chain` | 证据链 |
| `source_type` | 原始结果来源 |
| `source_mode` | 展示聚合模式 |
| `evidence_status` | 证据状态 |
| `source_rules` | 命中的规则 |
| `source_documents` | 关联文档 |
| `source_events` | 关联事件 |
| `feature_support` | 指标支撑 |
| `score_details` | 评分拆解 |

### 3.1 source_type

| source_type | 含义 | 归入展示来源 |
| --- | --- | --- |
| `rule` | 结构化规则命中 | 数据 |
| `financial_data` | 财务数据子分析命中 | 数据 |
| `event` | 公告事件风险 | 公告 |
| `model` | IsolationForest 异常检测 | 数据 |
| `baseline` | 基线观察 | 数据 |
| `document_rule` | 文档聚合风险 | 文档 |

### 3.2 source_mode

| source_mode | 排序权重 | 含义 |
| --- | ---: | --- |
| `document_primary` | 0 | 文档证据直接支持 |
| `document_plus_rule` | 1 | 文档和规则共同支持 |
| `announcement_event` | 2 | 公告事件正文支持 |
| `rule_only` | 3 | 纯规则推断，待文档验证 |
| `baseline_observation` | 8 | 基线观察 |

最终排序：

```text
先按 source_mode 排序，再按 risk_score 降序，再按 risk_name 排序。
```

## 4. 通用评分口径

除公告聚合分外，系统大多使用 0-100 分。

| 分数区间 | 默认等级 |
| --- | --- |
| `>= 80` | `HIGH` |
| `>= 60 and < 80` | `MEDIUM` |
| `< 60` | `LOW` |

评分只用于排序和审计关注优先级，不直接等同于审计结论。

## 5. 文档风险分析

### 5.1 输入范围

文档风险来自：

- 年报、半年报、季报。
- 审计报告。
- 内部控制评价报告。
- 内部控制审计报告。
- 巨潮公告原文。
- 用户上传文档。

文档抽取会跳过明显噪声：

- 封面。
- 目录。
- 页码。
- 无实质风险的报告标题。
- 过短且无指标、无规则、无事件的片段。

### 5.2 文档抽取风险评分

文档抽取结果使用 `_score_extract()` 评分。

```text
score = 70
      + financial_deep_dive_bonus
      + applied_rules_bonus
      + risk_points_bonus

score = min(score, 95)
```

明细如下：

| 项目 | 加分 |
| --- | ---: |
| `detail_level == financial_deep_dive` | `+8` |
| 每命中 1 条 `applied_rules` | `+4`，最高 `+12` |
| 每识别 1 条 `risk_points` | `+2`，最高 `+8` |
| 封顶 | `95` |

文档抽取等级：

| 条件 | 等级 |
| --- | --- |
| `detail_level == financial_deep_dive` | `HIGH` |
| 摘要或风险点含“重大、处罚、诉讼、缺陷、异常” | `HIGH` |
| 其他有效抽取 | `MEDIUM` |

### 5.3 文档事件特征评分

文档事件特征使用固定基准：

| feature_type | 分数 | 等级 |
| --- | ---: | --- |
| `event` | `78` | `severity == high` 时为 `HIGH`，否则 `MEDIUM` |
| 非 `event` | `74` | `severity == high` 时为 `HIGH`，否则 `MEDIUM` |

同一 `canonical_risk_key` 下，文档风险会聚合。

聚合规则：

- `risk_score` 取同组最大值。
- `risk_level` 取更高等级。
- `source_documents` 去重合并。
- `source_events` 去重合并。
- `evidence` 最多展示前 6 条。

## 6. 公告风险分析

### 6.1 输入范围

公告风险来自巨潮公告事件。

当前只保留：

- 近 365 天公告。
- 标题命中支持类目。
- 正文分析存在有效风险点、审计关注、金额、关键事实或实质信号。

会过滤：

- 只有“年报公告”“审计报告公告”等泛标题。
- 没有正文分析的空事件。
- 超出 365 天的旧公告。

### 6.2 公告类目

| category_code | 事件名称 | base_weight | 默认等级 | 分数封顶 |
| --- | --- | ---: | --- | ---: |
| `regulatory_litigation` | 监管处罚与诉讼仲裁风险 | `1.18` | `high` | `92` |
| `accounting_audit` | 会计差错与审计意见风险 | `1.12` | `high` | `90` |
| `fund_occupation_related_party_guarantee` | 资金占用、关联交易与担保风险 | `1.14` | `high` | `90` |
| `debt_liquidity_default` | 债务逾期与流动性风险 | `1.08` | `high` | `88` |
| `equity_control_pledge` | 股权变动与控制权风险 | `0.96` | `medium` | `80` |
| `performance_revision_impairment` | 业绩修正与减值风险 | `0.94` | `medium` | `78` |
| `governance_personnel_internal_control` | 治理异常与内控风险 | `0.92` | `medium` | `76` |

关键词会提升等级。例如：

- “立案、行政处罚、处罚决定、无法表示意见、否定意见、资金占用、违规担保、债务逾期、违约、重整、失控”会提升为 `high`。
- “问询函、监管措施、担保、关联交易、股权质押、业绩修正、内控缺陷、高管变动”通常为 `medium`。

### 6.3 单条公告评分

```text
score = SCORE_BY_LEVEL[risk_level]
      * base_weight
      * recency_multiplier
      + min(repeat_count_90d * 5, 12)

score = min(score, category_score_cap)
```

等级基准分：

| risk_level | SCORE_BY_LEVEL |
| --- | ---: |
| `low` | `42` |
| `medium` | `58` |
| `high` | `74` |

时间系数：

| 公告新近性 | recency_multiplier |
| --- | ---: |
| 无日期 | `0.78` |
| `<= 30` 天 | `1.00` |
| `<= 90` 天 | `0.93` |
| `<= 180` 天 | `0.86` |
| `> 180` 天 | `0.74` |

重复事件：

```text
repeat_count_90d = 近 90 天内同类公告重复次数
repeat_bonus = min(repeat_count_90d * 5, 12)
```

### 6.4 公告聚合分

公告风险另有一个聚合分。

```text
announcement_risk_score =
    top1_score * 0.46
  + top2_score * 0.27
  + top3_score * 0.17
  + top4_score * 0.10

announcement_risk_score = min(announcement_risk_score, 88)
```

聚合等级：

| announcement_risk_score | 等级 |
| --- | --- |
| `>= 70` | `high` |
| `>= 45 and < 70` | `medium` |
| `< 45` | `low` |

## 7. 数据风险分析

数据风险包含三条线：

- 结构化规则风险。
- 财务数据子分析。
- 税务风险。

IsolationForest 异常检测也归入数据风险。

### 7.1 结构化规则评分

结构化规则来自数据库 `AuditRule`，默认由 `data/seeds/backend/audit_rules.json` 初始化。

规则表达式支持：

- `>`
- `>=`
- `<`
- `<=`
- `==`

组合逻辑支持：

- `logic = all`
- `logic = any`

缺失指标会按 `0.0` 参与比较。

评分公式：

```text
matched = all(condition_hits) or any(condition_hits)

base_score = min(100, rule.weight * 20 + hit_condition_count * 10)

effective_weight = rule.weight * context_weight_multiplier

final_score = min(100, effective_weight * 20 + hit_condition_count * 10)
```

其中：

| 字段 | 含义 |
| --- | --- |
| `hit_condition_count` | 已通过条件数量 |
| `rule.weight` | 规则权重 |
| `context_weight_multiplier` | 场景权重系数 |
| `base_score` | 未考虑场景加权的分数 |
| `final_score` | 最终写入 `risk_score` 的分数 |

场景权重：

| 场景 | 适用规则 | 系数 |
| --- | --- | ---: |
| 轻资产行业 | `AR_COLLECTION`、`REV_AR_GAP`、`EXCESS_PROFIT_INDUSTRY_OUTLIER` | `1.15` |
| 高杠杆场景 | 债务、融资相关规则 | `1.20` |
| 总封顶 | 全部规则 | `1.30` |

当前结构化规则：

| rule_code | 触发条件 | risk_level | weight | 评分说明 |
| --- | --- | --- | ---: | --- |
| `REV_Q4_SPIKE` | `q4_revenue_ratio > 0.35` | `HIGH` | `3.2` | 基础分 `3.2*20+10=74` |
| `REV_AR_GAP` | `ar_revenue_growth_gap > 0.10` | `HIGH` | `3.0` | 基础分 `70`；轻资产可加权 |
| `OCF_PROFIT_DIVERGENCE` | `operating_cf_profit_ratio < 0.50` | `HIGH` | `3.4` | 基础分 `78` |
| `INV_BACKLOG` | `inventory_revenue_growth_gap > 0.10` 且 `inventory_turnover_delta < -0.20` | `HIGH` | `3.5` | 两条件全中基础分 `90` |
| `INV_INDUSTRY_DOWN` | `industry_demand_down_inventory_up >= 1` | `MEDIUM` | `2.6` | 基础分 `62` |
| `AR_COLLECTION` | `ar_turnover_delta < -0.30` 且 `accounts_receivable_growth_rate > 0.10` | `HIGH` | `3.1` | 两条件全中基础分 `82`；轻资产可加权 |
| `COMPLIANCE_EVENTS` | 重大诉讼、处罚、负面舆情任一存在 | `MEDIUM` | `2.8` | `any` 逻辑；按命中条件数加分 |
| `RELATED_PARTY_CONTROL` | 关联结构复杂或高管变动任一存在 | `MEDIUM` | `2.7` | `any` 逻辑 |
| `EXCESS_PROFIT_INDUSTRY_OUTLIER` | `excess_profit_risk_signal >= 1` | `HIGH` | `3.4` | 基础分 `78`；轻资产可加权 |
| `DEBT_PRESSURE_HIGH` | `short_term_debt_pressure >= 1` 或 `debt_ratio_industry_high >= 1` | `MEDIUM` | `2.8` | 高杠杆可加权 |

### 7.2 财务数据子分析

财务数据子分析读取最近 4 个季度指标。全部命中项会分别持久化，并各自生成审计建议；完整 `data_risks` 同时进入快照。

等级：

| risk_score | risk_level |
| --- | --- |
| `>= 80` | 高 |
| `>= 60 and < 80` | 中 |
| `< 60` | 低 |

评分规则：

| rule_code | 触发条件 | 评分 |
| --- | --- | --- |
| `FIN_DATA_REVENUE_VOLATILITY` | 任一季度收入环比绝对波动 `>= 30%` | `min(100, 60 + (max_abs - 30) * 0.8)` |
| `FIN_DATA_PROFIT_CASH_MISMATCH` | 单季净利润现金含量 `< 0.8`，单季净利润为正且经营现金流为负，或近 4 季经营现金流/净利润 `< 0.8` | 单季错配基准 `82`；比例错配为 `max(75, min(100, 75 + (0.8 - ratio) * 25))`；多个条件取最高分 |
| `FIN_DATA_MARGIN_DECLINE` | 毛利率较近 4 季首期下降 `>= 5` 个百分点，或净利率下降 `>= 3` 个百分点 | 毛利率：`65 + abs(delta + 5) * 3`；净利率：`65 + abs(delta + 3) * 4`；取高值并封顶 |
| `FIN_DATA_LEVERAGE_PRESSURE` | 最新资产负债率 `>= 65%`，或近 4 季上升 `>= 5` 个百分点 | 负债率：`70 + (latest - 65) * 1.2`；上升幅度：`70 + (change - 5) * 2`；取高值并封顶 |
| `FIN_DATA_DEDUCT_PROFIT_DEPENDENCE` | 最新季度归母净利润为正，且扣非净利润 / 归母净利润 `< 0.8` | `min(100, 70 + (0.8 - ratio) * 50)` |
| `FIN_DATA_AR_TURNOVER_DECLINE` | 近 4 季首尾应收账款周转率下降 `>= 30%` | `min(100, 65 + (decline_ratio - 0.30) * 80)` |
| `FIN_DATA_INVENTORY_TURNOVER_DECLINE` | 近 4 季首尾存货周转率下降 `>= 30%` | `min(100, 65 + (decline_ratio - 0.30) * 80)` |
| `FIN_DATA_INTEREST_DEBT_PRESSURE` | 最新有息负债率 `>= 30%`，或近 4 季上升 `>= 5` 个百分点 | 绝对值和上升幅度均以 `70` 为基准，取较高值并封顶 |
| `FIN_DATA_EXPENSE_RATIO_INCREASE` | 近 4 季首尾期间费用率上升 `>= 3` 个百分点 | `min(100, 65 + (increase - 3) * 4)` |
| `FIN_DATA_FIXED_ASSET_VOLATILITY` | 近 4 季固定资产最大最小差 / 期初固定资产 `>= 15%` | `min(100, 60 + (ratio - 0.15) * 120)` |
| `FIN_DATA_INDUSTRY_DEVIATION` | 龙头基准对比至少 2 项异常 | 2 项异常 `78`；3 项及以上 `88` |

龙头基准对比异常定义：

| 指标 | 异常条件 |
| --- | --- |
| 营收增长率低于龙头基准 | `gap <= -20` 个百分点 |
| 毛利率偏离龙头基准 | `abs(gap) >= 8` 个百分点 |
| 净利率偏离龙头基准 | `abs(gap) >= 5` 个百分点 |
| 应收周转低于龙头基准 | `gap_pct <= -0.30` |
| 存货周转低于龙头基准 | `gap_pct <= -0.30` |
| 资产负债率高于龙头基准 | `gap >= 10` 个百分点 |
| 期间费用率高于龙头基准 | `gap >= 3` 个百分点 |

营业收入绝对规模只用于展示，不直接判定数据风险。财报页展示全部命中项；综合风险分析为每个命中项分别写入风险结果和审计建议。

### 7.3 税务风险

税务风险使用固定基础分。命中后直接写入 `risk_score`。

| rule_code | 触发条件 | risk_level | risk_score |
| --- | --- | --- | ---: |
| `TAX_ETR_ABNORMAL` | 有效税率 `< 10%` 或 `> 35%`；或偏离法定税率 `>= 10` 个百分点且偏离近三期中位数 `>= 8` 个百分点 | `HIGH` | `88` |
| `TAX_CASHFLOW_MISMATCH` | 支付税费现金 / 名义税费 `< 0.65` 或 `> 1.80`，且差额占比 `>= 15%`；若有应交税费，则方向需一致 | `MEDIUM` | `76` |
| `DEFERRED_TAX_VOLATILITY` | 递延税净额变动 / 总资产 `>= 1%`，且相对上期波动 `>= 50%` | `MEDIUM` | `74` |
| `TAX_PAYABLE_ACCRUAL` | 应交税费同比增长 `>= 30%`，支付税费现金 `< 名义税费 * 80%`，收入同比增长 `< 20%` | `HIGH` | `86` |

税务规则会记录：

- 参与计算的指标。
- 缺失指标。
- 跳过原因。
- 计算证据链。
- 审计关注科目和程序。

### 7.4 模型异常检测

IsolationForest 只在年度样本不少于 3 年时运行。

输入指标：

- `revenue`
- `net_profit`
- `operating_cash_flow`
- `accounts_receivable`
- `inventory`

命中条件：

```text
latest_year_prediction == -1
```

输出：

| 字段 | 值 |
| --- | --- |
| `risk_name` | 数值异常波动风险 |
| `risk_category` | 经营风险 |
| `risk_level` | `MEDIUM` |
| `risk_score` | `68` |
| `source_type` | `model` |

## 8. 财报风险分析

财报风险是财报深度抽取结果的独立汇总。它不会直接替代风险分析结果，而是在前端统一展示时并入“财报”来源。

### 8.1 输入范围

财报风险来自：

- 财报文档抽取结果。
- `financial_statement` 抽取。
- `financial_deep_dive` 抽取。
- AkShare 结构化财报关键指标。

### 8.2 财报异常评分

财报异常使用 `_score_financial_extract()` 评分。

```text
score = 64
      + deep_dive_bonus
      + applied_rules_bonus
      + canonical_key_bonus
      + metric_value_bonus
      + compare_value_bonus
      + evidence_text_bonus
      + severity_bonus

score = min(95, max(0, score))
```

明细如下：

| 项目 | 加分 |
| --- | ---: |
| `detail_level == financial_deep_dive` | `+8` |
| 每条 `applied_rules` | `+4`，最高 `+12` |
| 存在 `canonical_risk_key` | `+4` |
| 存在 `metric_value` | `+3` |
| 存在 `compare_value` | `+3` |
| 存在 `problem_summary` 或 `evidence_excerpt` | `+4` |
| `severity == high` | `+8` |
| `severity == medium` | `+4` |
| 封顶 | `95` |

等级：

| score | risk_level |
| --- | --- |
| `>= 80` | `HIGH` |
| `>= 60 and < 80` | `MEDIUM` |
| `< 60` | `LOW` |

前端展示时，财报异常会优先取最新财报：

```text
排序键 = fiscal_year, fiscal_quarter, announcement_date, document_id
```

同一最新文档内的异常会一起展示。

## 9. 细分行业龙头基准口径

龙头基准来自东方财富业绩报表。分类直接使用报表的 `所处行业` 字段，不维护人工细分映射或父级 fallback。

刷新结果写入三张表：

- `industry_benchmark_refresh_state`：企业当前期间的刷新状态和可选板块校验结果。
- `industry_leader_company`：所处行业内实际入选的龙头企业。
- `industry_leader_benchmark`：所处行业、期间和指标对应的龙头均值。

同一细分行业内选取 Top 5 龙头企业：

1. 营业收入降序。
2. 营收缺失或相同时，归母净利润降序。
3. 再按股票代码稳定排序。

每家公司先计算指标，再取算术均值。东方财富 `push2` 板块接口只做可选校验；接口失败不会阻断业绩报表生成基准。

有效基准要求：

- 最多选取 Top 5 龙头企业。
- 指标有效样本数 `sample_count >= 3`。
- 同行财务报表精确匹配请求期间。
- 存在龙头集合算术均值。
- 公司自身指标存在。
- 不使用 `mock` 来源。

刷新失败或样本不足时，读取端隐藏旧基准，不使用旧期间替代。

行业对比输出字段：

| 字段 | 含义 |
| --- | --- |
| `company_value` | 公司指标 |
| `leader_benchmark` | 龙头企业指标均值 |
| `leader_companies` | 龙头企业列表，包含排名、股票代码和名称 |
| `gap` | 公司值 - 龙头基准 |
| `gap_pct` | 差异 / 龙头基准绝对值 |
| `sample_count` | 龙头样本数 |
| `source` | 固定为 `eastmoney_yjbb` |

## 10. 证据优先级

问答、审计重点和风险卡片应按以下优先级使用证据：

1. 官方文档原文抽取。
2. 公告正文事件分析。
3. 结构化财务指标。
4. 行业基准信号。
5. 模型异常检测。
6. LLM 总结。

禁止把 LLM 总结当作唯一证据。

如果只有规则命中，没有文档或公告支持，应标记为：

```text
evidence_status = rule_inferred
```

如果文档和规则共同支持，应标记为：

```text
evidence_status = document_plus_rule
```

## 11. 当前缺口

当前实现仍有这些边界：

- 部分规则依赖指标完整度，缺失指标会按 `0` 比较，可能导致保守或误判。
- 公告风险依赖正文分析质量。没有有效正文分析的标题命中会被过滤。
- 龙头基准只使用已刷新的东方财富结果，不在查询时实时构建同行池。
- 税务风险是规则判断，不等同于税务鉴证结论。
- IsolationForest 只提示异常波动，不直接判断错报。
- 财报风险和数据风险会在前端并入展示，但后端持久化路径不同。

## 12. 维护规则

新增风险规则时，必须同步维护以下内容：

1. `canonical_risk_key` 是否已存在。
2. `rule_code` 是否能映射到中文展示。
3. 触发条件和单位是否清楚。
4. 评分公式是否可复算。
5. 证据来源是否可追溯。
6. `source_type`、`source_mode`、`evidence_status` 是否符合本文档。

新增来源时，必须明确：

- 来源名称。
- 信任层级。
- 原始证据字段。
- 是否可用于正式分析。
- 是否只是派生结果。
