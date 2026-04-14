# AuditPilot AI 工作流设计（V1 第一阶段）

## 1. 目标

本设计文档定义 AuditPilot 当前两条 AI 工作流的职责边界，其中本轮只实现第一条的最小可用版本。

目标不是完整审计底稿，而是公开信息驱动的：

- 风险识别
- 审计重点提示
- 持续监控

数据底座限定为：

- `AkShare`
- `cninfo`
- `upload`

## 2. 工作流一：文档事件与参数抽取

### 2.1 输入

- 清洗后的年报、年报摘要候选段
- 审计报告候选段
- 内部控制评价/审计报告候选段
- 重大公告候选段

### 2.2 输出

每条输出固定包含：

- `extract_family`
- `event_type`
- `parameters`
- `summary`
- `fact_tags`
- `evidence_excerpt`
- `page_start`
- `page_end`

### 2.3 处理链

第一阶段处理链固定为：

1. 原文解析
2. 文档分型
3. 候选段筛选
4. 规则抽取候选
5. `LLM` 对候选段做结构化归纳
6. 失败时回退到规则抽取结果
7. 写入结构化主存储
8. 同步事件特征
9. 生成检索副产物

### 2.4 第一阶段范围

优先跑通：

- `announcement_event`
- `audit_opinion_issue`
- `internal_control_issue`

轻量支持：

- `annual_report`
- `annual_summary`

年报类第一阶段只要求产出：

- `financial_anomaly`
- 基础 `summary`
- `fact_tags`
- `evidence_excerpt`

### 2.5 设计约束

- `LLM` 只处理候选段，不处理整篇 PDF
- `summary` 必须是一句话
- `parameters` 必须是扁平 JSON 对象
- 不允许开放式 `event_type`
- 必须保留规则兜底
- 不直接把原始 PDF 段落暴露给风险页

## 3. 工作流二：风险归纳与审计提示

### 3.1 本轮定位

本轮只完成设计，不急着全部实现。

### 3.2 固定输出

风险归纳结果固定四项：

- 风险是什么
- 为什么值得关注
- 对应哪个审计重点
- 下一步建议看什么

对应字段：

- `risk_name`
- `why_it_matters`
- `audit_focus`
- `next_step`

### 3.3 目标主链

后续主链为：

1. 工作流一输出 `event_type + parameters + summary`
2. 事件与意见映射到 `canonical_risk_key`
3. 合并结构化财务规则结果
4. 生成聚合风险
5. 产出审计重点和问答证据

### 3.4 本轮只做的代码准备

- 结构化抽取结果补齐 `summary + parameters`
- 事件特征层保留对 `parameters` 的消费能力
- 风险主链继续复用现有 `DocumentRiskService`
- 不重写风险页

## 4. Schema 与接口位置

### 4.1 主存储

- `document_extract_result`
- `document_event_feature`

### 4.2 检索副产物

- `knowledge_chunk`

### 4.3 当前接口

- `GET /api/documents/{id}/extracts`

本轮只做增量扩展，不改路由语义。

## 5. 证据层级

证据层级固定为：

1. 文档抽取主存储
2. 事件特征
3. 聚合风险
4. `knowledge_chunk`
5. `llm_output`

其中：

- `knowledge_chunk` 是检索副产物
- `llm_output` 是派生结果
- 任何模型输出都不能替代原始证据和结构化主存储

## 6. 第一阶段测试要求

至少覆盖以下样例：

- 回购公告
- 可转债公告
- 高管变动公告
- 诉讼/处罚公告
- 关联交易公告
- 非标审计意见
- 内控缺陷
- 年报类 `financial_anomaly`

验证点固定为：

- `event_type` 命中固定枚举
- `summary` 为一句话，且不等于整段原文
- `parameters` 为对象
- `evidence_excerpt` 可追溯
- `LLM` 不可用时规则兜底仍可产出结构化结果

## 7. 下一步最适合继续实现的部分

本轮完成后，下一段最适合继续做的是：

1. 把 `parameters` 与 `DocumentRiskService` 的 `source_events / feature_support` 做更细映射
2. 为第二条工作流新增风险归纳模板输出
3. 再让审计重点与问答优先消费该归纳结果
