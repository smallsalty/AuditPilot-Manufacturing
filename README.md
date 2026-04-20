# AuditPilot-Manufacturing

制造业上市公司审计风险识别与审计重点生成系统。

系统围绕企业官方公告、年报、审计报告、内控报告和用户上传文档，完成文档解析、事件公告分析、风险清单生成、财报专项分析和审计重点建议生成。前端负责文档中心、风险清单、公告事件和审计重点展示；后端负责数据同步、PDF 解析、MiniMax 调用、风险识别和结果持久化。

## 技术架构

- Frontend：Next.js 14、TypeScript、Tailwind CSS、ECharts
- Backend：FastAPI、SQLAlchemy、Pydantic
- Database：PostgreSQL
- AI：MiniMax Anthropic-compatible API
- 数据来源：巨潮资讯、AkShare、用户上传文件
- 文档解析：pdfplumber、pypdf

## 核心能力

- 企业数据与公告同步：同步企业基础资料、巨潮公告、年报、审计报告、内控报告和事件类公告。
- 文档中心：支持上传文档、解析文档、查看抽取结果、查看原文件、删除文档。
- 文档抽取：对年报、审计报告、内控报告等文档抽取风险证据、财报专项信息和事件线索。
- 事件公告分析：巨潮事件类公告按标题识别事件类型，并下载/解析正文，调用 MiniMax 生成正文层面的审计风险总结。
- 风险清单：融合财务指标、文档抽取、公告事件和规则结果，生成企业风险清单。
- 财报专项分析：聚合文档中的财报异常证据，并持久化 MiniMax 总结，避免输入未变化时重复分析。
- 审计重点：基于风险清单和证据，调用 MiniMax 生成针对性审计建议，并持久化快照避免重复生成。
- 问答与报告：基于已有风险、文档证据和知识片段提供审计问答与报告接口。

`seed`、`mock` 和演示数据仅用于开发辅助，不属于正式运行数据来源。

## 目录结构

```text
apps/
  backend/              FastAPI 后端
    app/
      api/              API 路由
      ai/               MiniMax 客户端和提示词服务
      models/           SQLAlchemy 模型
      providers/        巨潮、AkShare 数据源
      scripts/          后端脚本入口
      services/         同步、解析、风险分析等业务服务
  frontend/             Next.js 前端
packages/
  shared-types/         前后端共享 TypeScript 类型
docs/                   项目说明文档
docker/                 数据库初始化脚本
```

更完整的结构说明见 [docs/project-structure.md](./docs/project-structure.md)。

## 环境变量

复制 `.env.example` 为 `.env`，至少配置以下变量：

```env
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://postgres:123456@localhost:5432/appdb

LLM_PROVIDER=minimax
ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M2.7

AKSHARE_ENABLE=true
CNINFO_ENABLE=true
CNINFO_QUERY_URL=https://www.cninfo.com.cn/new/hisAnnouncement/query
CNINFO_STATIC_BASE_URL=https://static.cninfo.com.cn
SYNC_LOOKBACK_DAYS=7
SYNC_INITIAL_LOOKBACK_DAYS=365

BACKEND_CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://60.205.216.59:8000
```

说明：

- `ANTHROPIC_API_KEY` 使用 MiniMax Anthropic-compatible API Key。
- `NEXT_PUBLIC_API_BASE_URL` 是前端访问后端的地址，本地前端连接云端后端时应指向云服务器 API。
- 当前正式数据源不使用 `TUSHARE_*`。
- 如果 MiniMax 配置缺失，部分 AI 能力会降级或使用 fallback，不建议作为生产状态。

## 本地开发

### 启动数据库

仓库提供 PostgreSQL docker-compose 配置：

```powershell
docker compose up -d postgres
```

### 启动后端

后端需要 Python 3.11+。首次使用建议在 `apps/backend` 下安装依赖：

```powershell
cd apps/backend
python -m pip install -e .
python -m app.scripts.init_db
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端启动时也会执行基础表结构初始化。

### 启动前端

从仓库根目录安装依赖并启动前端：

```powershell
npm install
npm --workspace apps/frontend run dev
```

或进入前端目录：

```powershell
cd apps/frontend
npm run dev
```

默认前端地址为 `http://localhost:3000`。

## 本地前端连接云端后端

如果后端部署在云服务器，本地只运行前端即可。

在 `apps/frontend/.env.local` 或根目录 `.env` 中设置：

```env
NEXT_PUBLIC_API_BASE_URL=http://你的云服务器IP:8000
```

云端后端需要允许本地前端来源：

```env
BACKEND_CORS_ORIGINS=http://localhost:3000
```

然后启动前端：

```powershell
npm --workspace apps/frontend run dev
```

## 云端部署要点

云端后端建议长期运行 FastAPI 服务，并使用 PostgreSQL 作为持久化数据库：

```bash
cd apps/backend
python -m pip install -e .
python -m app.scripts.init_db
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

生产环境应至少确认：

- `DATABASE_URL` 指向云端 PostgreSQL。
- `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL` 已配置。
- `CNINFO_ENABLE=true` 且巨潮 URL 配置正确。
- `BACKEND_CORS_ORIGINS` 包含实际前端域名。
- 上传目录和日志目录具备写入权限。

前端构建：

```powershell
npm --workspace apps/frontend run build
npm --workspace apps/frontend run start
```

## 巨潮公告每日定时监控

后端提供独立脚本用于云服务器每日自动监控巨潮公告：

```bash
cd apps/backend
python -m app.scripts.daily_cninfo_monitor --verbose
```

脚本会遍历当前系统企业，执行：

- 巨潮公告同步
- 文档和事件解析队列处理
- 新增数据触发风险分析
- 审计重点快照刷新
- JSON 格式监控摘要输出

可指定单个企业和日期范围：

```bash
python -m app.scripts.daily_cninfo_monitor --enterprise-id 1 --date-from 2026-04-19 --date-to 2026-04-20 --verbose
```

### Windows Task Scheduler

建议配置：

- Program：`python`
- Arguments：`-m app.scripts.daily_cninfo_monitor --verbose`
- Start in：`D:\firstmoney\AuditPilot-Manufacturing\apps\backend`

### Linux cron

示例，每天 02:00 执行：

```cron
0 2 * * * cd /path/to/AuditPilot-Manufacturing/apps/backend && python -m app.scripts.daily_cninfo_monitor --verbose >> /var/log/auditpilot-cninfo-monitor.log 2>&1
```

## 关键接口

所有业务接口默认带 `/api` 前缀。

### 企业与概览

- `GET /api/enterprises`
- `POST /api/enterprises/bootstrap`
- `GET /api/enterprises/{enterprise_id}`
- `GET /api/enterprises/{enterprise_id}/dashboard`
- `GET /api/companies/{company_id}/readiness`
- `GET /api/companies/{company_id}/audit-profile`
- `GET /api/companies/{company_id}/timeline`
- `GET /api/companies/{company_id}/risk-summary`

### 同步与文档

- `POST /api/sync/company`
- `GET /api/enterprises/{enterprise_id}/documents`
- `POST /api/ingestion/documents/upload`
- `POST /api/documents/{document_id}/parse`
- `GET /api/documents/{document_id}/extracts`
- `GET /api/documents/{document_id}/file`
- `DELETE /api/documents/{document_id}`
- `PATCH /api/documents/{document_id}/classification`
- `PATCH /api/documents/{document_id}/extracts/{evidence_span_id}/event-type`

### 事件、风险与审计

- `GET /api/enterprises/{enterprise_id}/events`
- `GET /api/enterprises/{enterprise_id}/financial-analysis`
- `GET /api/enterprises/{enterprise_id}/tax-risks`
- `POST /api/risk-analysis/{enterprise_id}/run`
- `GET /api/risk-analysis/{enterprise_id}/results`
- `PATCH /api/risk-analysis/{enterprise_id}/overrides/{canonical_risk_key}`
- `GET /api/audit-focus/{enterprise_id}`

### 问答与报告

- `POST /api/chat/{enterprise_id}`
- `GET /api/reports/{enterprise_id}`

## 常用流程

1. 启动后端和前端。
2. 调用或点击企业初始化：`POST /api/enterprises/bootstrap`。
3. 同步官方数据：`POST /api/sync/company`。
4. 在文档中心查看文档、解析状态、抽取结果和原文件。
5. 运行风险分析：`POST /api/risk-analysis/{enterprise_id}/run`。
6. 查看风险清单、财报专项分析、公告事件解释层和审计重点。
7. 云端部署后用每日定时监控脚本持续刷新巨潮公告事件。

## 静态检查

后端静态编译检查：

```bash
cd apps/backend
python -m compileall app
```

前端构建检查：

```powershell
npm --workspace apps/frontend run build
```

或仅做 TypeScript 检查：

```powershell
cd apps/frontend
npx tsc --noEmit --incremental false
```

## 注意事项

- 不要把 MiniMax API Key 提交到仓库。
- 定时监控脚本会触发同步、解析和必要的风险分析，应只在服务端计划任务中运行。
- 文档删除接口会删除关联抽取、事件特征、人工修正和知识片段，并仅在路径安全时删除本地原文件。
- 财报专项分析和审计重点已使用快照机制，同一批输入未变化时不会重复调用 MiniMax。
- 事件公告正文分析结果写入 `ExternalEvent.payload.event_analysis`，不新增数据库表。
