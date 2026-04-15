from typing import Any

from app.ai.llm_client import LLMClient


class RiskExplanationService:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def explain_risk(self, enterprise_name: str, risk_payload: dict[str, Any]) -> dict[str, Any]:
        system_prompt = (
            "你是一名制造业上市公司审计专家。请基于提供的风险命中信息，"
            "输出简洁、专业、可展示给商誉评委的中文 JSON 结果。"
        )
        user_prompt = (
            f"企业：{enterprise_name}\n"
            f"风险名称：{risk_payload['risk_name']}\n"
            f"风险类别：{risk_payload['risk_category']}\n"
            f"命中原因：{'；'.join(risk_payload['reasons'])}\n"
            f"证据链：{risk_payload['evidence_chain']}\n"
            "请返回 summary、explanation、audit_focus、procedures。"
        )
        result = self.llm_client.chat_completion(system_prompt, user_prompt, json_mode=True)
        normalized = self._normalize_result(result)
        return {
            "summary": normalized.get("summary", "系统已识别该风险并建议纳入重点审计关注。"),
            "explanation": normalized.get("explanation", "该风险由财务指标、外部事件和文本证据共同支持。"),
            "audit_focus": normalized.get("audit_focus", []),
            "procedures": normalized.get("procedures", []),
        }

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            if isinstance(result.get("items"), list):
                item = next((entry for entry in result["items"] if isinstance(entry, dict)), None)
                if isinstance(item, dict):
                    return item
            return result
        if isinstance(result, list):
            item = next((entry for entry in result if isinstance(entry, dict)), None)
            if isinstance(item, dict):
                return item
        return {}
