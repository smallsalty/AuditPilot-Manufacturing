import logging

from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient
from app.models import AuditChatRecord, EnterpriseProfile, RiskIdentificationResult
from app.rag.retrieval_service import RetrievalService


logger = logging.getLogger(__name__)


class AuditQAServer:
    def __init__(self, llm_client: LLMClient | None = None, retrieval_service: RetrievalService | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.retrieval_service = retrieval_service or RetrievalService()

    def answer(self, db: Session, enterprise: EnterpriseProfile, question: str) -> dict:
        risk_rows = (
            db.query(RiskIdentificationResult)
            .filter(RiskIdentificationResult.enterprise_id == enterprise.id)
            .order_by(RiskIdentificationResult.risk_score.desc())
            .limit(5)
            .all()
        )
        chunks = self.retrieval_service.retrieve(db, question, enterprise.id, top_k=5)

        if not risk_rows and not chunks:
            logger.info("chat blocked enterprise_id=%s no risk rows or chunks", enterprise.id)
            return {
                "answer": "当前企业尚无足够的风险结果或文档依据，请先同步官方数据并运行风险分析。",
                "basis_level": "insufficient_context",
                "citations": [],
                "suggested_actions": ["同步巨潮公告", "上传年报或公告 PDF", "运行风险分析"],
            }

        basis_level = "official_document" if chunks else "structured_result"
        context_lines = [f"[风险]{row.risk_name}:{'；'.join(row.reasons)}" for row in risk_rows]
        context_lines.extend([f"[知识]{chunk.title}:{chunk.content[:180]}" for chunk in chunks])
        context = "\n".join(context_lines)

        system_prompt = (
            "你是一名审计风险问答助手。请严格基于给定的风险结果和文档依据回答，"
            "使用中文，优先给出可执行的审计建议，并保持结构化。"
        )
        user_prompt = (
            f"企业：{enterprise.name}\n"
            f"问题：{question}\n"
            f"当前依据等级：{basis_level}\n"
            f"上下文：\n{context}\n"
            "请返回 JSON。"
        )
        result = self.llm_client.chat_completion(system_prompt, user_prompt, json_mode=True)

        citations = [
            {
                "title": chunk.title,
                "content": chunk.content[:180],
                "source_type": chunk.source_type,
            }
            for chunk in chunks
        ]
        answer = result.get("summary") or result.get("answer") or "系统已根据当前风险与文档依据生成回答。"
        suggested_actions = result.get("procedures") or [
            "查看风险清单中的证据链",
            "优先执行高风险科目的实质性程序",
            "补充获取合同、回款和库存佐证材料",
        ]

        db.add(
            AuditChatRecord(
                enterprise_id=enterprise.id,
                question=question,
                answer=answer,
                citations=citations,
                suggested_actions=suggested_actions,
            )
        )
        db.commit()
        logger.info(
            "chat answered enterprise_id=%s risk_rows=%s chunks=%s basis_level=%s",
            enterprise.id,
            len(risk_rows),
            len(chunks),
            basis_level,
        )
        return {
            "answer": answer,
            "basis_level": basis_level,
            "citations": citations,
            "suggested_actions": suggested_actions,
        }
