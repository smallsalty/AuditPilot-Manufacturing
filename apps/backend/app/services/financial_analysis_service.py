from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient, LLMRequestError
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository


class FinancialAnalysisService:
    SUPPORTED_DOCUMENT_TYPES = {"annual_report", "annual_summary", "audit_report", "internal_control_report"}
    DEFAULT_PROCEDURES = [
        "实施趋势分析并复核异常波动原因",
        "结合附注与披露复核关键财务指标口径",
        "核对经营现金流、收入与利润的匹配关系",
        "对重点科目执行穿行测试和截止测试",
    ]

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def build_analysis(self, db: Session, enterprise_id: int) -> dict[str, Any]:
        enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        repo = EnterpriseRepository(db)
        document_repo = DocumentRepository(db)
        document_items: list[dict[str, Any]] = []
        periods: list[str] = []
        key_metrics: list[dict[str, Any]] = []
        anomalies: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        focus_accounts: list[str] = []

        for document in repo.get_documents(enterprise_id, official_only=True):
            document_type = document.classified_type or document.document_type or "general"
            if document_type not in self.SUPPORTED_DOCUMENT_TYPES:
                continue

            extracts = [
                extract
                for extract in document_repo.list_extracts(document.id)
                if extract.extract_family == "financial_statement"
                and extract.detail_level == "financial_deep_dive"
            ]
            if not extracts:
                continue

            document_metrics: list[dict[str, Any]] = []
            document_anomalies: list[dict[str, Any]] = []
            for extract in extracts:
                period = extract.period or document.report_period_label
                if period and period not in periods:
                    periods.append(period)
                metric_name = extract.metric_name or extract.title
                if metric_name and metric_name not in focus_accounts:
                    focus_accounts.append(metric_name)

                metric_payload = {
                    "document_id": document.id,
                    "document_name": document.document_name,
                    "metric_name": metric_name,
                    "metric_value": extract.metric_value,
                    "metric_unit": extract.metric_unit,
                    "period": period,
                    "fiscal_year": extract.fiscal_year or document.fiscal_year,
                }
                if metric_name:
                    key_metrics.append(metric_payload)
                    document_metrics.append(metric_payload)

                anomaly_payload = {
                    "document_id": document.id,
                    "document_name": document.document_name,
                    "title": extract.title,
                    "summary": extract.problem_summary or extract.evidence_excerpt or extract.title,
                    "canonical_risk_key": extract.canonical_risk_key,
                    "metric_name": extract.metric_name,
                    "metric_value": extract.metric_value,
                    "metric_unit": extract.metric_unit,
                    "period": period,
                    "section_title": extract.section_title,
                    "page_start": extract.page_start,
                    "page_end": extract.page_end,
                }
                anomalies.append(anomaly_payload)
                document_anomalies.append(anomaly_payload)

                evidence.append(
                    {
                        "document_id": document.id,
                        "document_name": document.document_name,
                        "title": extract.title,
                        "snippet": extract.evidence_excerpt or extract.problem_summary or extract.title,
                        "period": period,
                        "section_title": extract.section_title,
                        "page_start": extract.page_start,
                        "page_end": extract.page_end,
                    }
                )

            document_items.append(
                {
                    "document_id": document.id,
                    "document_name": document.document_name,
                    "classified_type": document_type,
                    "period": document.report_period_label,
                    "fiscal_year": document.fiscal_year,
                    "analysis_status": (document.metadata_json or {}).get("analysis_status"),
                    "analysis_mode": ((document.metadata_json or {}).get("analysis_meta") or {}).get("analysis_mode"),
                    "extract_count": len(extracts),
                    "key_metrics": document_metrics,
                    "anomalies": document_anomalies,
                }
            )

        recommended_procedures = self._build_recommended_procedures(key_metrics, anomalies)
        summary = self._build_summary(
            enterprise_name=enterprise.name,
            periods=periods,
            anomalies=anomalies,
            focus_accounts=focus_accounts,
            recommended_procedures=recommended_procedures,
        )
        return {
            "enterprise_id": enterprise_id,
            "summary": summary,
            "documents": document_items,
            "periods": periods,
            "key_metrics": key_metrics[:20],
            "anomalies": anomalies[:20],
            "evidence": evidence[:12],
            "focus_accounts": focus_accounts[:12],
            "recommended_procedures": recommended_procedures,
        }

    def _build_recommended_procedures(
        self,
        key_metrics: list[dict[str, Any]],
        anomalies: list[dict[str, Any]],
    ) -> list[str]:
        procedures = list(self.DEFAULT_PROCEDURES)
        metric_names = {str(item.get("metric_name") or "") for item in key_metrics}
        if "应收账款" in metric_names:
            procedures.append("关注应收账款账龄、回款测试与坏账准备计提依据")
        if "存货" in metric_names:
            procedures.append("复核存货跌价准备、库龄结构与监盘证据")
        if "经营现金流" in metric_names or "净利润" in metric_names:
            procedures.append("对经营现金流与利润背离执行专项复核")
        if any(item.get("canonical_risk_key") == "revenue_recognition" for item in anomalies):
            procedures.append("对收入确认时点与截止测试执行专项复核")
        deduped: list[str] = []
        for item in procedures:
            if item not in deduped:
                deduped.append(item)
        return deduped[:8]

    def _build_summary(
        self,
        *,
        enterprise_name: str,
        periods: list[str],
        anomalies: list[dict[str, Any]],
        focus_accounts: list[str],
        recommended_procedures: list[str],
    ) -> str:
        if not anomalies:
            return "当前尚未形成可展示的财报专项异常，请先完成年报或审计报告解析。"

        if not self.llm_client.config_error:
            try:
                result = self.llm_client.chat_completion(
                    "你是一名财报审阅助手。请基于提供的财报异常摘要，用中文输出一个简洁 JSON 对象，至少包含 summary 字段。",
                    (
                        f"企业：{enterprise_name}\n"
                        f"期间：{', '.join(periods[:4])}\n"
                        f"重点科目：{', '.join(focus_accounts[:8])}\n"
                        f"异常摘要：{anomalies[:6]}\n"
                        f"建议程序：{recommended_procedures[:6]}\n"
                    ),
                    json_mode=True,
                    request_kind="financial_analysis_summary",
                    metadata={
                        "enterprise_id": None,
                        "candidate_count": len(anomalies),
                        "context_variant": "financial_analysis",
                    },
                )
                if isinstance(result, dict) and str(result.get("summary") or "").strip():
                    return str(result["summary"]).strip()
            except LLMRequestError:
                pass

        top_accounts = "、".join(focus_accounts[:3]) if focus_accounts else "关键财务科目"
        top_period = periods[0] if periods else "当前期间"
        return f"{enterprise_name} 在 {top_period} 的财报专项分析中，重点异常集中在 {top_accounts}，建议优先执行趋势复核、附注核对和关键科目细节测试。"
