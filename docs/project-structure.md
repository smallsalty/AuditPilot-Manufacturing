# 项目构成说明

## 统计口径与阅读方式

- 本文只覆盖源码与配置范围内的文件：根目录关键配置、`apps`、`packages`、`scripts`、`docs`。
- 明确不纳入逐文件说明的内容：`node_modules`、`.next`、`.pytest_cache`、`__pycache__`、`.playwright-cli`、`output`、运行日志、压缩包和其他构建/缓存产物。
- 当前纳入口径下约包含：`apps` 131 个文件、`packages` 2 个、`scripts` 2 个、`docs` 4 个，以及根目录 7 个关键配置文件。
- 阅读顺序建议：先看“仓库总览”，再按“根目录 -> 后端 -> 前端 -> 共享类型 -> 脚本 -> 文档”逐层定位。

## 仓库总览

- `apps/backend`：FastAPI 后端，负责企业同步、文档入库、风险分析、问答、审计重点与报表接口。
- `apps/frontend`：Next.js 前端，负责企业切换、总览、风险清单、文档分析、审计重点和问答页面。
- `packages/shared-types`：前后端共享的 TypeScript 类型定义，约束接口数据结构。
- `scripts`：本地开发和服务启动脚本。
- `docs`：设计说明、规则来源和数据筛选策略文档。
- 根目录配置：工作区依赖、环境变量模板、README、组合部署入口等。

## 根目录关键配置文件

- `.env`：本地实际运行环境变量文件，给后端和脚本读取数据库、模型、数据源和前端 API 地址。
- `.env.example`：环境变量模板，定义最小可运行配置项，供新环境复制初始化。
- `.gitignore`：版本控制忽略规则，避免缓存、依赖、构建产物和敏感文件进入仓库。
- `README.md`：项目入口说明，概述系统目标、技术栈、运行方式和关键接口。
- `docker-compose.yml`：本地/测试环境的容器编排入口，当前主要拉起 PostgreSQL。
- `package.json`：根工作区 npm 清单，声明 monorepo 基础依赖和工作区范围。
- `package-lock.json`：根工作区依赖锁文件，固定前端依赖版本和安装结果。

## apps/backend

### 应用入口

- `apps/backend/pyproject.toml`：后端 Python 包配置，声明 FastAPI/SQLAlchemy/AkShare/pytest 等依赖并定义 `app*` 包安装方式。
- `apps/backend/scripts/debug_minimax.py`：本地调试 MiniMax/Anthropic 兼容接口的辅助脚本，用来排查模型连接和响应问题。

### app 顶层

- `apps/backend/app/__init__.py`：后端应用包标记文件，本身不承载业务逻辑。
- `apps/backend/app/main.py`：FastAPI 应用入口，注册 CORS、中枢路由、启动时建表和健康检查接口。

### app/ai

- `apps/backend/app/ai/audit_qa_server.py`：审计问答主服务，组织上下文、调用 LLM、清洗回答并输出引用与建议动作。
- `apps/backend/app/ai/llm_client.py`：统一的大模型客户端封装，负责与 Anthropic/MiniMax 兼容接口通信。
- `apps/backend/app/ai/risk_explanation_service.py`：把规则命中结果转换成更易读的风险摘要、解释和审计关注点。

### app/api

- `apps/backend/app/api/router.py`：后端总路由汇总文件，只负责把各个子路由模块注册进统一 API。

#### app/api/routes

- `apps/backend/app/api/routes/__init__.py`：路由包标记文件，不承载独立业务。
- `apps/backend/app/api/routes/audit_focus.py`：暴露审计重点接口，返回增强后的 `audit_focus` 结果。
- `apps/backend/app/api/routes/chat.py`：暴露企业问答接口，调用问答服务输出回答、引用和建议。
- `apps/backend/app/api/routes/companies.py`：暴露公司概览类接口，给前端企业页和概览页提供聚合视图。
- `apps/backend/app/api/routes/documents.py`：暴露文档列表、文档分析和文档明细相关接口。
- `apps/backend/app/api/routes/enterprises.py`：暴露企业详情、只读资源和税务风险等接口，是企业域数据的主要入口。
- `apps/backend/app/api/routes/ingestion.py`：暴露文档上传与入库接口，承接人工上传材料。
- `apps/backend/app/api/routes/reports.py`：暴露报表/导出类接口，把分析结果整理为报告输出。
- `apps/backend/app/api/routes/risk_analysis.py`：暴露风险分析运行、结果查询和结果覆写接口。
- `apps/backend/app/api/routes/sync.py`：暴露企业同步接口，触发 AkShare 和巨潮资讯数据同步。

### app/core

- `apps/backend/app/core/config.py`：集中定义后端运行配置和环境变量读取逻辑，是全局配置源头。
- `apps/backend/app/core/db.py`：集中定义 SQLAlchemy 引擎、会话和建表逻辑，给路由和服务提供数据库连接。

### app/models

- `apps/backend/app/models/__init__.py`：统一导出领域模型，方便其他模块按一个入口引用模型。
- `apps/backend/app/models/base.py`：声明 ORM 基类和时间戳混入等共用模型基础设施。
- `apps/backend/app/models/domain.py`：定义企业、文档、事件、风险结果、建议、知识片段等核心领域表结构。

### app/providers

- `apps/backend/app/providers/__init__.py`：统一导出 provider，供同步服务和其他服务按统一入口引用。

#### app/providers/audit

- `apps/backend/app/providers/audit/__init__.py`：审计数据 provider 子包导出入口。
- `apps/backend/app/providers/audit/akshare_fast_provider.py`：使用 AkShare 快速获取企业主数据或轻量审计相关信息。
- `apps/backend/app/providers/audit/announcement_event_matcher.py`：只基于巨潮公告标题做关键词匹配、别名归一和主事件归类。
- `apps/backend/app/providers/audit/base.py`：审计类 provider 基类，约束抓取接口形态。
- `apps/backend/app/providers/audit/cninfo_keywords.py`：巨潮公告标题分类配置源，定义类别、主关键词、别名和排除词。
- `apps/backend/app/providers/audit/cninfo_provider.py`：巨潮资讯抓取实现，负责公告查询、年报包补抓、标题命中元数据生成和粗分类。
- `apps/backend/app/providers/audit/tushare_fast_provider.py`：保留的 Tushare 快速 provider 实现，当前更多作为兼容或历史实现参考。

#### app/providers/documents

- `apps/backend/app/providers/documents/base.py`：文档类 provider 基类，约束文档获取或解析前的数据形态。

#### app/providers/financial

- `apps/backend/app/providers/financial/akshare_provider.py`：财务指标主 provider，负责从 AkShare 抓取三大报表和指标并归一入库。
- `apps/backend/app/providers/financial/base.py`：财务 provider 基类，定义财务数据抓取接口。
- `apps/backend/app/providers/financial/mock_provider.py`：模拟财务 provider，用于无真实源时的测试或演示。

#### app/providers/risk

- `apps/backend/app/providers/risk/base.py`：企业风险 provider 基类，约束风险信号输入格式。
- `apps/backend/app/providers/risk/mock_provider.py`：模拟风险 provider，用于演示或测试非正式风险信号。

### app/rag

- `apps/backend/app/rag/retrieval_service.py`：检索增强问答服务，负责从知识库或结构化结果中检索上下文。

### app/repositories

- `apps/backend/app/repositories/document_repository.py`：文档域仓储，封装文档、抽取结果、事件特征和覆写记录的读写。
- `apps/backend/app/repositories/enterprise_repository.py`：企业域仓储，封装企业、财务、事件、文档和运行状态的查询。
- `apps/backend/app/repositories/risk_repository.py`：风险域仓储，封装风险结果和审计建议的查询、清理与聚合。

### app/rule_engine

- `apps/backend/app/rule_engine/evaluator.py`：规则引擎执行器，负责把财务特征代入规则并产生命中结果与证据链。

### app/schemas

- `apps/backend/app/schemas/__init__.py`：Pydantic schema 的统一导出入口。
- `apps/backend/app/schemas/chat.py`：问答接口的请求/响应结构定义。
- `apps/backend/app/schemas/common.py`：通用 schema 片段和可复用字段定义。
- `apps/backend/app/schemas/document.py`：文档列表、抽取结果和文档分析相关 schema。
- `apps/backend/app/schemas/enterprise.py`：企业详情、企业准备状态、企业概览等 schema。
- `apps/backend/app/schemas/ingestion.py`：上传入库相关 schema。
- `apps/backend/app/schemas/report.py`：报表和导出结果的 schema。
- `apps/backend/app/schemas/risk.py`：风险分析、风险结果和审计重点相关 schema。
- `apps/backend/app/schemas/sync.py`：同步接口的摘要、诊断和空结果原因 schema。

### app/scripts

- `apps/backend/app/scripts/backfill_clean_display_fields.py`：对历史数据做显示字段回填和清洗的维护脚本。
- `apps/backend/app/scripts/init_db.py`：初始化数据库结构或基础表的脚本入口。
- `apps/backend/app/scripts/migrate_phase1_audit_sync.py`：审计同步第一阶段相关数据迁移脚本。
- `apps/backend/app/scripts/seed_demo.py`：导入演示数据、规则和示例企业的 seed 脚本。

### app/services

- `apps/backend/app/services/__init__.py`：服务层统一导出入口，把主要服务暴露给其他模块使用。
- `apps/backend/app/services/announcement_risk_service.py`：把标题命中的巨潮公告聚合成 `announcement_risks`、公告分数和分类摘要。
- `apps/backend/app/services/audit_focus_service.py`：把最终风险结果整理成审计重点、推荐程序和证据来源说明。
- `apps/backend/app/services/audit_overview_service.py`：聚合企业审计概览页面所需的数据摘要。
- `apps/backend/app/services/audit_sync_service.py`：企业同步主流程，协调 provider 抓取、文档/事件落库、去重和诊断信息写入。
- `apps/backend/app/services/dashboard_service.py`：构建总览页评分、雷达图、趋势和 Top 风险。
- `apps/backend/app/services/document_classify_service.py`：对文档做类型分类和显示标签归并。
- `apps/backend/app/services/document_feature_service.py`：从文档抽取结果中沉淀事件特征、财务特征和规则支撑信息。
- `apps/backend/app/services/document_risk_service.py`：把文档抽取、规则结果和覆写结果合并成最终风险清单。
- `apps/backend/app/services/document_service.py`：文档上传、解析、抽取和文档页查询的主服务。
- `apps/backend/app/services/enterprise_runtime_service.py`：构建企业运行时上下文，例如 readiness、同步状态和首页企业列表。
- `apps/backend/app/services/feature_engineering_service.py`：从财务指标和事件数据生成规则引擎需要的派生特征。
- `apps/backend/app/services/financial_analysis_service.py`：构建财报专项分析页所需的关键指标、异常点和摘要。
- `apps/backend/app/services/industry_benchmark_service.py`：行业基准比较服务，生成企业相对行业的差异分析。
- `apps/backend/app/services/industry_classifier_service.py`：行业分类服务，负责把企业映射到内部行业分组。
- `apps/backend/app/services/ingestion_service.py`：上传材料和外部输入的统一入库服务。
- `apps/backend/app/services/knowledge_index_service.py`：知识切片、向量索引或检索准备的构建服务。
- `apps/backend/app/services/report_service.py`：把企业画像、风险和审计重点整理为报告输出。
- `apps/backend/app/services/risk_analysis_service.py`：风险分析主流程，串联规则命中、税务风险、公告风险、异常检测和审计重点返回。
- `apps/backend/app/services/tax_risk_service.py`：税务风险模块，基于 AkShare 财报数据输出结构化 `tax_risks`。

### app/utils

- `apps/backend/app/utils/display_text.py`：显示文案清洗工具，统一处理标题、文件名和展示文本。
- `apps/backend/app/utils/documents.py`：文档处理通用工具，辅助解析、页码、文本提取等逻辑。
- `apps/backend/app/utils/embeddings.py`：嵌入或向量相关的通用工具函数。

### tests

- `apps/backend/tests/test_akshare_financial_provider.py`：验证 AkShare 财务 provider 的字段映射和税务指标采集。
- `apps/backend/tests/test_announcement_risk_service.py`：验证公告标题匹配、主事件选择、时间衰减和重复事件加重逻辑。
- `apps/backend/tests/test_audit_qa_server.py`：验证问答主服务的回答生成、清洗和引用行为。
- `apps/backend/tests/test_audit_qa_server_light_context.py`：验证轻上下文模式下的问答降级和输出稳定性。
- `apps/backend/tests/test_backfill_clean_display_fields.py`：验证显示字段回填脚本的清洗和迁移结果。
- `apps/backend/tests/test_chat_fallback_route.py`：验证问答接口在上下文不足或模型不可用时的降级路径。
- `apps/backend/tests/test_dashboard_service.py`：验证总览页评分、Top 风险和风险分桶逻辑。
- `apps/backend/tests/test_display_text.py`：验证显示文本清洗工具的规范化行为。
- `apps/backend/tests/test_document_extract_schema.py`：验证文档抽取结果结构和字段约束。
- `apps/backend/tests/test_document_risk_tax_mapping.py`：验证税务规则码到最终风险 key 的映射结果。
- `apps/backend/tests/test_enterprises_documents_route.py`：验证企业文档相关路由的返回结构和筛选逻辑。
- `apps/backend/tests/test_feature_engineering.py`：验证特征工程生成的派生指标和风险信号。
- `apps/backend/tests/test_financial_analysis_service.py`：验证财报专项分析服务的摘要、异常和证据聚合。
- `apps/backend/tests/test_industry_benchmark_service.py`：验证行业基准比较和行业分组匹配逻辑。
- `apps/backend/tests/test_ingestion_route.py`：验证上传入库接口的基本行为。
- `apps/backend/tests/test_llm_client.py`：验证 LLM 客户端的请求参数和响应处理。
- `apps/backend/tests/test_risk_analysis_service.py`：验证风险分析主流程，包括文档模式、税务风险和公告风险接入。
- `apps/backend/tests/test_risk_context_weighting.py`：验证规则命中时的上下文加权逻辑。
- `apps/backend/tests/test_rule_engine.py`：验证规则引擎基础命中行为和条件判断。
- `apps/backend/tests/test_rule_engine_context_weight.py`：验证规则引擎在上下文权重参与时的得分变化。
- `apps/backend/tests/test_sync_service.py`：验证企业同步窗口、补抓逻辑、空结果原因和标题命中公告转事件。
- `apps/backend/tests/test_tax_risk_service.py`：验证税务风险四类规则的命中、跳过和解释口径。
- `apps/backend/tests/test_tax_risks_route.py`：验证税务风险路由的返回结构。

## apps/frontend

### 配置文件

- `apps/frontend/.env.local`：前端本地环境变量文件，主要提供 `NEXT_PUBLIC_*` 运行时配置。
- `apps/frontend/next-env.d.ts`：Next.js 自动生成的类型声明入口，供 TypeScript 识别 Next 环境。
- `apps/frontend/next.config.mjs`：Next.js 项目配置文件，控制构建和运行行为。
- `apps/frontend/package.json`：前端包清单，声明 Next.js、React、ECharts、共享类型等依赖和脚本。
- `apps/frontend/postcss.config.js`：PostCSS 配置，承接 Tailwind CSS 构建链。
- `apps/frontend/tailwind.config.ts`：Tailwind 主题与扫描路径配置。
- `apps/frontend/tsconfig.json`：前端 TypeScript 编译配置。

### app 路由页面

- `apps/frontend/app/globals.css`：全局样式和主题基础样式定义。
- `apps/frontend/app/layout.tsx`：前端根布局，注入全局样式、企业上下文和整体框架壳。
- `apps/frontend/app/page.tsx`：总览首页，展示风险评分、雷达图、趋势和 Top 风险。
- `apps/frontend/app/audit-focus/page.tsx`：审计重点页面，展示推荐关注点、程序和证据提示。
- `apps/frontend/app/chat/page.tsx`：企业问答页面，承接审计问答和引用展示。
- `apps/frontend/app/documents/page.tsx`：文档分析页面，展示文档列表、抽取状态和财报专项分析。
- `apps/frontend/app/enterprises/[id]/page.tsx`：企业详情页，聚合企业资料、时间线和概况数据。
- `apps/frontend/app/risks/page.tsx`：风险清单页，展示最终风险项、证据链和风险分析运行结果。

### components

- `apps/frontend/components/app-shell.tsx`：页面外层应用框架，负责导航、头部和主内容布局。
- `apps/frontend/components/echart.tsx`：ECharts 的 React 封装组件，统一处理图表挂载与尺寸。
- `apps/frontend/components/enterprise-provider.tsx`：企业上下文提供者，负责当前企业状态、URL 参数和资源共享。
- `apps/frontend/components/enterprise-select.tsx`：企业选择输入组件，负责企业候选列表交互。
- `apps/frontend/components/enterprise-switcher.tsx`：企业切换组件，负责页面顶部的企业切换体验。
- `apps/frontend/components/risk-table.tsx`：风险表格组件，负责最终风险列表的展示与交互。
- `apps/frontend/components/stat-card.tsx`：总览页指标卡片组件。

#### components/ui

- `apps/frontend/components/ui/badge.tsx`：轻量标签组件，承载状态、等级和来源展示。
- `apps/frontend/components/ui/button.tsx`：按钮基础组件，统一按钮样式和变体。
- `apps/frontend/components/ui/card.tsx`：卡片基础组件，统一页面卡片容器风格。

### lib

- `apps/frontend/lib/api.ts`：前端 API 请求封装，统一调用后端接口。
- `apps/frontend/lib/dashboard.ts`：总览页图表和 Top 风险数据的前端整理逻辑。
- `apps/frontend/lib/display-labels.ts`：用户可见标签映射层，把接口枚举和值转成中文显示。
- `apps/frontend/lib/enterprise-resources.ts`：企业维度资源获取与缓存逻辑，封装多个页面共用的数据请求。
- `apps/frontend/lib/utils.ts`：前端通用工具函数，如样式合并和轻量格式化。

## packages/shared-types

- `packages/shared-types/package.json`：共享类型包配置，供前端以 workspace 方式直接引用。
- `packages/shared-types/src/index.ts`：集中定义前后端共享的接口类型，包括企业、风险、问答、文档、税务和公告风险结构。

## scripts

- `scripts/dev.ps1`：Windows 本地一键开发脚本，检查环境、安装依赖、校验数据库并同时拉起前后端。
- `scripts/server-run.sh`：Linux/macOS 或服务器环境的一键启动脚本，拉起 PostgreSQL、准备虚拟环境并启动后端。

## docs

- `docs/ai_parameter_schema.md`：记录 AI 参数和结构化输出相关的字段口径与约束。
- `docs/ai_workflow_design.md`：记录 AI 工作流设计，包括问答、抽取和解释链路的设计意图。
- `docs/document_collection_filtering_risk_scoring.md`：记录文档收集、筛选和风险评分口径。
- `docs/rules-and-sources.md`：记录风险规则和数据来源的整理说明，帮助理解规则和证据从哪里来。
