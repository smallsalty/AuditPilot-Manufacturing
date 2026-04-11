from datetime import date

from pydantic import BaseModel, Field


class CompanySyncRequest(BaseModel):
    company_id: int
    sources: list[str] = Field(default_factory=lambda: ["tushare_fast", "cninfo"])
    date_from: date | None = None
    date_to: date | None = None
