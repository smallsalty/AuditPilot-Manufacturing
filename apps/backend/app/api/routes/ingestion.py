from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.enterprise_repository import EnterpriseRepository
from app.schemas.ingestion import FinancialIngestionRequest, MacroIngestionRequest, RiskEventIngestionRequest
from app.services.ingestion_service import IngestionService


router = APIRouter(prefix="/ingestion")


@router.post("/financial")
def ingest_financial(payload: FinancialIngestionRequest, db: Session = Depends(get_db)) -> dict:
    enterprise = EnterpriseRepository(db).get_by_id(payload.enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在")
    if payload.provider == "mock" or payload.force_seed_fallback:
        raise HTTPException(status_code=400, detail="运行态已禁用 mock/seed 财务数据，请使用 AkShare。")
    try:
        inserted, provider = IngestionService().ingest_financials(
            db,
            enterprise,
            provider_name=payload.provider,
            include_quarterly=payload.include_quarterly,
            force_seed_fallback=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "provider": provider, "inserted": inserted, "message": "财务数据导入完成"}


@router.post("/risk-events")
def ingest_risk_events(payload: RiskEventIngestionRequest, db: Session = Depends(get_db)) -> dict:
    raise HTTPException(status_code=400, detail="运行态已禁用 mock 风险事件导入，请改用官方同步链路。")


@router.post("/macro")
def ingest_macro(payload: MacroIngestionRequest, db: Session = Depends(get_db)) -> dict:
    raise HTTPException(status_code=400, detail="运行态已禁用 mock 宏观 / 行业导入。")
