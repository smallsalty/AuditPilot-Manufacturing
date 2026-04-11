from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.audit_overview_service import AuditOverviewService


router = APIRouter()


@router.get("/companies/{company_id}/audit-profile")
def get_audit_profile(company_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return AuditOverviewService().build_profile(db, company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/companies/{company_id}/timeline")
def get_company_timeline(company_id: int, db: Session = Depends(get_db)) -> list[dict]:
    try:
        return AuditOverviewService().build_timeline(db, company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/companies/{company_id}/risk-summary")
def get_risk_summary(company_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return AuditOverviewService().build_risk_summary(db, company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
