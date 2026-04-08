# AuditPilot-Manufacturing

制造业上市公司智能风险识别与审计重点提示系统原型。

## 架构概览

- 前端：Next.js + TypeScript + Tailwind CSS + ECharts
- 后端：FastAPI + SQLAlchemy + PostgreSQL
- 向量检索：本地 HashingVectorizer 轻量 RAG，Docker 初始化预留 pgvector 扩展
- AI：MiniMax OpenAI 兼容封装，未配置密钥时自动降级 Mock

## 目录结构

```text
apps/
  backend/
  frontend/
packages/
  shared-types/
data/
  mock/
  seeds/
docs/
docker/
```

## 环境变量

复制 `.env.example` 为 `.env`，至少配置：

- `DATABASE_URL`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `AKSHARE_ENABLE`
- `NEXT_PUBLIC_API_BASE_URL`

说明：

- `.env` 以服务器数据库架构为准，Windows 本地开发与 Ubuntu 服务器 backend 共用同一套核心数据库配置
- 不再提供任何本地 PostgreSQL 专用配置示例
- `LLM_API_KEY` 为空时系统自动进入 Mock 模式

## 一键运行

### Windows 本地开发

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

首次运行时会按需完成：

- 创建 `apps/backend/.venv`
- 安装后端依赖
- 安装前端依赖
- 检查远程/服务器数据库是否 ready
- 启动 FastAPI 与 Next.js

如需初始化或重置 demo 数据：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Seed
```

### Ubuntu 服务器后端

```bash
chmod +x scripts/server-run.sh
bash scripts/server-run.sh
```

该脚本会：

- 启动 `postgres` 容器
- 按需创建 `apps/backend/.venv`
- 按需安装后端依赖
- 检查数据库是否 ready
- 启动 FastAPI

如需初始化或重置 demo 数据：

```bash
bash scripts/server-run.sh --seed
```

## 手动启动方式

### 服务器数据库容器

```bash
docker compose up -d postgres
```

数据库容器启动后，后端使用服务器本机 Python 3.11 运行，不使用 backend 容器。

### 后端本机运行

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Linux 服务器可将激活命令替换为：

```bash
source .venv/bin/activate
```

### 前端本地开发

```bash
cd apps/frontend
npm install
npm run dev
```

## 数据导入与演示

1. 启动数据库与后端。
2. 首次初始化数据库或需要重置 demo 数据时，再运行 `python -m app.scripts.seed_demo`。
3. 打开前端首页，选择三一重工。
4. 在风险清单页点击“运行风险分析”。
5. 在审计重点页查看重点科目、流程、审计程序。
6. 在 AI 问答页追问风险原因或建议程序。

## 推荐环境变量示例

```env
DATABASE_URL=postgresql+psycopg://user:password@server_ip:5432/dbname
LLM_PROVIDER=minimax
LLM_API_KEY=your_key_here
LLM_BASE_URL=https://api.minimax.io/v1
LLM_MODEL=your_exact_minimax_model_name
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
BACKEND_CORS_ORIGINS=http://localhost:3000
```

如果前端不是本地开发而是直连服务器后端，可将 `NEXT_PUBLIC_API_BASE_URL` 改为服务器地址。

## 文档解析

- 文档中心支持上传 PDF。
- 后端使用 `pdfplumber` 解析，`pypdf` 作为兜底。
- 可抽取 MD&A、风险提示、会计政策变化、重大事项和制造业风险关键词片段。

## MiniMax Mock 模式

当 `LLM_API_KEY` 为空时：

- 风险解释服务自动使用内置 Mock 模板生成摘要
- 审计问答返回基于规则和知识片段拼接的可解释答案
- 不会阻断整体演示流程

## 数据源策略

- 结构化财务数据优先使用 `AkshareFinancialProvider`
- 若联机失败，则透明回退至本地 seed 数据
- 工商、处罚、诉讼、高管变动采用 Mock provider
- 宏观与行业数据从 `data/mock` 导入

## 测试

```bash
cd apps/backend
pytest
```

## 服务器部署建议

- PostgreSQL 使用 Docker Compose 运行
- FastAPI 使用服务器本机 Python 3.11 运行
- 开发/试运行可直接用 `uvicorn`
- 稳定运行建议通过 `systemd` 管理 `uvicorn`
- 日常重启服务不建议默认执行 seed

示例 `systemd` 服务模板：

```ini
[Unit]
Description=AuditPilot FastAPI
After=network.target

[Service]
WorkingDirectory=/opt/AuditPilot-Manufacturing/apps/backend
EnvironmentFile=/opt/AuditPilot-Manufacturing/.env
ExecStart=/opt/AuditPilot-Manufacturing/apps/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## 当前 Demo 企业

- 三一重工（600031.SH）
- 已内置近三年年度指标和四个季度指标
- 内置外部风险事件、规则库、知识片段与文档摘录
