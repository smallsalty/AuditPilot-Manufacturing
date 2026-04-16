import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient, LLMRequestError
from app.models import AuditChatRecord, EnterpriseProfile, RiskIdentificationResult
from app.rag.retrieval_service import RetrievalService
from app.services.document_risk_service import DocumentRiskService
from app.utils.display_text import clean_document_title


logger = logging.getLogger(__name__)


class AuditQAServer:
    DEFAULT_SUGGESTED_ACTIONS = [
        "查看风险清单中的文档证据",
        "优先复核高风险科目与披露依据",
        "补充获取合同、回款和库存等支持材料",
    ]
    DEFAULT_FALLBACK_ANSWER = "系统已基于当前文档依据和风险结果生成兜底回答，请优先查看证据链并继续核查高风险事项。"
    CHAT_LLM_TIMEOUT_SECONDS = 18.0
    CHAT_WAIT_TIMEOUT_SECONDS = 18.5

    def __init__(self, llm_client: LLMClient | None = None, retrieval_service: RetrievalService | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.document_risk_service = DocumentRiskService()

    def answer(self, db: Session, enterprise: EnterpriseProfile, question: str) -> dict:
        try:
            risk_rows, document_risks, chunks = self._collect_context(db, enterprise, question)
        except Exception as exc:
            logger.exception("chat context collection failed enterprise_id=%s error=%s", enterprise.id, exc)
            fallback = self._fallback_chat_result()
            return {
                "answer": fallback["answer"],
                "basis_level": "fallback_context",
                "citations": [],
                "suggested_actions": fallback["suggested_actions"],
            }
        if not risk_rows and not chunks and not document_risks:
            logger.info("chat blocked enterprise_id=%s no risk rows or chunks", enterprise.id)
            return {
                "answer": "当前企业尚无足够的文档依据或风险结果，请先同步官方数据并执行文档解析。",
                "basis_level": "insufficient_context",
                "citations": [],
                "suggested_actions": ["同步巨潮公告", "上传年报或公告 PDF", "执行文档解析"],
            }

        basis_level, system_prompt, user_prompt, context_variant = self.build_prompt_payload(
            enterprise=enterprise,
            question=question,
            risk_rows=risk_rows,
            document_risks=document_risks,
            chunks=chunks,
            context_variant="risk_summary",
        )

        result = self._run_chat_completion(
            enterprise_id=enterprise.id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_variant=context_variant,
            candidate_count=len(risk_rows) + len(document_risks) + len(chunks),
        )

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
                        "title": " | ".join([part for part in [clean_document_title(evidence.get("source_label")), *location] if part]) or item["risk_name"],
                        "content": str(evidence.get("snippet") or item.get("summary") or "")[:180],
                        "source_type": "document",
                    }
                )
        if not citations:
            citations = [
                {
                    "title": clean_document_title(chunk.title),
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

        normalized_result = self._normalize_chat_result(result)
        answer = normalized_result["answer"]
        suggested_actions = normalized_result["suggested_actions"]

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
            "chat answered enterprise_id=%s risk_rows=%s document_risks=%s chunks=%s basis_level=%s context_variant=%s payload_mode=%s parsed_ok=%s",
            enterprise.id,
            len(risk_rows),
            len(document_risks),
            len(chunks),
            basis_level,
            context_variant,
            normalized_result["payload_mode"],
            normalized_result["parsed_ok"],
        )
        return {
            "answer": answer,
            "basis_level": basis_level,
            "citations": citations,
            "suggested_actions": suggested_actions,
        }

    def _run_chat_completion(
        self,
        *,
        enterprise_id: int,
        system_prompt: str,
        user_prompt: str,
        context_variant: str,
        candidate_count: int,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audit-chat-llm")
        future = executor.submit(
            self.llm_client.chat_completion,
            system_prompt,
            user_prompt,
            json_mode=False,
            timeout=self.CHAT_LLM_TIMEOUT_SECONDS,
            request_kind="chat",
            metadata={
                "enterprise_id": enterprise_id,
                "candidate_count": candidate_count,
                "context_variant": context_variant,
                "llm_input_chars": len(user_prompt),
            },
            max_attempts=2,
            max_tokens=512,
            strict_json_instruction=False,
        )
        try:
            return future.result(timeout=self.CHAT_WAIT_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            logger.warning("chat llm timeout fallback enterprise_id=%s", enterprise_id)
            future.cancel()
            return None
        except (RuntimeError, LLMRequestError) as exc:
            logger.warning("chat failed fallback enterprise_id=%s error_type=%s status_code=%s", enterprise_id, getattr(exc, "error_type", None), getattr(exc, "status_code", None))
            return None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _normalize_chat_result(self, result: object) -> dict[str, Any]:
        payload = self._select_chat_payload(result)
        if payload is None:
            return self._fallback_chat_result()

        answer = self._clean_answer_text(
            payload.get("summary")
            or payload.get("answer")
            or payload.get("raw")
            or payload.get("_text")
        )
        if not answer:
            answer = self.DEFAULT_FALLBACK_ANSWER

        suggested_actions = self._normalize_suggested_actions(
            payload.get("procedures") or payload.get("suggested_actions")
        )
        if not suggested_actions:
            suggested_actions = list(self.DEFAULT_SUGGESTED_ACTIONS)

        return {
            "answer": answer,
            "suggested_actions": suggested_actions,
            "parsed_ok": bool(payload.get("parsed_ok", False)),
            "payload_mode": str(payload.get("payload_mode") or "fallback"),
        }

    def _select_chat_payload(self, result: object) -> dict[str, Any] | None:
        if isinstance(result, dict):
            if isinstance(result.get("items"), list):
                item = self._pick_best_chat_item(result["items"])
                if item is not None:
                    item.setdefault("parsed_ok", bool(result.get("parsed_ok", False)))
                    item.setdefault("payload_mode", "list_item")
                    return item
            payload = dict(result)
            payload.setdefault("parsed_ok", bool(payload.get("parsed_ok", False)))
            payload.setdefault("payload_mode", str(payload.get("payload_mode") or "dict"))
            return payload
        if isinstance(result, list):
            return self._pick_best_chat_item(result)
        if isinstance(result, str):
            return {"_text": result, "parsed_ok": False, "payload_mode": "raw_text"}
        return None

    def _pick_best_chat_item(self, items: list[object]) -> dict[str, Any] | None:
        dict_items = [dict(item) for item in items if isinstance(item, dict)]
        if not dict_items:
            return None
        for item in dict_items:
            if item.get("summary") or item.get("answer"):
                item.setdefault("parsed_ok", True)
                item.setdefault("payload_mode", "list_item")
                return item
        for item in dict_items:
            if item.get("procedures") or item.get("suggested_actions"):
                item.setdefault("parsed_ok", True)
                item.setdefault("payload_mode", "list_item")
                return item
        first = dict_items[0]
        first.setdefault("parsed_ok", True)
        first.setdefault("payload_mode", "list_item")
        return first

    def _clean_answer_text(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = " ".join(text.split())
        if len(text) > 320:
            text = text[:320].rstrip("，；、 ") + "。"
        return text

    def _normalize_suggested_actions(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        actions: list[str] = []
        for item in value:
            text = self._clean_answer_text(item)
            if text and text not in actions:
                actions.append(text)
        return actions[:3]

    def _fallback_chat_result(self) -> dict[str, Any]:
        return {
            "answer": self.DEFAULT_FALLBACK_ANSWER,
            "suggested_actions": list(self.DEFAULT_SUGGESTED_ACTIONS),
            "parsed_ok": False,
            "payload_mode": "fallback",
        }

    def _collect_context(self, db: Session, enterprise: EnterpriseProfile, question: str):
        risk_rows = (
            db.query(RiskIdentificationResult)
            .filter(RiskIdentificationResult.enterprise_id == enterprise.id)
            .order_by(RiskIdentificationResult.risk_score.desc())
            .limit(3)
            .all()
        )
        document_risks = self.document_risk_service.list_risks(db, enterprise.id)[:3]
        chunks = [] if document_risks else self.retrieval_service.retrieve(db, question, enterprise.id, top_k=2)
        return risk_rows, document_risks, chunks

    def build_prompt_payload(
        self,
        *,
        enterprise: EnterpriseProfile,
        question: str,
        risk_rows: list[RiskIdentificationResult],
        document_risks: list[dict],
        chunks: list,
        context_variant: str = "full",
    ) -> tuple[str, str, str, str]:
        basis_level = "official_document" if chunks or document_risks else "structured_result"
        context_lines = []
        if context_variant == "risk_summary":
            for row in risk_rows[:3]:
                reasons = "锛?".join((row.reasons or [])[:2])
                context_lines.append(f"[risk]{row.risk_name}: score={row.risk_score}; reasons={reasons}")
            for row in document_risks[:3]:
                evidence = ""
                first_evidence = next(iter(row.get("evidence") or []), None)
                if isinstance(first_evidence, dict):
                    evidence = str(first_evidence.get("snippet") or "")[:120]
                summary = str(row.get("summary") or "锛?".join(row.get("reasons") or []))[:160]
                context_lines.append(
                    f"[document_risk]{row.get('risk_name')}: level={row.get('risk_level')}; "
                    f"summary={summary}; evidence={evidence}"
                )
            for chunk in chunks[:2]:
                context_lines.append(f"[evidence]{clean_document_title(chunk.title)}:{chunk.content[:100]}")
        if context_variant in {"full", "risk_rows"}:
            context_lines.extend([f"[风险]{row.risk_name}:{'；'.join(row.reasons)}" for row in risk_rows])
        if context_variant in {"full", "document_risks"}:
            context_lines.extend(
                [
                    f"[文档风险]{row['risk_name']}:{row.get('summary') or '；'.join(row.get('reasons') or [])}"
                    for row in document_risks
                ]
            )
        if context_variant in {"full", "chunks"}:
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
            "请直接输出中文回答，概括判断、核心依据和下一步关注点，不要返回 JSON、代码块或额外格式说明。"
        )
        return basis_level, system_prompt, user_prompt, context_variant
