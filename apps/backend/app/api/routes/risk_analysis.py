from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import ReviewOverride
from app.repositories.enterprise_repository import EnterpriseRepository
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
        status = 404 if str(exc) == "企业不存在。" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/{enterprise_id}/results")
def get_risk_results(enterprise_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return RiskAnalysisService().get_results(db, enterprise_id)


@router.patch("/{enterprise_id}/overrides/{canonical_risk_key}")
def override_risk_result(
    enterprise_id: int,
    canonical_risk_key: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在。")
    db.add(
        ReviewOverride(
            enterprise_id=enterprise_id,
            scope="risk",
            target_key=canonical_risk_key,
            override_value={
                "ignored": bool(payload.get("ignored", False)),
                "merge_to_key": payload.get("merge_to_key"),
            },
        )
    )
    db.commit()
    return {"enterprise_id": enterprise_id, "canonical_risk_key": canonical_risk_key, "override": payload}
