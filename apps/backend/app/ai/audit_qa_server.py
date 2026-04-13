import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient
from app.models import AuditChatRecord, EnterpriseProfile, RiskIdentificationResult
from app.rag.retrieval_service import RetrievalService
from app.services.document_risk_service import DocumentRiskService


logger = logging.getLogger(__name__)


class AuditQAServer:
    def __init__(self, llm_client: LLMClient | None = None, retrieval_service: RetrievalService | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.document_risk_service = DocumentRiskService()

    def answer(self, db: Session, enterprise: EnterpriseProfile, question: str) -> dict:
        risk_rows = (
            db.query(RiskIdentificationResult)
            .filter(RiskIdentificationResult.enterprise_id == enterprise.id)
            .order_by(RiskIdentificationResult.risk_score.desc())
            .limit(5)
            .all()
        )
        document_risks = self.document_risk_service.list_risks(db, enterprise.id)[:5]
        chunks = self.retrieval_service.retrieve(db, question, enterprise.id, top_k=5)

        if not risk_rows and not chunks and not document_risks:
            logger.info("chat blocked enterprise_id=%s no risk rows or chunks", enterprise.id)
            return {
                "answer": "当前企业尚无足够的文档依据或风险结果，请先同步官方数据并执行文档解析。",
                "basis_level": "insufficient_context",
                "citations": [],
                "suggested_actions": ["同步巨潮公告", "上传年报或公告 PDF", "执行文档解析"],
            }

        basis_level = "official_document" if chunks or document_risks else "structured_result"
        context_lines = [f"[风险]{row.risk_name}:{'；'.join(row.reasons)}" for row in risk_rows]
        context_lines.extend(
            [
                f"[文档风险]{row['risk_name']}:{row.get('summary') or '；'.join(row.get('reasons') or [])}"
                for row in document_risks
            ]
        )
        context_lines.extend([f"[知识]{chunk.title}:{chunk.content[:180]}" for chunk in chunks])
        context = "\n".join(context_lines)

        system_prompt = (
            "你是一名审计风险问答助手。请严格基于给定的风险结果和文档依据回答，"
            "优先使用中文给出精炼判断、依据和建议动作。"
        )
        user_prompt = (
            f"企业：{enterprise.name}\n"
            f"问题：{question}\n"
            f"当前依据等级：{basis_level}\n"
            f"上下文：\n{context}\n"
            "请返回 JSON。"
        )

        try:
            result = self.llm_client.chat_completion(system_prompt, user_prompt, json_mode=True)
        except RuntimeError as exc:
            logger.warning("chat failed enterprise_id=%s error=%s", enterprise.id, exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        citations = []
        for item in document_risks[:3]:
            for evidence in (item.get("evidence") or [])[:2]:
                location = []
                if evidence.get("section_title"):
                    location.append(str(evidence.get("section_title")))
                if evidence.get("page_start") or evidence.get("page_end"):
                    location.append(f"页码 {evidence.get('page_start') or '?'}-{evidence.get('page_end') or evidence.get('page_start') or '?'}")
                citations.append(
                    {
                        "title": " | ".join([part for part in [evidence.get("source_label"), *location] if part]) or item["risk_name"],
                        "content": str(evidence.get("snippet") or item.get("summary") or "")[:180],
                        "source_type": "document",
                    }
                )
        if not citations:
            citations = [
                {
                    "title": chunk.title,
                    "content": chunk.content[:180],
                    "source_type": chunk.source_type,
                }
                for chunk in chunks
            ]
        if not citations:
            citations = [
                {
                    "title": item["risk_name"],
                    "content": str(item.get("summary") or "")[:180],
                    "source_type": str(item.get("source_mode") or "document_primary"),
                }
                for item in document_risks[:3]
            ]

        answer = result.get("summary") or result.get("answer") or "系统已基于当前文档依据和风险结果生成回答。"
        suggested_actions = result.get("procedures") or result.get("suggested_actions") or [
            "查看风险清单中的文档证据",
            "优先复核高风险科目与披露依据",
            "补充获取合同、回款和库存等支撑材料",
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
            "chat answered enterprise_id=%s risk_rows=%s document_risks=%s chunks=%s basis_level=%s",
            enterprise.id,
            len(risk_rows),
            len(document_risks),
            len(chunks),
            basis_level,
        )
        return {
            "answer": answer,
            "basis_level": basis_level,
            "citations": citations,
            "suggested_actions": suggested_actions,
        }
