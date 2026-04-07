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

## 启动方式

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
python -m app.scripts.seed_demo
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
2. 运行 `python -m app.scripts.seed_demo` 初始化示例企业与规则。
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
NEXT_PUBLIC_API_BASE_URL=http://your_server_ip:8000
BACKEND_CORS_ORIGINS=http://localhost:3000
```

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
