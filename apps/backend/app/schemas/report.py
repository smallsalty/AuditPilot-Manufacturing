from pydantic import BaseModel

from app.schemas.enterprise import EnterpriseSummary
from app.schemas.risk import RiskResultPayload


class ReportPayload(BaseModel):
    enterprise: EnterpriseSummary
    overview: str
    risk_profile: dict
    top_risks: list[RiskResultPayload]
    audit_focus: dict
    basis: list[str]
    markdown: str | None = None

