# AuditPilot-Manufacturing

制造业上市公司审计风险识别与审计重点提示系统。

## 当前运行态

当前正式运行态只使用以下数据来源：

- `AkShare`
  - 仅负责企业主数据同步
- `巨潮资讯`
  - 负责公告、年报、审计报告、内控审计报告、处罚/监管类公告
- `upload`
  - 用户上传的 PDF / 文本文件

以下内容仅保留为开发辅助，不属于正式运行态：

- `seed`
- `mock`
- 年报节选演示数据

## 技术栈

- Frontend: Next.js + TypeScript + Tailwind CSS + ECharts
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL
- AI: MiniMax OpenAI-compatible client
- Document parsing: pdfplumber / pypdf

## 关键环境变量

复制 `.env.example` 为 `.env`，至少配置：

- `DATABASE_URL`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `AKSHARE_ENABLE`
- `CNINFO_ENABLE`
- `CNINFO_QUERY_URL`
- `CNINFO_STATIC_BASE_URL`
- `SYNC_LOOKBACK_DAYS`
- `NEXT_PUBLIC_API_BASE_URL`

说明：

- 当前不再提供 `TUSHARE_*` 作为正式运行配置。
- 若 `LLM_API_KEY` 为空，系统会自动进入 Mock 模式，但这仅用于大模型兜底，不改变官方数据运行态口径。

## 本地前端 / 云端后端联调

### 本地前端

```powershell
cd apps/frontend
npm run dev
```

### 云端后端

后端按服务器本机 Python 3.11 运行，数据库使用服务器本机 PostgreSQL。

## 第一阶段审计同步能力

当前已接通：

1. 企业主数据同步
2. 巨潮公告同步
3. 年报 / 审计报告 / 内控审计报告入库
4. 基础处罚 / 监管类公告入库
5. 文档原始文件落盘与标准字段入库
6. 入库成功后异步触发解析
7. 企业审计概览展示

## 关键接口

### 企业与状态

- `GET /api/enterprises`
- `POST /api/enterprises/bootstrap`
- `GET /api/companies/{id}/readiness`

### 审计概览

- `POST /api/sync/company`
- `GET /api/companies/{id}/audit-profile`
- `GET /api/companies/{id}/timeline`
- `GET /api/companies/{id}/risk-summary`

### 风险分析与问答

- `POST /api/risk-analysis/{enterprise_id}/run`
- `POST /api/chat/{enterprise_id}`

## 同步摘要返回结构

`POST /api/sync/company` 返回：

```json
{
  "enterprise_id": 1,
  "sources": ["akshare_fast", "cninfo"],
  "company_profile_updated": true,
  "announcements_fetched": 8,
  "documents_found": 5,
  "documents_inserted": 5,
  "events_found": 1,
  "events_inserted": 1,
  "parse_queued": 5,
  "warnings": [],
  "errors": []
}
```

## 页面状态约定

正式页面统一覆盖以下状态：

- 无企业
- 未同步
- 同步中
- 同步失败
- 无官方文档
- 已分析
- 无证据链

页面不直接展示原始异常对象，也不展示 `seed/mock` 运行态提示。

## 验证建议

1. 调用 `POST /api/enterprises/bootstrap`
2. 调用 `POST /api/sync/company`
3. 打开 `/enterprises/{id}` 查看审计概览、时间线、风险摘要
4. 运行 `POST /api/risk-analysis/{enterprise_id}/run`
5. 打开风险清单、审计重点、问答页验证上下文一致性

## 静态检查

后端：

```bash
python -m compileall apps/backend/app
```

前端：

```bash
cd apps/frontend
npx tsc --noEmit --incremental false
```
