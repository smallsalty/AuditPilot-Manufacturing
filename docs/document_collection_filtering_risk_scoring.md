# 文档搜集、筛选总结与风险评分规则说明

本文记录当前项目中已经实现的文档搜集、文档筛选/抽取总结、风险评分规则。本文只描述现有实现，不代表新增功能。

## 1. 文档搜集规则

### 1.1 数据来源

当前官方文档和公告主要来自 CNInfo/巨潮资讯链路：

- `CninfoProvider`：负责查询公告、识别公告类型、构造文档下载地址。
- `AuditSyncService`：负责同步企业官方公告/文档并落库到 `DocumentMeta` 或 `ExternalEvent`。
- `POST /api/sync/company`：企业同步入口。

当前同步链路的目标是“同步官方文档/事件”，不是自动解析全文。同步完成后，文档可以进入 `parse_queued` 等待手动解析，但不会自动调用文档解析队列。

### 1.2 通用公告窗口抓取

同步企业时会按当前配置窗口抓取 CNInfo 公告。抓取结果按公告标题和类型分流：

- 文档类：写入 `DocumentMeta`。
- 事件/公告类：写入 `ExternalEvent`。
- 无法归类或无关公告：保留为其他类型或不进入文档中心。

同步时会按 `source_object_id`、标题、公告日期、内容哈希等信息做去重，避免同一公告重复入库。

### 1.3 年报包补抓

首次同步或通用窗口没有抓到足够文档时，当前实现会补抓最近财年的“年报包”。关键词包括：

- 年度报告
- 年度报告摘要
- 年度审计报告
- 年度内部控制评价报告
- 年度内部控制审计报告
- 非经营性资金占用专项说明
- 专项审计报告

补抓通常覆盖目标财年及上一财年，用于处理“财年在当年、披露在次年”的情况。

### 1.4 文档类型识别口径

当前文档分类主要依赖标题关键词、同步来源和后续解析分类，典型类型包括：

- `annual_report`：年度报告。
- `annual_summary`：年度报告摘要。
- `audit_report`：审计报告。
- `internal_control_report`：内部控制评价报告或内部控制审计报告。
- `interim_report`：半年度报告。
- `quarter_report`：季度报告。
- `announcement_event`：公告事件，例如高管变动、诉讼处罚、回购、担保、关联交易等。
- `general`：无法明确归类的文档。

当前同步入库时会清洗标题展示字段，去除 CNInfo 高亮标签，例如 `<em>...</em>`。

## 2. 文档筛选与抽取总结规则

### 2.1 文本清洗

`DocumentService` 负责文档解析。解析前会对文本做基础清洗和切分，目标是减少封面、目录、页码、免责声明等噪声。

当前清洗规则包括：

- 去除 HTML 标签和搜索高亮标签。
- 合并连续空白。
- 删除页码、目录、封面标题、日期行、事务所页脚等低价值内容。
- 压缩重复标题和重复短句。
- 对 `summary`、`evidence_excerpt`、`subject` 等展示字段再次做轻量清洗。

### 2.2 候选段落构建

解析后的文本会被切成候选段落。`DocumentService._build_candidate()` 会根据文档类型和段落内容构建候选抽取项。

候选项通常包含：

- `title`
- `summary`
- `problem_summary`
- `evidence_excerpt`
- `event_type`
- `extract_family`
- `parameters`
- `canonical_risk_key`
- `detail_level`
- `financial_topics`
- `risk_points`
- `section_title`
- `page_start` / `page_end`

候选会按文档类型限制数量，避免把全文全部送入模型。

### 2.3 LLM 抽取与规则 fallback

文档抽取优先尝试通过统一 `LLMClient` 调 MiniMax Anthropic 兼容接口。LLM 输出失败或不可用时，不会让文档解析整体失败，而是回退到规则候选结果。

当前抽取模式包括：

- `llm_primary`：LLM 返回有效结构化结果。
- `hybrid_fallback`：LLM 尝试失败或结果不完整，回退规则结果。
- `rule_only`：未调用 LLM 或配置不可用，直接使用规则候选。

解析状态会写入 `metadata_json.analysis_status / analysis_meta / last_error`。

### 2.4 JSON 容错

LLM 返回 JSON 时，当前实现支持多种容错路径：

- 顶层 JSON 对象。
- 顶层 JSON 数组。
- 包含 `items` 或 `extracts` 的对象。
- 前后带说明文字的 JSON。
- `raw_text` fallback。
- 截断数组中已经完整闭合的对象会被部分恢复。

如果完全无法恢复结构化结果，会记录 fallback 信息并使用规则抽取结果，不把接口视为不可用。

### 2.5 抽取分类强映射

LLM 返回的 `extract_family` 不会被完全信任。当前实现会根据 `event_type` 做固定后处理映射，避免典型错配。

当前关键映射包括：

- `financial_anomaly -> financial_statement`
- `audit_opinion_issue -> opinion_conclusion`
- `internal_control_issue -> internal_control_conclusion`
- `executive_change -> announcement_event`
- `major_contract -> announcement_event`
- `related_party_transaction -> announcement_event`
- `share_repurchase -> announcement_event`
- `equity_pledge -> announcement_event`
- `penalty_or_inquiry -> announcement_event`
- `litigation_arbitration -> announcement_event`

未识别事件类型会根据审计意见、财务指标和文档类型做降级判断，否则落到 `general`。

## 3. 风险评分与结果生成规则

### 3.1 风险来源

当前风险结果主要来自两条链路：

- 结构化规则风险：`RiskAnalysisService + RuleEvaluator + audit_rules.json`
- 文档主导风险：`DocumentRiskService.list_risks()`

其中，文档-only 企业也允许运行风险分析。没有财务指标和外部事件时，风险结果以文档抽取风险为主。

### 3.2 结构化规则风险

`RiskAnalysisService.run()` 会读取企业财务指标、外部事件和行业基准，调用 `FeatureEngineeringService.build_features()` 生成特征，再用 `RuleEvaluator` 匹配 `data/seeds/backend/audit_rules.json` 中的规则。

`RuleEvaluator` 的规则命中逻辑：

- 每条规则包含 `conditions`。
- 条件支持 `>`、`>=`、`<`、`<=`、`==`。
- 规则支持 `logic=all` 或 `logic=any`。
- 命中后生成 `RuleHit`，包含原因和证据链。

结构化规则风险评分公式为：

```text
risk_score = min(100, rule.weight * 20 + 命中原因数 * 10)
```

风险结果会写入 `RiskIdentificationResult`，并按 `risk_score desc` 排序展示。

### 3.3 文档主导风险

`DocumentRiskService.list_risks()` 会聚合当前文档抽取结果和文档事件特征，生成以文档证据为主的风险项。

文档风险聚合会参考：

- `canonical_risk_key`
- `event_type`
- `extract_family`
- 财务异常指标
- 审计意见异常
- 内部控制缺陷
- 治理变动
- 诉讼处罚、问询、担保、关联交易等公告事件
- 证据片段和来源文档

文档风险结果通常包含：

- `risk_name`
- `risk_level`
- `risk_score`
- `summary`
- `reasons`
- `evidence`
- `source_documents`
- `source_events`
- `feature_support`

文档主导风险会保留证据链，风险页和 AI 问答都会优先引用这些证据。

### 3.4 模型异常检测

当企业有足够年度财务数据时，`RiskAnalysisService._run_anomaly_detection()` 会用 IsolationForest 对历史年度财务指标做异常检测。

当前输入指标包括：

- revenue
- net_profit
- operating_cash_flow
- accounts_receivable
- inventory

样本不足 3 年时不会运行该检测。

## 4. 当前缺口

### 4.1 动态行业基准库尚未完整实现

项目已有 `IndustryBenchmark` 表，也有 mock 行业基准字段，例如：

- `gross_margin_benchmark`
- `ar_turnover_benchmark`
- `inventory_turnover_benchmark`
- `demand_index_yoy`

但当前完整风险链路只显式使用了 `demand_index_yoy` 这类行业需求信号。毛利率和应收账款周转率的“企业 vs 行业均值”离群分析尚未完整接入。

因此，目前还没有完整实现：

- 动态计算同行业平均毛利率。
- 动态计算同行业平均应收账款周转率。
- 计算企业相对行业均值的 z-score 或分位数。
- 基于“个体 vs 行业”的超额盈利风险规则。

### 4.2 LLM 摘要不是风险结果可用前提

MiniMax 摘要失败、限流、过载或返回不规范 JSON 时，系统会 fallback 到本地摘要或规则抽取结果。

风险结果是否可用，应以结构化抽取、规则命中和文档证据链为准，不应以 LLM 摘要是否成功为准。

### 4.3 文档解析仍可能遇到截断 JSON

LLM 仍可能返回截断 JSON 或不完整数组。当前业务层会尽量恢复已完整闭合的对象；无法恢复时会走规则 fallback。

这类日志不等同于接口不可用，但需要结合 `analysis_mode`、`analysis_status` 和最终抽取结果判断解析质量。

### 4.4 mock 行业基准与正式行业基准要区分

当前仓库包含 mock 行业基准 CSV，用于演示和测试。正式分析中应避免把 mock 数据误当作生产可信来源。

后续如果实现动态行业基准库，应明确：

- 行业分类来源。
- 同业样本选取规则。
- 基准计算周期。
- 样本数量下限。
- 异常值剔除规则。
- 行业基准来源标记。
