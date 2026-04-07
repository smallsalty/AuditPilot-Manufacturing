from pydantic import BaseModel, Field


class FinancialIngestionRequest(BaseModel):
    enterprise_id: int
    provider: str = Field(default="akshare")
    include_quarterly: bool = True
    force_seed_fallback: bool = False


class RiskEventIngestionRequest(BaseModel):
    enterprise_id: int
    provider: str = Field(default="mock")


class MacroIngestionRequest(BaseModel):
    industry_tag: str = Field(default="工程机械")


class IngestionResponse(BaseModel):
    status: str
    provider: str
    inserted: int
    message: str

