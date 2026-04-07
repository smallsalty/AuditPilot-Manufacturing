# AuditPilot Manufacturing Architecture

## Backend

- `api/`: REST 路由层
- `core/`: 配置与数据库连接
- `models/`: SQLAlchemy 模型
- `providers/`: 财务、风险、文档 provider 适配层
- `services/`: 数据接入、特征工程、文档解析、风险分析、报告输出
- `rule_engine/`: 结构化规则计算器
- `ai/`: 通用 OpenAI-compatible LLM 客户端、MiniMax 接入、风险解释与问答
- `rag/`: 轻量检索服务

## Frontend

- Dashboard：综合评分、雷达图、趋势图、Top 风险
- 企业详情页：企业画像、财务指标、外部事件
- 风险清单页：运行分析、查看证据链
- 审计重点页：重点科目、流程、程序、证据
- 文档中心：上传、解析、抽取
- AI 问答页：追问风险原因与审计程序建议

## Data Flow

1. 结构化数据通过 provider 进入 `financial_indicator`、`external_event`
2. 文档上传解析后进入 `document_meta`、`document_extract_result`
3. 特征工程将原始指标转换为风险可判定特征
4. 规则引擎和异常检测共同产出 `risk_identification_result`
5. AI 解释服务生成摘要和建议
6. RAG 从规则、文档、程序模板中检索依据，支持问答

## Runtime

- PostgreSQL + pgvector：Docker Compose 运行
- FastAPI：服务器本机 Python 3.11 运行
- Frontend：本地开发环境或独立前端部署
