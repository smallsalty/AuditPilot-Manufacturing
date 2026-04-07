from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient
from app.models import AuditChatRecord, EnterpriseProfile, RiskIdentificationResult
from app.rag.retrieval_service import RetrievalService


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
        context = "\n".join(
            [f"[风险]{row.risk_name}:{';'.join(row.reasons)}" for row in risk_rows]
            + [f"[知识]{chunk.title}:{chunk.content[:180]}" for chunk in chunks]
        )
        system_prompt = "你是一名审计问答助手。请根据风险识别结果和知识片段，用中文回答，并给出建议操作。"
        user_prompt = f"企业：{enterprise.name}\n问题：{question}\n上下文：\n{context}\n请返回 JSON。"
        result = self.llm_client.chat_completion(system_prompt, user_prompt, json_mode=True)
        citations = [
            {
                "title": chunk.title,
                "content": chunk.content[:180],
                "source_type": chunk.source_type,
            }
            for chunk in chunks
        ]
        answer = result.get("summary") or result.get("answer") or "系统已根据当前风险和文档依据生成回答。"
        suggested_actions = result.get("procedures") or [
            "查看风险清单页中的证据链",
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
        return {
            "answer": answer,
            "citations": citations,
            "suggested_actions": suggested_actions,
        }
