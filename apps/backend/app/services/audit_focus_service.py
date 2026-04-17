from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.document_risk_service import DocumentRiskService


class AuditFocusService:
    SOURCE_LABELS = {
        "financial_anomaly": "来自财务异常",
        "risk_rule": "来自规则命中",
        "announcement_event": "来自公告事件",
        "penalty_event": "来自处罚/问询",
        "uploaded_document": "来自上传文档",
        "management_interview": "来自管理层访谈建议",
        "bank_statement": "来自银行流水/资金证据",
        "tax_analysis": "来自税务分析",
    }

    def build_focus(self, db: Session, enterprise_id: int) -> dict:
        from app.services.risk_analysis_service import RiskAnalysisService

        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        risk_items = DocumentRiskService().list_risks(db, enterprise_id)
        recommendation_items = []
        focus_accounts: list[str] = []
        focus_processes: list[str] = []
        recommended_procedures: list[str] = []
        evidence_types: list[str] = []

        for item in risk_items:
            focus_accounts = self._dedupe(focus_accounts + list(item.get("focus_accounts") or []))
            focus_processes = self._dedupe(focus_processes + list(item.get("focus_processes") or []))
            recommended_procedures = self._dedupe(recommended_procedures + list(item.get("recommended_procedures") or []))
            evidence_types = self._dedupe(evidence_types + list(item.get("evidence_types") or []))

            summary = str(item.get("summary") or item.get("risk_name") or "").strip()
            if not summary:
                continue
            rationale = self._build_rationale(item)
            recommendation_items.append(
                {
                    "text": summary,
                    "sources": [self.SOURCE_LABELS.get(source, source) for source in (item.get("evidence_types") or item.get("sources") or [])],
                    "rationale": rationale,
                }
            )

        focus_cards = []
        for index, item in enumerate(risk_items[:8], start=1):
            focus_cards.append(
                {
                    "id": f"focus-{index}",
                    "title": item["risk_name"],
                    "summary": str(item.get("summary") or item["risk_name"]),
                    "sources": [self.SOURCE_LABELS.get(source, source) for source in (item.get("evidence_types") or [])],
                    "evidence_preview": [
                        str(evidence.get("snippet") or evidence.get("content") or "")[:140]
                        for evidence in (item.get("evidence") or [])[:2]
                    ],
                    "expanded_sections": [
                        {
                            "title": "建议关注",
                            "items": self._dedupe(
                                list(item.get("recommended_procedures") or [])
                                + list(item.get("focus_accounts") or [])
                                + list(item.get("focus_processes") or [])
                            )[:5],
                        }
                    ],
                }
            )

        return {
            "enterprise_id": enterprise_id,
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": recommended_procedures,
            "evidence_types": evidence_types,
            "recommendations": [rec["text"] for rec in recommendation_items],
            "recommendation_items": recommendation_items,
            "items": focus_cards,
        }

    def _build_rationale(self, item: dict) -> str:
        category = str(item.get("risk_category") or "")
        summary = str(item.get("summary") or item.get("risk_name") or "")
        if "公告" in str(item.get("risk_name") or "") or "announcement_" in str(item.get("canonical_risk_key") or ""):
            return f"{summary} 说明公告事件已经影响到审计对披露完整性、管理层判断或持续经营假设的评估。"
        if category in {"财务风险", "document_risk"}:
            return f"{summary} 会直接影响财务报表项目真实性和计量口径，应与公告事件信号合并判断。"
        return f"{summary} 需要结合既有财务异常和公告信号一并评估审计应对范围。"

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        items: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in items:
                items.append(text)
        return items
