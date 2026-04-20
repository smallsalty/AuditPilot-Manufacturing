from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository
from app.schemas.enterprise import EnterpriseBootstrapRequest
from app.services.dashboard_service import DashboardService
from app.services.document_service import DocumentService
from app.services.announcement_risk_service import AnnouncementRiskService
from app.services.enterprise_runtime_service import EnterpriseRuntimeService
from app.services.financial_analysis_service import FinancialAnalysisService
from app.services.tax_risk_service import TaxRiskService
from app.utils.display_text import clean_document_title


router = APIRouter()


@router.get("/enterprises")
def list_enterprises(
    q: str | None = Query(default=None, description="按企业名称或股票代码模糊搜索"),
    db: Session = Depends(get_db),
) -> list[dict]:
    enterprises = EnterpriseRepository(db).list_enterprises(query=q, official_only=True)
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


@router.post("/enterprises/bootstrap")
def bootstrap_enterprise(payload: EnterpriseBootstrapRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return EnterpriseRuntimeService().bootstrap(db, ticker=payload.ticker, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
            for item in repo.get_financials(enterprise_id, official_only=True)
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
            for event in repo.get_external_events(enterprise_id, official_only=True)
        ],
    }


@router.get("/enterprises/{enterprise_id}/dashboard")
def get_dashboard(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return DashboardService().build_dashboard(db, enterprise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/enterprises/{enterprise_id}/documents")
def get_enterprise_documents(enterprise_id: int, db: Session = Depends(get_db)) -> list[dict]:
    repo = EnterpriseRepository(db)
    enterprise = repo.get_by_id(enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在")
    documents = repo.get_documents(enterprise_id, official_only=True)
    document_repo = DocumentRepository(db)
    items = []
    for document in documents:
        extracts = document_repo.list_extracts(document.id)
        features = document_repo.list_event_features(document.id)
        metadata = document.metadata_json or {}
        analysis_meta = metadata.get("analysis_meta") or {}
        classification_meta = metadata.get("classification_meta") or {}
        cleaning_meta = metadata.get("cleaning_meta") or {}
        last_error = metadata.get("last_error") or {}
        items.append(
            {
                "id": document.id,
                "document_name": clean_document_title(document.document_name),
                "document_type": document.document_type,
                "classified_type": document.classified_type or document.document_type,
                "classification_source": document.classification_source,
                "classification_reason": classification_meta.get("classification_reason"),
                "classification_signals": classification_meta.get("classification_signals") or [],
                "parse_status": document.parse_status,
                "source": document.source,
                "supports_deep_dive": (document.classified_type or document.document_type) in {"annual_report", "annual_summary", "audit_report", "internal_control_report"},
                "extract_status": "ready" if extracts else ("failed" if document.parse_status == "failed" else "pending"),
                "extract_family_summary": sorted({item.extract_family or "general" for item in extracts}),
                "event_coverage": sorted({item.event_type or item.opinion_type for item in features if item.event_type or item.opinion_type}),
                "latest_extract_version": max([item.extract_version or "" for item in extracts], default=None),
                "analysis_status": metadata.get("analysis_status"),
                "analysis_mode": analysis_meta.get("analysis_mode"),
                "analysis_version": analysis_meta.get("analysis_version"),
                "analyzed_at": analysis_meta.get("analyzed_at"),
                "analysis_groups": [group for group in analysis_meta.get("analysis_groups", []) if group in DocumentService.ANALYSIS_GROUPS],
                "cleaning_summary": cleaning_meta,
                "last_error_code": last_error.get("code") or last_error.get("error_type"),
                "last_error_message": last_error.get("message"),
                "last_error_at": last_error.get("last_error_at"),
                "llm_diagnostics": analysis_meta.get("llm_diagnostics"),
                "financial_section_detected": cleaning_meta.get("financial_section_detected"),
                "financial_section_count": cleaning_meta.get("financial_section_count"),
                "sub_analysis_modes": cleaning_meta.get("sub_analysis_modes") or [],
                "created_at": document.created_at.isoformat() if document.created_at else None,
            }
        )
    return items


@router.get("/enterprises/{enterprise_id}/events")
def get_enterprise_events(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    repo = EnterpriseRepository(db)
    enterprise = repo.get_by_id(enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在")

    risk_payload = AnnouncementRiskService().build_announcement_risks(db, enterprise_id)
    raw_events = []
    for event in repo.get_external_events(enterprise_id, official_only=True):
        payload = event.payload if isinstance(event.payload, dict) else {}
        event_analysis = payload.get("event_analysis") if isinstance(payload, dict) else None
        event_analysis_meta = payload.get("event_analysis_meta") if isinstance(payload, dict) else None
        raw_events.append(
            {
                "id": event.id,
                "title": clean_document_title(event.title),
                "event_type": event.event_type,
                "severity": event.severity,
                "event_date": event.event_date.isoformat() if event.event_date else None,
                "summary": event.summary,
                "source_url": event.source_url,
                "sync_status": event.sync_status,
                "title_matches": payload.get("title_matches") or [],
                "primary_title_match": payload.get("primary_title_match"),
                "event_analysis": event_analysis if isinstance(event_analysis, dict) else None,
                "event_analysis_status": (
                    event_analysis_meta.get("status")
                    if isinstance(event_analysis_meta, dict)
                    else event_analysis.get("analysis_status")
                    if isinstance(event_analysis, dict)
                    else None
                ),
            }
        )

    return {
        "enterprise_id": enterprise_id,
        "risk_summary": {
            "announcement_risks": risk_payload.get("announcement_risks") or [],
            "announcement_risk_score": risk_payload.get("announcement_risk_score") or 0.0,
            "announcement_risk_level": risk_payload.get("announcement_risk_level") or "low",
            "matched_event_count": risk_payload.get("matched_event_count") or 0,
            "high_risk_event_count": risk_payload.get("high_risk_event_count") or 0,
            "category_breakdown": risk_payload.get("category_breakdown") or [],
            "summary": risk_payload.get("announcement_summary") or "",
        },
        "raw_events": raw_events,
    }


@router.get("/enterprises/{enterprise_id}/financial-analysis")
def get_financial_analysis(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return FinancialAnalysisService().build_analysis(db, enterprise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/enterprises/{enterprise_id}/tax-risks")
def get_tax_risks(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return TaxRiskService().build_tax_risks(db, enterprise_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
