# AuditPilot AI 参数 Schema（V1 第一阶段）

## 1. 目标

本文档定义 AuditPilot 第一阶段“文档事件与参数抽取”所使用的最小参数 schema。  
参数设计完全从 [rules-and-sources.md](D:/firstmoney/AuditPilot-Manufacturing/docs/rules-and-sources.md) 反推，不引入开放式自由字段。

设计原则：

- `parameters` 使用扁平 JSON 对象
- 参数只保留机器消费需要的核心字段
- 所有字段都应可追溯到文档、公告、意见或规则
- `LLM` 仅对候选段做结构化归纳，失败时必须回退到规则提取

## 2. 固定枚举

### 2.1 `event_type`

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

### 2.2 `extract_family`

- `announcement_event`
- `opinion_conclusion`
- `financial_statement`
- `general`

### 2.3 `canonical_risk_key`

- `revenue_recognition`
- `receivable_recoverability`
- `inventory_impairment`
- `cashflow_quality`
- `financing_pressure`
- `governance_instability`
- `litigation_compliance`
- `internal_control_effectiveness`
- `related_party_transaction`
- `audit_opinion_issue`
- `market_signal_conflict`

## 3. 文档事件抽取输出结构

```json
{
  "extract_family": "announcement_event",
  "event_type": "share_repurchase",
  "parameters": {
    "event_date": "2025-03-12",
    "repurchase_amount_upper": 200000000.0,
    "repurchase_price_upper": 18.5,
    "ratio_to_cash": 0.42,
    "direction": "positive",
    "severity": "medium"
  },
  "summary": "公司披露股份回购安排，需关注资金压力与回购执行意图。",
  "fact_tags": ["share_repurchase", "financing_pressure"],
  "evidence_excerpt": "公司拟使用自有资金回购股份，回购金额不超过2亿元，回购价格不超过18.5元/股。",
  "page_start": 12,
  "page_end": 12
}
```

字段说明：

- `summary`：一句话摘要，不回显整段原文
- `parameters`：按 `event_type` 选填的扁平 JSON 对象
- `fact_tags`：供检索和风险映射使用的标签
- `evidence_excerpt`：保留可追溯的短证据，不保留整篇原文

## 4. 各 `event_type` 最小参数集合

### 4.1 `share_repurchase`

必选：

- `event_date`

建议抽取：

- `repurchase_amount_upper`
- `repurchase_price_upper`
- `ratio_to_cash`
- `direction`
- `severity`

### 4.2 `convertible_bond`

必选：

- `event_date`

建议抽取：

- `downward_revision_triggered`
- `premium_rate`
- `maturity_date`
- `direction`
- `severity`

### 4.3 `executive_change`

必选：

- `event_date`

建议抽取：

- `person_name`
- `position`
- `change_type`
- `direction`
- `severity`

### 4.4 `litigation`

必选：

- `event_date`

建议抽取：

- `amount`
- `counterparty`
- `ratio_to_net_profit`
- `case_stage`
- `severity`

### 4.5 `penalty_or_inquiry`

必选：

- `event_date`

建议抽取：

- `issuing_authority`
- `penalty_type`
- `subject`
- `amount`
- `severity`

### 4.6 `guarantee`

必选：

- `event_date`

建议抽取：

- `guaranteed_party`
- `guarantee_amount`
- `ratio_to_net_assets`
- `severity`

### 4.7 `related_party_transaction`

必选：

- `event_date`

建议抽取：

- `counterparty`
- `transaction_type`
- `amount`
- `pricing_basis`
- `severity`

### 4.8 `audit_opinion_issue`

必选：

- `event_date`

建议抽取：

- `opinion_type`
- `affected_scope`
- `auditor_or_board_source`
- `severity`

### 4.9 `internal_control_issue`

必选：

- `event_date`

建议抽取：

- `defect_level`
- `conclusion`
- `affected_scope`
- `severity`

### 4.10 `financial_anomaly`

必选：

- `period`

建议抽取：

- `metric_name`
- `current_value`
- `metric_unit`
- `fiscal_year`
- `severity`

## 5. JSON Schema（逻辑口径）

### 5.1 Extract Item Schema

```json
{
  "type": "object",
  "required": [
    "extract_family",
    "event_type",
    "parameters",
    "summary",
    "fact_tags",
    "evidence_excerpt"
  ],
  "properties": {
    "extract_family": {
      "type": "string",
      "enum": ["announcement_event", "opinion_conclusion", "financial_statement", "general"]
    },
    "event_type": {
      "type": "string",
      "enum": [
        "share_repurchase",
        "convertible_bond",
        "executive_change",
        "litigation",
        "penalty_or_inquiry",
        "guarantee",
        "related_party_transaction",
        "audit_opinion_issue",
        "internal_control_issue",
        "financial_anomaly"
      ]
    },
    "parameters": {
      "type": "object",
      "additionalProperties": true
    },
    "summary": {
      "type": "string",
      "minLength": 6
    },
    "fact_tags": {
      "type": "array",
      "items": { "type": "string" }
    },
    "evidence_excerpt": {
      "type": "string",
      "minLength": 6
    },
    "page_start": { "type": ["integer", "null"] },
    "page_end": { "type": ["integer", "null"] }
  }
}
```

## 6. 风险归纳字段结构（先定义）

第二条 AI 工作流先定义结构，不要求本轮全部实现：

```json
{
  "risk_name": "收入确认风险",
  "why_it_matters": "应收增长快于收入增长，回款与收入真实性需要重点复核。",
  "audit_focus": "收入真实性、应收可回收性",
  "next_step": "检查合同、验收单、期后回款和坏账计提依据。"
}
```

## 7. 落库建议

第一阶段落库优先级：

1. `document_extract_result`
   - 主存储
   - 保留 `summary`、`parameters`、`event_type`、`extract_family`、`evidence_excerpt`
2. `document_event_feature`
   - 机器消费特征层
   - 用于参数映射、事件特征、风险主链消费
3. `knowledge_chunk`
   - 检索副产物
   - 不作为结构化主真相来源

## 8. 当前仍需确认的点

以下点本轮不阻塞实现，但后续建议明确：

- `financial_anomaly` 是否要固定更细的参数键集
- 审计意见异常是否要把 `kams`、`emphasis_matter` 单独拆成结构化字段
- 事件参数是否要在后续版本引入“必填/可选/推断值来源”标记
