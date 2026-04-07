from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiMessage(BaseModel):
    message: str


class EvidenceItem(BaseModel):
    type: str
    title: str
    content: str
    source: str | None = None
    report_period: str | None = None
    metadata: dict[str, Any] | None = None


class TimelineItem(BaseModel):
    id: int
    title: str
    event_type: str
    severity: str
    event_date: date | None
    summary: str


class PeriodMetric(BaseModel):
    report_period: str
    period_type: str
    indicator_code: str
    indicator_name: str
    value: float
    source: str


class RunSummary(BaseModel):
    run_id: int | None
    status: str
    summary: str | None = None
    created_at: datetime | None = None

