from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import PeriodMetric, TimelineItem


class EnterpriseSummary(BaseModel):
    id: int
    name: str
    ticker: str
    industry_tag: str
    report_year: int


class EnterpriseBootstrapRequest(BaseModel):
    ticker: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def validate_identifier(self):
        if not (self.ticker or self.name):
            raise ValueError("ticker 或 name 至少需要提供一个。")
        return self


class EnterpriseBootstrapResponse(BaseModel):
    enterprise_id: int
    created: bool
    name: str
    ticker: str
    industry_tag: str


class EnterpriseReadinessPayload(BaseModel):
    enterprise_id: int
    profile_ready: bool
    sync_status: str
    official_doc_count: int
    documents_pending_parse: int = 0
    manual_parse_required: bool = False
    official_event_count: int
    risk_analysis_ready: bool
    risk_analysis_reason: str
    risk_analysis_message: str
    last_sync_at: str | None = None
    last_sync_source: str | None = None
    risk_analysis_status: str
    qa_ready: bool


class EnterpriseDetail(BaseModel):
    id: int
    name: str
    ticker: str
    report_year: int
    industry_tag: str
    sub_industry: str | None = None
    exchange: str
    province: str | None = None
    city: str | None = None
    listed_date: date | None = None
    employee_count: int | None = None
    description: str | None = None
    portrait: dict | None = None
    financial_metrics: list[PeriodMetric]
    external_events: list[TimelineItem]


class ScoreBlock(BaseModel):
    total: float
    financial: float
    operational: float
    compliance: float


class RadarPoint(BaseModel):
    name: str
    value: float


class TrendPoint(BaseModel):
    report_period: str
    risk_score: float


class TopRiskCard(BaseModel):
    id: int
    risk_name: str
    risk_level: str
    risk_score: float
    source_type: str


class DashboardPayload(BaseModel):
    enterprise: EnterpriseSummary
    score: ScoreBlock
    radar: list[RadarPoint]
    trend: list[TrendPoint]
    top_risks: list[TopRiskCard]
    analysis_status: str = Field(default="not_started")
    last_run_at: str | None = None
    last_error: str | None = None
