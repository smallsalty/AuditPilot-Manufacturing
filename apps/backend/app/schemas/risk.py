from pydantic import BaseModel

from app.schemas.common import EvidenceItem, RunSummary


class RiskResultPayload(BaseModel):
    id: int
    risk_name: str
    risk_category: str
    risk_level: str
    risk_score: float
    source_type: str
    reasons: list[str]
    evidence_chain: list[EvidenceItem]
    llm_summary: str | None = None
    llm_explanation: str | None = None
    focus_accounts: list[str]
    focus_processes: list[str]
    recommended_procedures: list[str]
    evidence_types: list[str]
    score_details: dict | None = None
    industry_comparison: dict | None = None
    is_baseline_observation: bool = False


class RiskAnalysisRunResponse(BaseModel):
    run: RunSummary
    results: list[RiskResultPayload]


class AuditFocusItem(BaseModel):
    title: str
    items: list[str]


class AuditFocusPayload(BaseModel):
    enterprise_id: int
    focus_accounts: list[str]
    focus_processes: list[str]
    recommended_procedures: list[str]
    evidence_types: list[str]
    recommendations: list[str]
