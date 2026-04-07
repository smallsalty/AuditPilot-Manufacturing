from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.dashboard_service import DashboardService


router = APIRouter()


@router.get("/enterprises")
def list_enterprises(db: Session = Depends(get_db)) -> list[dict]:
    enterprises = EnterpriseRepository(db).list_enterprises()
    return [
        {
            "id": enterprise.id,
            "name": enterprise.name,
            "ticker": enterprise.ticker,
            "industry_tag": enterprise.industry_tag,
            "report_year": enterprise.report_year,
        }
        for enterprise in enterprises
    ]


@router.get("/enterprises/{enterprise_id}")
def get_enterprise(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    repo = EnterpriseRepository(db)
    enterprise = repo.get_by_id(enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在")
    return {
        "id": enterprise.id,
        "name": enterprise.name,
        "ticker": enterprise.ticker,
        "report_year": enterprise.report_year,
        "industry_tag": enterprise.industry_tag,
        "sub_industry": enterprise.sub_industry,
        "exchange": enterprise.exchange,
        "province": enterprise.province,
        "city": enterprise.city,
        "listed_date": enterprise.listed_date,
        "employee_count": enterprise.employee_count,
        "description": enterprise.description,
        "portrait": enterprise.portrait,
        "financial_metrics": [
            {
                "report_period": item.report_period,
                "period_type": item.period_type,
                "indicator_code": item.indicator_code,
                "indicator_name": item.indicator_name,
                "value": item.value,
                "source": item.source,
            }
            for item in repo.get_financials(enterprise_id)
        ],
        "external_events": [
            {
                "id": event.id,
                "title": event.title,
                "event_type": event.event_type,
                "severity": event.severity,
                "event_date": event.event_date,
                "summary": event.summary,
            }
            for event in repo.get_external_events(enterprise_id)
        ],
    }


@router.get("/enterprises/{enterprise_id}/dashboard")
def get_dashboard(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return DashboardService().build_dashboard(db, enterprise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

