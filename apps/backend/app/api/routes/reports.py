from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.report_service import ReportService


router = APIRouter(prefix="/reports")


@router.get("/{enterprise_id}")
def get_report(
    enterprise_id: int,
    format: str = Query(default="json"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return ReportService().build_report(db, enterprise_id, format_type=format)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

