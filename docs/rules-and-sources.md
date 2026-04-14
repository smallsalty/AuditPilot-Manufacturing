# AuditPilot V1 结构化规则规范

## 1. 文档目的

本文档用于定义 AuditPilot 在当前 V1 阶段的正式运行口径，包括：

- 风险识别的标准风险分类
- 结构化财务规则与公告事件规则
- 指标定义与阈值口径
- 风险到审计重点的映射关系
- 数据源职责与可信度边界
- 当前工程实现约束

本规范服务于以下模块：

- 财务报表风控模块
- 公告事件抽取模块
- 风险清单生成模块
- 审计重点提示模块
- 问答与证据组织模块

本文档不等同于完整审计底稿规范，其目标是为“公开信息驱动的风险识别、审计重点提示与持续监控”提供统一标准。

## 2. 适用范围

V1 阶段系统主要处理以下信息来源：

- 上市公司年报、半年报、一季报、三季报
- 审计报告、内部控制评价报告、内部控制审计报告
- 巨潮资讯临时公告
- AkShare 提供的企业主数据、财务指标、行情数据
- 用户上传的补充文档

V1 不覆盖以下内容作为主输入：

- 企业 ERP 全量底账
- 凭证级明细
- 银行流水原始回单
- 函证回函
- 现场盘点底稿

## 3. 风险标准键（Canonical Risk Keys）

所有规则命中、文档抽取结果、公告事件和风险归纳结果，均应优先归并到以下标准风险键。

| canonical_risk_key | 展示名称 | 含义 |
| --- | --- | --- |
| `revenue_recognition` | 收入确认风险 | 关注收入确认时点、期末集中确认、信用放宽带来的收入真实性风险 |
| `receivable_recoverability` | 应收账款回收风险 | 关注应收账款增长异常、回款变慢、坏账准备不足 |
| `inventory_impairment` | 存货积压与减值风险 | 关注库存积压、周转下降、跌价准备不足 |
| `cashflow_quality` | 现金流支撑与利润质量风险 | 关注利润与经营现金流背离、利润含金量不足 |
| `financing_pressure` | 融资与偿债压力风险 | 关注可转债、现金流承压、资金安排不合理 |
| `governance_instability` | 公司治理与关键岗位稳定性风险 | 关注 CFO、董事长等关键岗位变动对财务治理和内控的影响 |
| `litigation_compliance` | 诉讼处罚与合规风险 | 关注诉讼、处罚、监管问询及潜在合规压力 |
| `internal_control_effectiveness` | 内控有效性风险 | 关注内控缺陷、整改不到位、控制执行失效 |
| `related_party_transaction` | 关联交易与资金占用风险 | 关注关联交易复杂、非经营性往来、资金占用 |
| `audit_opinion_issue` | 审计意见异常风险 | 关注非标意见、强调事项、关键审计事项异常 |
| `market_signal_conflict` | 市场信号背离风险 | 关注财报表现与市场反应显著背离的情形 |

## 4. 指标定义规范

### 4.1 通用要求

所有结构化指标必须具备以下元信息：

- `metric_name`：指标英文键
- `display_name`：指标中文名
- `definition`：指标业务定义
- `formula`：计算公式
- `unit`：单位或口径
- `period_scope`：适用期间
- `data_source`：主要数据来源

### 4.2 财务指标定义表

#### 4.2.1 应收账款增长偏离

- `metric_name`: `ar_revenue_growth_gap`
- `display_name`: 应收账款增长偏离
- `definition`: 应收账款同比增速减营业收入同比增速
- `formula`: `accounts_receivable_growth_rate - revenue_growth_rate`
- `unit`: 百分点或比例差
- `period_scope`: 同期同比，优先年度；季度模式下为本季度同比
- `data_source`: `AkShare / 财报抽取`

#### 4.2.2 存货增长偏离

- `metric_name`: `inventory_revenue_growth_gap`
- `display_name`: 存货增长偏离
- `definition`: 存货同比增速减营业收入同比增速
- `formula`: `inventory_growth_rate - revenue_growth_rate`
- `unit`: 百分点或比例差
- `period_scope`: 同期同比
- `data_source`: `AkShare / 财报抽取`

#### 4.2.3 存货占总资产比

- `metric_name`: `inventory_asset_ratio`
- `display_name`: 存货占总资产比
- `definition`: 存货余额占总资产比重
- `formula`: `inventory / total_assets`
- `unit`: 比例
- `period_scope`: 期末时点
- `data_source`: `AkShare / 财报抽取`

#### 4.2.4 其他应收款占总资产比

- `metric_name`: `other_receivable_asset_ratio`
- `display_name`: 其他应收款占总资产比
- `definition`: 其他应收款占总资产比重
- `formula`: `other_receivables / total_assets`
- `unit`: 比例
- `period_scope`: 期末时点
- `data_source`: `AkShare / 财报抽取`

#### 4.2.5 四季度收入占比

- `metric_name`: `q4_revenue_ratio`
- `display_name`: 四季度收入占全年收入比
- `definition`: 第四季度营业收入占全年营业收入比重
- `formula`: `q4_revenue / full_year_revenue`
- `unit`: 比例
- `period_scope`: 年度
- `data_source`: 财报结构化数据

#### 4.2.6 四季度利润占比

- `metric_name`: `q4_profit_ratio`
- `display_name`: 四季度净利润占全年净利润比
- `definition`: 第四季度单季净利润占全年净利润比重
- `formula`: `q4_net_profit / full_year_net_profit`
- `unit`: 比例
- `period_scope`: 年度
- `data_source`: 财报结构化数据

#### 4.2.7 四季度利润偏离历史均值

- `metric_name`: `q4_profit_ratio_deviation`
- `display_name`: 四季度利润贡献偏离度
- `definition`: 本期四季度利润占比与过去三年均值的偏离绝对值
- `formula`: `abs(q4_profit_ratio - avg(q4_profit_ratio_last_3y))`
- `unit`: 百分点或比例差
- `period_scope`: 年度
- `data_source`: 历史财报结构化数据

#### 4.2.8 毛利率

- `metric_name`: `gross_margin`
- `display_name`: 毛利率
- `definition`: 收入扣除成本后的毛利占收入比重
- `formula`: `(revenue - cost) / revenue`
- `unit`: 比例
- `period_scope`: 年度或季度
- `data_source`: `AkShare / 财报抽取`

#### 4.2.9 费用率

- `metric_name`: `expense_ratio`
- `display_name`: 费用率
- `definition`: 销售、管理、研发等费用合计占收入比重
- `formula`: `(selling_expense + admin_expense + rd_expense) / revenue`
- `unit`: 比例
- `period_scope`: 年度或季度
- `data_source`: 财报结构化数据

#### 4.2.10 经营现金流与净利润比

- `metric_name`: `operating_cf_profit_ratio`
- `display_name`: 净现比
- `definition`: 经营活动现金流净额与净利润之比
- `formula`: `operating_cashflow / net_profit`
- `unit`: 比例
- `period_scope`: 年度或季度
- `data_source`: `AkShare / 财报抽取`

#### 4.2.11 应收周转变化

- `metric_name`: `ar_turnover_delta`
- `display_name`: 应收周转变化
- `definition`: 应收账款周转指标相对上期或上年的变化幅度
- `formula`: `accounts_receivable_turnover_current - accounts_receivable_turnover_previous`
- `unit`: 差值或变化率
- `period_scope`: 年度同比优先
- `data_source`: 财务指标计算

#### 4.2.12 存货周转变化

- `metric_name`: `inventory_turnover_delta`
- `display_name`: 存货周转变化
- `definition`: 存货周转指标相对上期或上年的变化幅度
- `formula`: `inventory_turnover_current - inventory_turnover_previous`
- `unit`: 差值或变化率
- `period_scope`: 年度同比优先
- `data_source`: 财务指标计算

#### 4.2.13 三日超额收益率

- `metric_name`: `alpha_3d`
- `display_name`: 财报后三日超额收益率
- `definition`: 财报或重大公告发布后 3 个交易日个股收益率相对基准指数收益率的差值
- `formula`: `stock_return_3d - benchmark_return_3d`
- `unit`: 比例
- `period_scope`: 事件窗口
- `data_source`: `AkShare` 行情数据

## 5. 结构化财务规则

### 5.1 规则字段规范

每条规则应至少具备以下字段：

- `rule_code`
- `display_name`
- `canonical_risk_key`
- `trigger_condition`
- `severity_level`
- `explanation_template`
- `default_weight`
- `primary_metrics`
- `audit_focus`
- `next_step_template`

### 5.2 规则表

#### 5.2.1 收入确认风险：四季度收入占比异常

- `rule_code`: `REV_Q4_RATIO`
- `display_name`: 四季度收入占比异常
- `canonical_risk_key`: `revenue_recognition`
- `trigger_condition`: `q4_revenue_ratio > 0.35`
- `severity_level`: `medium`
- `explanation_template`: 四季度收入占全年收入比重偏高，需关注期末集中确认收入或跨期确认风险。
- `default_weight`: `0.15`
- `primary_metrics`: `q4_revenue_ratio`
- `audit_focus`: 收入真实性、截止测试
- `next_step_template`: 检查合同、发货单、验收单及期后回款，重点核查期末确认的销售交易。

#### 5.2.2 收入确认风险：应收账款增速显著高于营收增速

- `rule_code`: `REV_AR_GAP`
- `display_name`: 应收账款增速偏离
- `canonical_risk_key`: `revenue_recognition`
- `trigger_condition`: `ar_revenue_growth_gap > 0.10`
- `severity_level`: `high`
- `explanation_template`: 应收账款增长快于营业收入增长，可能存在信用政策放宽、收入确认激进或回款能力下降。
- `default_weight`: `0.20`
- `primary_metrics`: `ar_revenue_growth_gap`
- `audit_focus`: 收入真实性、应收可回收性
- `next_step_template`: 复核主要客户销售合同、收入确认时点、期后回款及坏账计提依据。

#### 5.2.3 现金流支撑不足

- `rule_code`: `CF_PROFIT_LOW`
- `display_name`: 净现比偏低
- `canonical_risk_key`: `cashflow_quality`
- `trigger_condition`: `operating_cf_profit_ratio < 0.50`
- `severity_level`: `high`
- `explanation_template`: 经营现金流与利润明显背离，利润含金量偏低，需关注收入真实性和资金回笼质量。
- `default_weight`: `0.30`
- `primary_metrics`: `operating_cf_profit_ratio`
- `audit_focus`: 利润真实性、持续经营、现金流质量
- `next_step_template`: 检查销售回款、经营性现金流构成、异常往来及大额期末调整分录。

#### 5.2.4 存货积压与跌价风险

- `rule_code`: `INV_GROWTH_TURNOVER`
- `display_name`: 存货增长与周转恶化
- `canonical_risk_key`: `inventory_impairment`
- `trigger_condition`: `inventory_revenue_growth_gap > 0.10 AND inventory_turnover_delta < -0.20`
- `severity_level`: `high`
- `explanation_template`: 存货增长快于收入且周转恶化，可能存在库存积压和跌价准备不足。
- `default_weight`: `0.15`
- `primary_metrics`: `inventory_revenue_growth_gap, inventory_turnover_delta`
- `audit_focus`: 存货存在性、跌价准备、产销匹配
- `next_step_template`: 检查库龄、监盘记录、跌价测试、期后销售情况及产销计划。

#### 5.2.5 行业走弱下库存仍上升

- `rule_code`: `INV_INDUSTRY_CONFLICT`
- `display_name`: 行业弱景气下库存逆势上升
- `canonical_risk_key`: `inventory_impairment`
- `trigger_condition`: `industry_demand_down_inventory_up >= 1`
- `severity_level`: `medium`
- `explanation_template`: 行业需求偏弱但公司库存继续上升，需关注备货合理性和潜在减值压力。
- `default_weight`: `0.10`
- `primary_metrics`: `industry_demand_down_inventory_up`
- `audit_focus`: 存货减值、经营预测合理性
- `next_step_template`: 对比行业景气和公司产销变化，复核管理层库存解释及减值计提依据。

#### 5.2.6 应收账款回款压力

- `rule_code`: `AR_TURNOVER_PRESSURE`
- `display_name`: 应收周转恶化
- `canonical_risk_key`: `receivable_recoverability`
- `trigger_condition`: `ar_turnover_delta < -0.30 AND accounts_receivable_growth_rate > 0.10`
- `severity_level`: `high`
- `explanation_template`: 应收周转变慢且应收账款继续增长，坏账风险和回款压力上升。
- `default_weight`: `0.20`
- `primary_metrics`: `ar_turnover_delta, accounts_receivable_growth_rate`
- `audit_focus`: 应收账款可回收性、坏账准备
- `next_step_template`: 进行账龄分析、函证、期后回款测试并复核坏账计提政策。

#### 5.2.7 其他应收款异常占比

- `rule_code`: `OTHER_AR_ASSET_RATIO`
- `display_name`: 其他应收款占比异常
- `canonical_risk_key`: `related_party_transaction`
- `trigger_condition`: `other_receivable_asset_ratio > 0.05`
- `severity_level`: `medium`
- `explanation_template`: 其他应收款占比偏高，需关注非经营性资金往来、关联方占款和款项性质。
- `default_weight`: `0.10`
- `primary_metrics`: `other_receivable_asset_ratio`
- `audit_focus`: 关联方识别、资金占用、款项真实性
- `next_step_template`: 穿透其他应收款明细，识别关联方、款项用途及期后回收情况。

#### 5.2.8 四季度利润贡献偏离历史常态

- `rule_code`: `Q4_PROFIT_DEVIATION`
- `display_name`: 四季度利润贡献异常
- `canonical_risk_key`: `revenue_recognition`
- `trigger_condition`: `q4_profit_ratio_deviation > 0.15`
- `severity_level`: `medium`
- `explanation_template`: 四季度利润贡献明显偏离历史季节性常态，需关注年底利润集中确认或费用调整。
- `default_weight`: `0.15`
- `primary_metrics`: `q4_profit_ratio_deviation`
- `audit_focus`: 收入确认、成本费用截止、利润平滑
- `next_step_template`: 对比近三年季节性表现，核查年末收入、成本和减值相关会计处理。

#### 5.2.9 毛利率或费用率异常

- `rule_code`: `GM_EXPENSE_ANOMALY`
- `display_name`: 毛利率与费用率异常
- `canonical_risk_key`: `cashflow_quality`
- `trigger_condition`: `gross_margin_abnormal == 1 OR expense_ratio_abnormal == 1`
- `severity_level`: `medium`
- `explanation_template`: 毛利率显著偏离行业或费用率异常下降，需关注利润质量和费用确认完整性。
- `default_weight`: `0.10`
- `primary_metrics`: `gross_margin, expense_ratio`
- `audit_focus`: 成本完整性、费用完整性、利润真实性
- `next_step_template`: 对比行业水平，复核成本归集、费用确认和期末调节项目。

## 6. 公告事件规则

### 6.1 事件类型枚举

V1 阶段公告事件固定为以下枚举：

- `share_repurchase`
- `convertible_bond`
- `executive_change`
- `litigation`
- `penalty_or_inquiry`
- `guarantee`
- `related_party_transaction`
- `audit_opinion_issue`
- `internal_control_issue`
- `financial_anomaly`

### 6.2 事件参数最小集合

#### 6.2.1 share_repurchase

- `repurchase_amount_upper`
- `repurchase_price_upper`
- `current_market_price`
- `ratio_to_cash`
- `fund_source`
- `event_date`

#### 6.2.2 convertible_bond

- `downward_revision_triggered`
- `conversion_price`
- `premium_rate`
- `maturity_date`
- `event_date`

#### 6.2.3 executive_change

- `person_name`
- `position`
- `change_type`
- `reason`
- `event_date`

#### 6.2.4 litigation

- `counterparty`
- `amount`
- `currency`
- `case_stage`
- `ratio_to_net_profit`
- `event_date`

#### 6.2.5 penalty_or_inquiry

- `issuing_authority`
- `penalty_type`
- `subject`
- `amount`
- `event_date`

#### 6.2.6 guarantee

- `guaranteed_party`
- `guarantee_amount`
- `ratio_to_net_assets`
- `event_date`

#### 6.2.7 related_party_transaction

- `counterparty`
- `transaction_type`
- `amount`
- `pricing_basis`
- `event_date`

#### 6.2.8 audit_opinion_issue

- `opinion_type`
- `kams`
- `emphasis_matter`
- `event_date`

#### 6.2.9 internal_control_issue

- `defect_level`
- `affected_area`
- `conclusion`
- `rectification_status`
- `event_date`

#### 6.2.10 financial_anomaly

- `metric_name`
- `current_value`
- `previous_value`
- `delta`
- `threshold`
- `period`

### 6.3 公告事件规则表

#### 6.3.1 股份回购诚意不足

- `rule_code`: `BUYBACK_PRICE_SINCERITY`
- `canonical_risk_key`: `market_signal_conflict`
- `trigger_condition`: `repurchase_price_upper < current_market_price`
- `severity_level`: `medium`
- `explanation_template`: 回购价格上限低于当前市价，市场可能认为回购诚意不足。
- `audit_focus`: 资本运作动机、信息披露一致性
- `next_step_template`: 结合公司现金状况、历史回购执行情况及后续公告判断实际回购意图。

#### 6.3.2 股份回购对现金形成压力

- `rule_code`: `BUYBACK_CASH_PRESSURE`
- `canonical_risk_key`: `financing_pressure`
- `trigger_condition`: `ratio_to_cash > 0.50`
- `severity_level`: `high`
- `explanation_template`: 拟回购金额占货币资金比重较高，可能加大现金流压力。
- `audit_focus`: 现金流安排、资本运作合理性
- `next_step_template`: 关注货币资金真实性、受限资金情况及回购资金来源。

#### 6.3.3 可转债下修叠加现金流为负

- `rule_code`: `CBOND_DOWNWARD_CF_NEG`
- `canonical_risk_key`: `financing_pressure`
- `trigger_condition`: `downward_revision_triggered == true AND operating_cashflow < 0`
- `severity_level`: `high`
- `explanation_template`: 可转债触发下修且经营现金流为负，反映融资和偿债压力加大。
- `audit_focus`: 持续经营、融资安排、债务压力
- `next_step_template`: 检查债务到期结构、融资计划和现金流预测。

#### 6.3.4 可转债转股溢价率过高

- `rule_code`: `CBOND_PREMIUM_HIGH`
- `canonical_risk_key`: `financing_pressure`
- `trigger_condition`: `premium_rate > 0.50`
- `severity_level`: `medium`
- `explanation_template`: 转股溢价率偏高，转股动力不足，债务性压力可能延续。
- `audit_focus`: 偿债压力、资本结构
- `next_step_template`: 关注后续转股情况、债券到期安排和流动性保障。

#### 6.3.5 财务负责人变动

- `rule_code`: `EXEC_CHANGE_CFO`
- `canonical_risk_key`: `governance_instability`
- `trigger_condition`: `position == "CFO" OR position == "财务总监"`
- `severity_level`: `high`
- `explanation_template`: 财务负责人变动可能影响财务报告连续性和关键会计判断一致性。
- `audit_focus`: 财务报告内控、关键岗位交接、重大判断一致性
- `next_step_template`: 核查变动原因、交接安排及关键财务流程控制执行情况。

#### 6.3.6 董事长变动

- `rule_code`: `EXEC_CHANGE_CHAIRMAN`
- `canonical_risk_key`: `governance_instability`
- `trigger_condition`: `position == "董事长"`
- `severity_level`: `medium`
- `explanation_template`: 董事长变动可能影响公司治理稳定性和重大决策连续性。
- `audit_focus`: 治理结构、授权审批、重大事项决策
- `next_step_template`: 关注管理层稳定性、决策链条变动及治理文件更新。

#### 6.3.7 重大诉讼

- `rule_code`: `MAJOR_LITIGATION`
- `canonical_risk_key`: `litigation_compliance`
- `trigger_condition`: `ratio_to_net_profit > 0.20`
- `severity_level`: `high`
- `explanation_template`: 重大诉讼金额占净利润比例较高，需关注预计负债、信息披露及经营影响。
- `audit_focus`: 或有事项、预计负债、合规风险
- `next_step_template`: 查看诉讼进展、律师意见、会计处理和相关披露是否充分。

#### 6.3.8 处罚或监管问询

- `rule_code`: `PENALTY_OR_INQUIRY`
- `canonical_risk_key`: `litigation_compliance`
- `trigger_condition`: `event_exists == true`
- `severity_level`: `high`
- `explanation_template`: 公司受到处罚或监管问询，反映合规与披露风险上升。
- `audit_focus`: 合规风险、信息披露、内控执行
- `next_step_template`: 核查处罚原因、整改进展及是否影响财务报表披露。

#### 6.3.9 关联交易异常

- `rule_code`: `RPT_ABNORMAL`
- `canonical_risk_key`: `related_party_transaction`
- `trigger_condition`: `amount > threshold OR pricing_basis_missing == true`
- `severity_level`: `high`
- `explanation_template`: 关联交易金额较大或定价依据不清，需关注交易公允性和利益输送风险。
- `audit_focus`: 关联方识别、交易公允性、信息披露充分性
- `next_step_template`: 检查交易定价、审批程序、资金流向及关联方关系识别是否完整。

#### 6.3.10 审计意见异常

- `rule_code`: `AUDIT_OPINION_ABNORMAL`
- `canonical_risk_key`: `audit_opinion_issue`
- `trigger_condition`: `opinion_type != "standard_unqualified"`
- `severity_level`: `high`
- `explanation_template`: 审计意见非标准无保留，需重点关注影响事项及相关会计处理。
- `audit_focus`: 审计意见影响事项、会计处理充分性、持续经营
- `next_step_template`: 阅读审计报告正文、强调事项和关键审计事项，分析其影响范围。

#### 6.3.11 内控异常

- `rule_code`: `IC_DEFECT_REPORTED`
- `canonical_risk_key`: `internal_control_effectiveness`
- `trigger_condition`: `defect_level in ["material", "significant"] OR conclusion == "ineffective"`
- `severity_level`: `high`
- `explanation_template`: 内控报告披露重大或重要缺陷，或结论显示内控无效，需重点关注控制执行与整改效果。
- `audit_focus`: 内控设计与执行有效性、整改落实
- `next_step_template`: 核查缺陷类型、整改措施、整改期限及是否影响财务报告可靠性。

#### 6.3.12 财报表现与市场反应背离

- `rule_code`: `MARKET_REACTION_MISMATCH`
- `canonical_risk_key`: `market_signal_conflict`
- `trigger_condition`: `profit_growth_rate > 0.20 AND alpha_3d < -0.05`
- `severity_level`: `medium`
- `explanation_template`: 利润增速较高但市场反应为负，可能存在市场对业绩质量或可持续性的质疑。
- `audit_focus`: 利润质量、持续经营、披露解释充分性
- `next_step_template`: 结合公告、分析师关注点和财务结构变化解释市场不信任原因。

## 7. 风险到审计重点映射

| canonical_risk_key | 风险说明 | 对应审计重点 | 下一步建议 |
| --- | --- | --- | --- |
| `revenue_recognition` | 收入确认时点、期末集中确认或信用放宽异常 | 收入真实性、截止测试 | 检查合同、发货、验收、回款与期末交易 |
| `receivable_recoverability` | 应收增长异常、回款变慢、坏账压力上升 | 应收可回收性、坏账准备 | 做账龄分析、函证、期后回款测试 |
| `inventory_impairment` | 存货积压、周转下降、跌价压力 | 存货存在性、跌价准备 | 监盘、库龄分析、跌价测试、期后销售核查 |
| `cashflow_quality` | 利润与经营现金流背离 | 利润真实性、现金流质量、持续经营 | 检查经营现金流构成、异常回款和期末调节 |
| `financing_pressure` | 可转债、回购或债务安排反映流动性压力 | 持续经营、融资安排、流动性 | 查看债务结构、融资计划、现金预测 |
| `governance_instability` | CFO、董事长等关键岗位变动 | 财务治理、关键岗位内控 | 核查岗位变动原因、审批与交接控制 |
| `litigation_compliance` | 诉讼、处罚、问询等带来的合规压力 | 或有事项、预计负债、披露充分性 | 查看进展、法律意见、会计处理和整改 |
| `internal_control_effectiveness` | 内控重大缺陷或控制执行失效 | 内控有效性、整改落实 | 查看缺陷认定、整改措施、穿行测试 |
| `related_party_transaction` | 关联交易复杂或非经营性往来异常 | 关联方识别、交易公允性、资金占用 | 穿透资金流、检查审批和定价依据 |
| `audit_opinion_issue` | 非标审计意见或强调事项异常 | 审计意见影响事项、会计处理充分性 | 阅读审计报告全文并核查影响范围 |
| `market_signal_conflict` | 业绩表现与市场反应不一致 | 业绩质量、信息披露解释 | 结合公告、结构变化和市场预期分析原因 |

## 8. 数据源与资源规范

### 8.1 数据源分层

| source_name | source_type | trust_level | primary_usage | 说明 |
| --- | --- | --- | --- | --- |
| `akshare_fast` | 结构化外部数据 | `semi_official` | 企业检索、财务指标、行情数据 | 用于企业识别、基础财务分析和市场数据 |
| `cninfo` | 官方披露数据 | `official` | 公告、年报、审计报告、内控报告 | V1 主证据来源 |
| `upload` | 用户提供文档 | `user_provided` | 补充证据、企业私有材料 | 与官方文档并行进入文档中心 |
| `knowledge_chunk` | 派生检索数据 | `derived` | 检索、问答、证据组织 | 不是原始事实来源 |
| `llm_output` | 模型生成结果 | `derived` | 文档抽取、归纳总结、解释增强 | 只能作为派生结果，不可替代原始证据 |

### 8.2 正式来源口径

当前正式运行来源限定为：

- `akshare_fast`
- `cninfo`
- `upload`

以下来源不属于正式运行来源：

- `seed`
- `mock`

## 9. 文档抽取与事件抽取规范

### 9.1 文档分型

V1 文档分型至少包括：

- `annual_report`
- `annual_summary`
- `audit_report`
- `internal_control_report`
- `announcement_event`
- `general`

### 9.2 抽取输出最小字段

每条文档抽取结果至少应包含：

- `extract_family`
- `problem_summary`
- `applied_rules`
- `evidence_excerpt`
- `detail_level`
- `fact_tags`

当属于事件类抽取时，额外包含：

- `event_type`
- `event_direction`
- `event_severity`
- `event_date`
- `parameters`

### 9.3 抽取质量约束

- `problem_summary` 必须为一句式总结，不直接回显整段原文
- 抽取优先使用清洗后的候选段，不直接对整篇 PDF 做总结
- 需尽量去除封面、目录、页眉页脚、页码、重复段落
- 事件类型必须来自固定枚举，不允许开放式自由分类
- 模型抽取失败时，应回退到规则提取，而不是回退到粗糙原文片段展示

## 10. 风险结果输出规范

每条风险结果至少包含：

- `risk_name`
- `canonical_risk_key`
- `risk_category`
- `risk_level`
- `risk_score`
- `summary`
- `evidence`
- `source_mode`
- `source_rules`
- `source_documents`
- `source_events`
- `feature_support`

### 10.1 source_mode 枚举

- `document_primary`
- `document_plus_rule`
- `rule_only`

### 10.2 风险排序规则

排序应遵循以下原则：

- `document_primary` 优先
- `document_plus_rule` 次之
- `rule_only` 最后
- 同组内按 `risk_score` 降序排列

### 10.3 证据状态建议

建议额外增加：

- `evidence_status: document_supported | rule_inferred`

用于明确区分文档支持风险与纯规则推断风险。

## 11. 当前工程实现约束

### 11.1 规则表达式支持范围

当前规则引擎支持以下比较操作符：

- `>`
- `>=`
- `<`
- `<=`
- `==`

复杂逻辑允许通过 `AND / OR` 在代码层组合，不要求规则文档直接支持任意表达式嵌套。

### 11.2 当前评分实现

当前命中规则后的风险分数实现为：

`min(100, weight * 20 + hit_condition_count * 10)`

该公式仅代表 V1 当前工程实现，不应视为长期固定业务规则。后续版本可引入以下增强项：

- 风险严重度
- 文档证据支持度
- 来源可信度
- 时间新近性
- 多源一致性

### 11.3 当前问答口径

问答回答优先级如下：

1. 官方文档抽取结果
2. 公告事件事实
3. 财务规则证据
4. 通用审计程序模板

## 12. 版本管理与扩展原则

### 12.1 版本字段建议

建议对以下结果增加 `version` 字段：

- 文档抽取结果
- 事件特征
- 风险结果

用于支持抽取逻辑升级后的历史重建和兼容。

### 12.2 扩展原则

V1 扩展时遵循以下原则：

- 先扩枚举，再扩模型自由度
- 先扩结构化字段，再扩自然语言总结
- 先保证可追溯，再优化解释丰富度
- 先保证文档主链稳定，再扩外部行业和舆情因子

## 13. V1 实施重点

当前 V1 阶段优先完成以下目标：

- 提升文档清洗与抽取质量，减少封面、目录、页码和重复片段干扰
- 建立“事件 + 参数 + 一句式总结”的文档抽取输出
- 将风险清单调整为“文档主链 + 规则补充”
- 让审计重点和问答优先消费文档主链风险
- 明确正式来源、派生来源和模型生成结果之间的证据层级
