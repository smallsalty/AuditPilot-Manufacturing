from datetime import date

from pydantic import BaseModel

from app.schemas.common import PeriodMetric, TimelineItem


class EnterpriseSummary(BaseModel):
    id: int
    name: str
    ticker: str
    industry_tag: str
    report_year: int


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

