# AuditPilot 规则与信息源主文档

## 1. 文档说明

本文件是 `AuditPilot-Manufacturing` 当前版本的主维护文档，用于统一说明：

- 系统当前有效的风险判定规则口径
- 系统当前调用或接入的信息源渠道
- 当前已实现、Mock、预留的能力边界
- 风险识别所依赖的特征、证据和知识增强来源

维护原则：

- 后续若新增或调整 `audit_rules.json`、provider、信息渠道、主要特征工程口径、LLM/RAG 来源说明，应优先同步更新本文件。
- 本文件以当前代码与 seed 数据现状为准，不描述未落地的复杂实现细节。
- 本文件兼顾展示与维护，但优先保证可追溯到当前代码事实。

当前代码事实来源主要包括：

- `data/seeds/backend/audit_rules.json`
- `data/seeds/backend/knowledge_chunks.json`
- `apps/backend/app/providers/*`
- `apps/backend/app/services/ingestion_service.py`
- `apps/backend/app/services/feature_engineering_service.py`
- `apps/backend/app/services/document_service.py`
- `apps/backend/app/ai/llm_client.py`

## 2. 当前判定规则总览

### 2.1 收入确认风险

- 四季度收入占比异常偏高
- 应收账款增速显著高于营收增速
- 经营现金流与利润背离

### 2.2 存货减值/积压风险

- 存货增速高于营收增速且周转下降
- 行业需求下行时存货继续上升

### 2.3 应收账款回款风险

- 回款周期延长

### 2.4 合规与外部事件风险

- 诉讼、行政处罚、负面舆情集中出现

### 2.5 关联交易 / 内控风险

- 关联企业结构复杂
- 高管频繁变动

当前规则引擎支持的判定方式：

- `all` 逻辑：全部条件命中才触发
- `any` 逻辑：任一条件命中即可触发
- 指标-运算符-阈值结构：如 `metric > value`
- 结果返回：命中原因、证据链、风险等级、建议关注科目/流程/程序/证据类型

## 3. 规则明细

### 3.1 REV_Q4_SPIKE

- 规则编码：`REV_Q4_SPIKE`
- 规则名称：收入确认风险：四季度收入占比异常偏高
- 风险类别：财务风险
- 风险等级：HIGH
- 判定指标：`q4_revenue_ratio`
- 阈值 / 逻辑：`all`；四季度收入占比 `> 0.35`
- 重点科目：主营业务收入、应收账款、合同资产
- 重点流程：收入确认、期末截止、订单履约
- 建议程序：执行截止测试、抽查重大合同与签收单、检查期后退货与折让
- 建议证据：销售合同、出库与签收单、期后回款记录
- 当前实现状态：已实现

### 3.2 REV_AR_GAP

- 规则编码：`REV_AR_GAP`
- 规则名称：收入确认风险：应收账款增速显著高于营收增速
- 风险类别：财务风险
- 风险等级：HIGH
- 判定指标：`ar_revenue_growth_gap`
- 阈值 / 逻辑：`all`；应收账款增速显著高于营收增速 `> 0.1`
- 重点科目：应收账款、坏账准备、主营业务收入
- 重点流程：授信审批、销售回款、收入确认
- 建议程序：实施函证、复核账龄结构、执行期后回款测试
- 建议证据：应收账款明细、账龄分析、客户回款流水
- 当前实现状态：已实现

### 3.3 OCF_PROFIT_DIVERGENCE

- 规则编码：`OCF_PROFIT_DIVERGENCE`
- 规则名称：收入确认风险：经营现金流与利润背离
- 风险类别：财务风险
- 风险等级：HIGH
- 判定指标：`operating_cf_profit_ratio`
- 阈值 / 逻辑：`all`；经营现金流 / 净利润 `< 0.5`
- 重点科目：经营活动现金流量、主营业务收入、应收账款
- 重点流程：收款循环、收入确认、现金流分析
- 建议程序：比较利润与现金流差异、复核重大应收项目、抽取异常订单穿行测试
- 建议证据：现金流量表、银行回单、客户对账单
- 当前实现状态：已实现

### 3.4 INV_BACKLOG

- 规则编码：`INV_BACKLOG`
- 规则名称：存货减值 / 积压风险：存货增速高于营收增速且周转下降
- 风险类别：经营风险
- 风险等级：HIGH
- 判定指标：`inventory_revenue_growth_gap`、`inventory_turnover_delta`
- 阈值 / 逻辑：`all`；存货增速高于营收增速 `> 0.1`，且存货周转率变化 `< -0.2`
- 重点科目：存货、存货跌价准备
- 重点流程：采购与生产计划、仓储管理、减值测试
- 建议程序：实施存货监盘、执行库龄分析、复核跌价准备测算
- 建议证据：库存台账、库龄清单、跌价准备测算表
- 当前实现状态：已实现

### 3.5 INV_INDUSTRY_DOWN

- 规则编码：`INV_INDUSTRY_DOWN`
- 规则名称：存货减值 / 积压风险：行业需求下行时存货上升
- 风险类别：经营风险
- 风险等级：MEDIUM
- 判定指标：`industry_demand_down_inventory_up`
- 阈值 / 逻辑：`all`；行业需求下行时存货仍上升 `>= 1`
- 重点科目：存货、营业成本
- 重点流程：销售预测、生产排产、库存管理
- 建议程序：对比行业景气度与企业产销数据、复核滞销物料清单
- 建议证据：行业数据、产销报表、库存结构分析
- 当前实现状态：已实现

### 3.6 AR_COLLECTION

- 规则编码：`AR_COLLECTION`
- 规则名称：应收账款回款风险：回款周期延长
- 风险类别：财务风险
- 风险等级：HIGH
- 判定指标：`ar_turnover_delta`、`accounts_receivable_growth_rate`
- 阈值 / 逻辑：`all`；应收账款周转率下降 `< -0.3`，且应收账款规模明显上升 `> 0.1`
- 重点科目：应收账款、坏账准备
- 重点流程：信用管理、回款管理
- 建议程序：检查账龄结构变化、执行大额客户回款测试、复核坏账准备计提
- 建议证据：账龄表、回款台账、坏账测算底稿
- 当前实现状态：已实现

### 3.7 COMPLIANCE_EVENTS

- 规则编码：`COMPLIANCE_EVENTS`
- 规则名称：合规与外部事件风险：诉讼处罚及负面舆情
- 风险类别：合规风险
- 风险等级：MEDIUM
- 判定指标：`major_litigation_count`、`penalty_count`、`negative_sentiment_count`
- 阈值 / 逻辑：`any`；存在重大诉讼 / 行政处罚 / 负面舆情任一项即可触发
- 重点科目：预计负债、营业外支出、信息披露相关科目
- 重点流程：合规管理、法务审查、信息披露
- 建议程序：获取诉讼处罚资料、询问法务与合规负责人、复核是否充分披露
- 建议证据：法律函件、处罚决定书、董事会纪要
- 当前实现状态：已实现

### 3.8 RELATED_PARTY_CONTROL

- 规则编码：`RELATED_PARTY_CONTROL`
- 规则名称：关联交易 / 内控风险：关联结构复杂且高管频繁变动
- 风险类别：内控风险
- 风险等级：MEDIUM
- 判定指标：`related_party_complexity_score`、`executive_change_count`
- 阈值 / 逻辑：`any`；关联企业结构复杂或高管存在频繁变动任一项即可触发
- 重点科目：关联交易、其他应收应付、采购成本
- 重点流程：关联方识别、审批授权、内控执行
- 建议程序：获取关联方清单、检查审批链条、复核异常关联交易定价
- 建议证据：关联方台账、审批记录、合同与定价依据
- 当前实现状态：已实现

## 4. 当前信息源与渠道总览

### 4.1 财务与行情类

- 目标渠道：同花顺 iFinD、聚源、AkShare、Tushare
- 当前已实现渠道：`AkshareFinancialProvider`、`MockFinancialProvider`
- 当前调用方式：通过统一财务 provider 抽象层接入；优先 AkShare，失败时可回落到 Mock/seed
- 当前使用状态：AkShare 已实现；Mock 已实现；iFinD / 聚源 / Tushare 为预留方向
- 进入系统的表或模块：`financial_indicator`、`IngestionService.ingest_financials`
- 典型用途：营收、利润、现金流、应收、存货、毛利率、周转率等结构化指标导入

### 4.2 工商与风险事件类

- 目标渠道：天眼查、企查查、公开处罚 / 诉讼 / 被执行信息
- 当前已实现渠道：`MockCorporateRiskProvider`
- 当前调用方式：本地 Mock JSON 导入
- 当前使用状态：Mock 已实现；商业渠道为预留
- 进入系统的表或模块：`external_event`、`IngestionService.ingest_risk_events`
- 典型用途：诉讼、处罚、负面舆情、高管变动、关联方复杂度等事件型风险识别

### 4.3 文本与公告类

- 目标渠道：巨潮资讯公告 / 年报 PDF、RESSET 财经文本平台、新闻文本导入
- 当前已实现渠道：上传文档 + 本地解析
- 当前调用方式：`DocumentService.save_upload()` + `DocumentService.parse_document()`
- 当前使用状态：上传 / 解析已实现；RESSET 为预留
- 进入系统的表或模块：`document_meta`、`document_extract_result`、`knowledge_chunk`
- 典型用途：抽取 MD&A、风险提示、会计政策变化、重大事项、制造业风险关键词段落

### 4.4 宏观与行业类

- 目标渠道：国家统计局、FRED / IMF / World Bank、行业景气度数据
- 当前已实现渠道：本地 CSV / Mock
- 当前调用方式：`IngestionService.ingest_macro()`
- 当前使用状态：Mock 已实现；外部公开 API 为预留
- 进入系统的表或模块：`macro_indicator`、`industry_benchmark`
- 典型用途：景气度解释、行业需求对比、原材料与库存风险解释

### 4.5 AI / LLM / RAG 辅助类

- 目标渠道：MiniMax、未来可扩展其他 OpenAI-compatible 模型
- 当前已实现渠道：MiniMax OpenAI-compatible 接口、Mock 模式、本地轻量 embedding
- 当前调用方式：`LLMClient` + `RiskExplanationService` + `AuditQAServer` + `RetrievalService`
- 当前使用状态：MiniMax 已接入；无 key 时自动 Mock；RAG 已实现轻量版本
- 进入系统的表或模块：`knowledge_chunk`、风险解释服务、问答服务
- 典型用途：风险解释、审计重点建议、程序推荐、问答引用与知识增强

## 5. 当前已实现渠道状态

### 5.1 当前演示可运行渠道

- 财务指标：AkShare / Mock seed
- 风险事件：Mock JSON
- 宏观与行业：Mock CSV
- 文档：本地上传 + PDF / 文本解析
- 知识增强：seed 规则摘要、审计程序模板、文档片段
- LLM：MiniMax OpenAI-compatible 或 Mock 模式

### 5.2 目标商业渠道但尚未落地

- 同花顺 iFinD：预留
- 聚源：预留
- 天眼查：预留
- 企查查：预留
- RESSET：预留

### 5.3 当前渠道状态说明

- 已实现：代码中已有 provider/service 或已能通过 seed / mock 跑通
- Mock：已有演示数据与导入逻辑，但不代表真实线上直连
- 预留：架构上有扩展方向，但当前代码未直接实现

## 6. 风险判定所依赖的特征与证据类型

### 6.1 当前主要特征

当前特征工程逻辑由 `FeatureEngineeringService` 生成，已实现的核心特征包括：

- 营收增长率：`revenue_growth_rate`
- 净利润增长率：`net_profit_growth_rate`
- 经营现金流 / 净利润：`operating_cf_profit_ratio`
- 存货增长率：`inventory_growth_rate`
- 应收账款增长率：`accounts_receivable_growth_rate`
- 存货周转率变化：`inventory_turnover_delta`
- 应收账款周转率变化：`ar_turnover_delta`
- 毛利率波动：`gross_margin_volatility`
- 资产负债率变化：`debt_ratio_delta`
- 期间费用率变化：`expense_ratio_delta`
- 应收增速与营收增速差：`ar_revenue_growth_gap`
- 存货增速与营收增速差：`inventory_revenue_growth_gap`
- 四季度收入占比：`q4_revenue_ratio`
- 连续亏损：`consecutive_losses`
- 经营现金流持续为负：`operating_cf_negative_streak`
- 短期偿债压力：`short_term_debt_pressure`
- 重大诉讼计数：`major_litigation_count`
- 行政处罚计数：`penalty_count`
- 负面舆情计数：`negative_sentiment_count`
- 高管变动计数：`executive_change_count`
- 关联方复杂度：`related_party_complexity_score`
- 行业需求下行且存货上升：`industry_demand_down_inventory_up`

### 6.2 当前主要证据类型

系统当前生成和消费的主要证据类型包括：

- 财务指标：年度 / 季度结构化数据
- 外部事件：诉讼、处罚、负面舆情、高管变动、关联方事件
- 文档抽取段落：MD&A、风险提示、会计政策变化、重大事项
- 行业与宏观对比：行业景气度、PPI、PMI、原材料价格等
- 规则库摘要：风险主题的规则说明文本
- 审计程序模板：重点科目对应的程序建议

### 6.3 当前知识增强来源

`knowledge_chunk` 当前主要承载以下内容：

- 规则摘要
- 审计程序模板
- 文档抽取结果
- 企业范围内的年报风险提示片段

## 7. 已知限制与后续补充方向

### 7.1 当前限制

- 财务真实直连当前主要依赖 AkShare，稳定性受外部公开接口影响
- 工商、处罚、诉讼、高管变动当前仍主要依赖 Mock 数据
- 文本知识增强当前为轻量实现，embedding 采用本地哈希向量，不等同于生产级语义检索
- LLM 当前采用 MiniMax OpenAI-compatible 接入；若 key 缺失或服务端拒绝，则自动退回 Mock 模式
- 规则集目前主要覆盖制造业上市公司演示场景，行业泛化能力尚未扩展

### 7.2 后续补充方向

- 接入 iFinD / 聚源等商业财务数据源
- 接入天眼查 / 企查查等商业风险渠道
- 增强公告、新闻、年报的真实采集流程
- 将规则维护从 seed JSON 进一步升级为后台可配置
- 增强向量检索与案例库建设
- 将行业模板从制造业扩展到其他行业

## 8. 最近更新记录

- 2026-04-08：新增本主文档，统一沉淀当前有效规则、信息渠道、特征口径与维护约定。影响范围：规则说明、信息源说明、后续维护方式。

## 9. 附录清单

### 9.1 规则清单总表

| 规则编码 | 风险主题 | 风险等级 | 主要指标 | 状态 |
| --- | --- | --- | --- | --- |
| REV_Q4_SPIKE | 收入确认风险 | HIGH | q4_revenue_ratio | 已实现 |
| REV_AR_GAP | 收入确认风险 | HIGH | ar_revenue_growth_gap | 已实现 |
| OCF_PROFIT_DIVERGENCE | 收入确认风险 | HIGH | operating_cf_profit_ratio | 已实现 |
| INV_BACKLOG | 存货减值 / 积压风险 | HIGH | inventory_revenue_growth_gap, inventory_turnover_delta | 已实现 |
| INV_INDUSTRY_DOWN | 存货减值 / 积压风险 | MEDIUM | industry_demand_down_inventory_up | 已实现 |
| AR_COLLECTION | 应收账款回款风险 | HIGH | ar_turnover_delta, accounts_receivable_growth_rate | 已实现 |
| COMPLIANCE_EVENTS | 合规与外部事件风险 | MEDIUM | major_litigation_count, penalty_count, negative_sentiment_count | 已实现 |
| RELATED_PARTY_CONTROL | 关联交易 / 内控风险 | MEDIUM | related_party_complexity_score, executive_change_count | 已实现 |

### 9.2 渠道清单总表

| 数据类型 | 目标渠道 | 当前已实现渠道 | 当前状态 | 进入系统位置 |
| --- | --- | --- | --- | --- |
| 财务与行情 | iFinD、聚源、AkShare、Tushare | AkShare、Mock seed | 已实现 + Mock |
| 工商与风险事件 | 天眼查、企查查、公开处罚 / 诉讼 | Mock JSON | Mock |
| 文本与公告 | 巨潮资讯、RESSET、新闻文本 | 上传文档 + 本地解析 | 已实现 |
| 宏观与行业 | 国家统计局、FRED / IMF / WB | 本地 CSV / Mock | 已实现 + Mock |
| AI / LLM | MiniMax、其他兼容模型 | MiniMax OpenAI-compatible、Mock | 已实现 |
| RAG / 知识增强 | 文档、规则、程序模板、案例 | knowledge_chunk | 已实现 |

### 9.3 当前实现状态清单

| 项目 | 当前状态 | 说明 |
| --- | --- | --- |
| 规则引擎 | 已实现 | 支持 `all` / `any`、阈值判定、命中原因与证据链 |
| 财务 provider | 已实现 | AkShare + Mock |
| 风险事件 provider | 已实现 | Mock |
| 文档解析 | 已实现 | PDF / 文本解析、关键词抽取、入库 |
| 宏观 / 行业数据导入 | 已实现 | 本地 CSV |
| MiniMax 接入 | 已实现 | OpenAI-compatible，支持 Mock 兜底 |
| 轻量 RAG | 已实现 | 基于 `knowledge_chunk` 和本地 embedding |
| 商业数据源直连 | 预留 | iFinD、聚源、天眼查、RESSET 等待扩展 |
