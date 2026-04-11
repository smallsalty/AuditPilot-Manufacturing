# AuditPilot-Manufacturing

制造业上市公司智能风险识别与审计重点提示系统原型。

## 当前阶段

当前第一阶段已经接通两类审计信息源：

- `AkShare`
  - 只负责公司基础资料同步
  - 不负责公告发现
- `巨潮资讯`
  - 负责年报、审计报告、内控审计、处罚/监管类公告
  - 负责 PDF/附件下载
  - 作为权威主源落库

第一阶段链路目标：

1. 指定公司同步基础信息
2. 同步审计报告/年报公告
3. 同步基础监管处罚公告
4. 原始文件落盘，标准字段入库
5. 入库成功后异步解析
6. 前端展示公司审计概览

## 技术栈

- Frontend: Next.js + TypeScript + Tailwind CSS + ECharts
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL
- AI: MiniMax OpenAI-compatible client
- Document parsing: pdfplumber / pypdf

## 关键环境变量

复制 `.env.example` 到 `.env`，至少配置：

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

- 第一阶段不再提供 `TUSHARE_*` 配置。
- 若旧请求仍传 `tushare_fast`，后端会返回明确 `400`。
- `LLM_API_KEY` 为空时，系统自动进入 Mock 模式。

## 一键运行

### Windows 本地开发

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

如需重置 demo 数据：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Seed
```

### Ubuntu 服务器后端

```bash
chmod +x scripts/server-run.sh
bash scripts/server-run.sh
```

如需重置 demo 数据：

```bash
bash scripts/server-run.sh --seed
```

## 第一阶段服务器联调步骤

服务器升级后建议按这个顺序操作：

1. 拉取最新代码
2. 备份 `.env`
3. 执行数据库迁移脚本
4. 重启后端
5. 调用同步接口
6. 打开审计概览页验证
7. 查看文档中心状态

命令示例：

```bash
cd /path/to/AuditPilot-Manufacturing/apps/backend
source .venv/bin/activate
python -m app.scripts.migrate_phase1_audit_sync
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

同步接口示例：

```bash
curl -X POST http://127.0.0.1:8000/api/sync/company \
  -H "Content-Type: application/json" \
  -d '{"company_id":1,"sources":["akshare_fast","cninfo"]}'
```

返回结构示例：

```json
{
  "enterprise_id": 1,
  "sources": ["akshare_fast", "cninfo"],
  "company_profile_updated": true,
  "documents_found": 8,
  "documents_inserted": 5,
  "events_found": 3,
  "events_inserted": 2,
  "parse_queued": 6,
  "warnings": [],
  "errors": []
}
```

## 审计概览接口

- `POST /api/sync/company`
- `GET /api/companies/{id}/audit-profile`
- `GET /api/companies/{id}/timeline`
- `GET /api/companies/{id}/risk-summary`

现有接口继续可用：

- `POST /api/chat/{enterprise_id}`
- `POST /api/risk-analysis/{enterprise_id}/run`

## 文件与解析状态

`document_meta` 统一记录：

- `file_name`
- `file_path`
- `file_url`
- `file_hash`
- `mime_type`
- `file_size`
- `download_status`

同步状态与解析状态建议关注：

- `sync_status`: `pending | fetched | stored | parse_queued | parse_failed`
- `parse_status`: `uploaded | parsing | parsed | failed`

## 验证建议

1. 调 `POST /api/sync/company`
2. 检查 `document_meta` 是否写入年报/审计报告
3. 检查 `external_event` 是否写入处罚/监管类公告
4. 检查文件是否落到 `apps/backend/uploads/synced/<enterprise_id>/`
5. 打开 `/enterprises/{id}` 查看审计概览、时间线、风险摘要
6. 打开文档中心确认文档状态从 `parse_queued` 进入 `parsed` 或稳定状态

## 测试

后端静态检查：

```bash
python -m compileall apps/backend/app
```

前端构建检查：

```bash
npm --prefix apps/frontend run build
```
