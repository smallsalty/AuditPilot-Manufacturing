import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import DocumentEventFeature, DocumentExtractResult, ReviewOverride
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.utils.display_text import clean_document_title


router = APIRouter()


@router.post("/ingestion/documents/upload")
async def upload_document(
    enterprise_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    document = DocumentService().save_upload(
        db,
        enterprise_id=enterprise_id,
        filename=file.filename or "document.pdf",
        file_bytes=await file.read(),
        uploads_dir=settings.uploads_dir,
    )
    return {"id": document.id, "document_name": clean_document_title(document.document_name), "parse_status": document.parse_status}


@router.post("/documents/{document_id}/parse")
def parse_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        document = DocumentService().parse_document(db, document_id)
        return {"id": document.id, "document_name": clean_document_title(document.document_name), "parse_status": document.parse_status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/{document_id}/extracts")
def get_document_extracts(document_id: int, db: Session = Depends(get_db)) -> dict:
    repository = DocumentRepository(db)
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    extracts = repository.list_extracts(document_id)
    features = repository.list_event_features(document_id)
    feature_by_extract = {feature.extract_id: feature for feature in features if feature.extract_id}
    return {"document_id": document_id, "extracts": [_serialize_extract(extract, feature_by_extract.get(extract.id)) for extract in extracts]}


@router.patch("/documents/{document_id}/classification")
def override_document_classification(
    document_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    repository = DocumentRepository(db)
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    classified_type = str(payload.get("classified_type") or "").strip()
    if not classified_type:
        raise HTTPException(status_code=400, detail="classified_type 不能为空。")
    db.add(
        ReviewOverride(
            enterprise_id=document.enterprise_id,
            document_id=document.id,
            scope="classification",
            target_key="document_type",
            override_value={"classified_type": classified_type},
        )
    )
    db.commit()
    document = DocumentService().parse_document(db, document.id)
    return {"document_id": document.id, "classified_type": document.classified_type}


@router.patch("/documents/{document_id}/extracts/{evidence_span_id}/event-type")
def override_extract_event_type(
    document_id: int,
    evidence_span_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    repository = DocumentRepository(db)
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    event_type = str(payload.get("event_type") or "").strip()
    if not event_type:
        raise HTTPException(status_code=400, detail="event_type 不能为空。")
    extract = next((item for item in repository.list_extracts(document_id) if item.evidence_span_id == evidence_span_id), None)
    if extract is None:
        raise HTTPException(status_code=404, detail="抽取项不存在。")
    extract.event_type = event_type
    extract.extract_family = "announcement_event"
    extract.content = json.dumps({**_serialize_extract(extract), "event_type": event_type}, ensure_ascii=False)
    feature = next((item for item in repository.list_event_features(document_id) if item.extract_id == extract.id), None)
    if feature is not None:
        feature.event_type = event_type
    db.add(
        ReviewOverride(
            enterprise_id=document.enterprise_id,
            document_id=document.id,
            scope="event_type",
            target_key=evidence_span_id,
            override_value={"event_type": event_type},
        )
    )
    db.commit()
    return {"document_id": document_id, "evidence_span_id": evidence_span_id, "event_type": event_type}


def _serialize_extract(extract: DocumentExtractResult, feature: DocumentEventFeature | None = None) -> dict:
    payload: dict = {}
    try:
        payload = json.loads(extract.content)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    event_type = feature.event_type if feature and feature.event_type else extract.event_type
    opinion_type = feature.opinion_type if feature and feature.opinion_type else extract.opinion_type
    return {
        "id": extract.id,
        "extract_type": extract.extract_type,
        "extract_version": extract.extract_version,
        "extract_family": extract.extract_family or "general",
        "title": clean_document_title(extract.title),
        "summary": extract.problem_summary or extract.content,
        "problem_summary": extract.problem_summary or extract.content,
        "parameters": extract.parameters or payload.get("parameters") or {},
        "applied_rules": extract.applied_rules or [],
        "evidence_excerpt": extract.evidence_excerpt or extract.content,
        "page_number": extract.page_number,
        "page_start": extract.page_start,
        "page_end": extract.page_end,
        "section_title": extract.section_title,
        "paragraph_hash": extract.paragraph_hash,
        "evidence_span_id": extract.evidence_span_id,
        "keywords": extract.keywords,
        "detail_level": extract.detail_level or "general",
        "financial_topics": payload.get("financial_topics") or [],
        "note_refs": payload.get("note_refs") or [],
        "risk_points": payload.get("risk_points") or [],
        "fact_tags": extract.fact_tags or [],
        "metric_name": extract.metric_name,
        "metric_value": extract.metric_value,
        "metric_unit": extract.metric_unit,
        "compare_target": extract.compare_target,
        "compare_value": extract.compare_value,
        "period": extract.period,
        "fiscal_year": extract.fiscal_year,
        "fiscal_quarter": extract.fiscal_quarter,
        "event_type": event_type,
        "event_direction": feature.direction if feature and feature.direction else extract.direction,
        "event_severity": feature.severity if feature and feature.severity else extract.severity,
        "event_date": feature.event_date.isoformat() if feature and feature.event_date else (extract.event_date.isoformat() if extract.event_date else None),
        "subject": clean_document_title(feature.subject if feature and feature.subject else extract.subject),
        "amount": feature.amount if feature and feature.amount is not None else extract.amount,
        "counterparty": feature.counterparty if feature and feature.counterparty else extract.counterparty,
        "direction": feature.direction if feature and feature.direction else extract.direction,
        "severity": feature.severity if feature and feature.severity else extract.severity,
        "conditions": feature.conditions if feature and feature.conditions else None,
        "opinion_type": opinion_type,
        "defect_level": feature.defect_level if feature and feature.defect_level else extract.defect_level,
        "conclusion": feature.conclusion if feature and feature.conclusion else extract.conclusion,
        "affected_scope": feature.affected_scope if feature and feature.affected_scope else extract.affected_scope,
        "auditor_or_board_source": feature.auditor_or_board_source if feature and feature.auditor_or_board_source else extract.auditor_or_board_source,
        "canonical_risk_key": extract.canonical_risk_key,
    }
