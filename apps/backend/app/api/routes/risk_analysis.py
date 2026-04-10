from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.risk_analysis_service import RiskAnalysisService


router = APIRouter(prefix="/risk-analysis")


@router.post("/{enterprise_id}/run")
def run_risk_analysis(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        result = RiskAnalysisService().run(db, enterprise_id)
        return {
            "run": {
                "run_id": result["run_id"],
                "status": result["status"],
                "summary": result["summary"],
            },
            "results": result["results"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{enterprise_id}/results")
def get_risk_results(enterprise_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return RiskAnalysisService().get_results(db, enterprise_id)
