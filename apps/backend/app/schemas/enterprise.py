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
    text_warning: float = 0.0


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


class FinancialReportMetricSnapshot(BaseModel):
    report_period: str
    revenue: float | None = None
    revenue_growth: float | None = None
    net_profit: float | None = None
    deduct_net_profit: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    profit_cash_content: float | None = None
    ar_turnover: float | None = None
    inventory_turnover: float | None = None
    debt_ratio: float | None = None
    interest_bearing_debt_ratio: float | None = None
    expense_ratio: float | None = None
    ocf: float | None = None
    fixed_assets: float | None = None
    roe: float | None = None
    eps: float | None = None


class FinancialReportRowPayload(BaseModel):
    year: int
    quarter: str
    report_period: str
    revenue: float | None = None
    revenue_growth: float | None = None
    revenue_yoy: float | None = None
    revenue_qoq: float | None = None
    net_profit: float | None = None
    deduct_net_profit: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    profit_cash_content: float | None = None
    ar_turnover: float | None = None
    inventory_turnover: float | None = None
    debt_ratio: float | None = None
    interest_bearing_debt_ratio: float | None = None
    expense_ratio: float | None = None
    ocf: float | None = None
    fixed_assets: float | None = None
    roe: float | None = None
    eps: float | None = None
    source: str


class FinancialReportSummaryItem(BaseModel):
    text: str


class FinancialIndustryComparisonMetric(BaseModel):
    company_value: float | None = None
    industry_mean: float | None = None
    industry_median: float | None = None
    p25: float | None = None
    p75: float | None = None
    gap: float | None = None
    gap_pct: float | None = None
    zscore: float | None = None
    percentile: float | None = None
    available: bool = False
    sample_count: int = 0
    confidence: str | None = None
    source: str | None = None
    unavailable_reason: str | None = None
    distribution_available: bool = False
    metric: str | None = None
    period: str | None = None
    requested_period: str | None = None
    actual_peer_period_range: list[str] = Field(default_factory=list)
    period_aligned: bool = False
    industry_name: str | None = None
    industry_level: str | None = None
    fallback_used: bool = False
    aggregation_method: str | None = None


class FinancialIndustryComparisonPayload(BaseModel):
    industry_code: str
    industry_name: str
    industry_source: str
    latest_year: int | None = None
    reference_industry_name: str | None = None
    industry_level: str | None = None
    fallback_used: bool = False
    original_industry: str | None = None
    cache_state: str | None = None
    cache_updated_at: str | None = None
    revenue_growth: FinancialIndustryComparisonMetric
    gross_margin: FinancialIndustryComparisonMetric
    net_margin: FinancialIndustryComparisonMetric
    revenue: FinancialIndustryComparisonMetric
    ar_turnover: FinancialIndustryComparisonMetric
    inventory_turnover: FinancialIndustryComparisonMetric
    debt_ratio: FinancialIndustryComparisonMetric
    expense_ratio: FinancialIndustryComparisonMetric


class FinancialDataRiskItem(BaseModel):
    rule_code: str
    risk_name: str
    risk_level: str
    risk_score: float
    judgment: str
    evidence: str
    periods: list[str]


class FinancialReportPayload(BaseModel):
    enterprise_id: int
    company_name: str
    ticker: str
    data_source: str
    period_range: dict[str, str | None]
    updated_at: str | None = None
    stale: bool = False
    refresh_error: str | None = None
    latest_period: str
    latest_metrics: FinancialReportMetricSnapshot
    rows: list[FinancialReportRowPayload]
    summaries: list[FinancialReportSummaryItem]
    industry_comparison: FinancialIndustryComparisonPayload
    data_risk_score: float = 0.0
    data_risks: list[FinancialDataRiskItem] = Field(default_factory=list)
