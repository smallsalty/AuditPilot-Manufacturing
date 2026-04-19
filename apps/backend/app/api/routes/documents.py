import json
import logging
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta, KnowledgeChunk, ReviewOverride
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.utils.display_text import clean_document_title


logger = logging.getLogger(__name__)
router = APIRouter()

LITIGATION_KEYWORDS = ("诉讼", "仲裁", "立案", "原告", "被告", "案号", "裁决", "判决")
PENALTY_KEYWORDS = ("处罚", "问询", "监管", "警示", "立案调查", "责令", "整改", "行政监管")
REPURCHASE_KEYWORDS = ("回购", "购回", "股份回购")
CONVERTIBLE_BOND_KEYWORDS = ("可转债", "转股", "赎回", "下修", "债券")
GUARANTEE_KEYWORDS = ("担保", "保证", "连带责任", "担保方", "被担保")
EXECUTIVE_CHANGE_KEYWORDS = ("董事", "监事", "高管", "辞职", "聘任", "换届", "离任", "任职")
RELATED_PARTY_KEYWORDS = ("关联交易", "关联方", "关联方资金", "资金占用")
AUDIT_OPINION_KEYWORDS = ("保留意见", "否定意见", "无法表示意见", "强调事项", "关键审计事项", "审计意见")
INTERNAL_CONTROL_KEYWORDS = ("内控", "内部控制", "重大缺陷", "重要缺陷", "整改")


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
        return _serialize_document_state(document)
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


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: int, db: Session = Depends(get_db)):
    document = DocumentRepository(db).get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    local_path = _safe_upload_file_path(document.file_path)
    if local_path is not None:
        return FileResponse(
            path=local_path,
            media_type=document.mime_type or "application/octet-stream",
            filename=document.file_name or document.document_name,
        )
    redirect_url = _first_url(document.file_url, document.source_url)
    if redirect_url:
        return RedirectResponse(redirect_url)
    raise HTTPException(status_code=404, detail="原文件不可用。")


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    document = DocumentRepository(db).get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    local_path = _safe_upload_file_path(document.file_path)
    document_name = clean_document_title(document.document_name)

    db.execute(delete(DocumentEventFeature).where(DocumentEventFeature.document_id == document_id))
    db.execute(delete(DocumentExtractResult).where(DocumentExtractResult.document_id == document_id))
    db.execute(delete(ReviewOverride).where(ReviewOverride.document_id == document_id))
    db.execute(
        delete(KnowledgeChunk)
        .where(KnowledgeChunk.source_type == "document")
        .where(KnowledgeChunk.source_id == document_id)
    )
    db.execute(delete(DocumentMeta).where(DocumentMeta.id == document_id))
    db.commit()

    if local_path is not None:
        try:
            local_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("failed to delete document file document_id=%s path=%s error=%s", document_id, local_path, exc)
    return {"document_id": document_id, "document_name": document_name, "deleted": True}


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
    serialized = _serialize_document_state(document)
    return {
        "document_id": document.id,
        "classified_type": serialized.get("classified_type"),
        "classification_source": serialized.get("classification_source"),
        "classification_reason": serialized.get("classification_reason"),
        "analysis_status": serialized.get("analysis_status"),
        "analysis_mode": serialized.get("analysis_mode"),
        "last_error_code": serialized.get("last_error_code"),
        "last_error_message": serialized.get("last_error_message"),
        "llm_diagnostics": serialized.get("llm_diagnostics"),
    }


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


def _safe_upload_file_path(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = settings.uploads_dir / candidate
    try:
        root = settings.uploads_dir.resolve()
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _first_url(*values: str | None) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text.startswith(("http://", "https://")):
            return text
    return None


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _build_extract_text(title: str | None, summary: str | None, evidence_excerpt: str | None) -> str:
    return " ".join(part.strip() for part in (title, summary, evidence_excerpt) if part and str(part).strip())


def _infer_event_type_from_text(text: str) -> str | None:
    if not text:
        return None
    if _contains_any(text, AUDIT_OPINION_KEYWORDS):
        return "audit_opinion_issue"
    if _contains_any(text, INTERNAL_CONTROL_KEYWORDS):
        return "internal_control_issue"
    if _contains_any(text, RELATED_PARTY_KEYWORDS):
        return "related_party_transaction"
    if _contains_any(text, REPURCHASE_KEYWORDS):
        return "share_repurchase"
    if _contains_any(text, CONVERTIBLE_BOND_KEYWORDS):
        return "convertible_bond"
    if _contains_any(text, GUARANTEE_KEYWORDS):
        return "guarantee"
    if _contains_any(text, LITIGATION_KEYWORDS):
        return "litigation"
    if _contains_any(text, PENALTY_KEYWORDS):
        return "penalty_or_inquiry"
    if _contains_any(text, EXECUTIVE_CHANGE_KEYWORDS):
        return "executive_change"
    return None


def _infer_event_type(
    *,
    current_event_type: str | None,
    opinion_type: str | None,
    defect_level: str | None,
    canonical_risk_key: str | None,
    title: str | None,
    summary: str | None,
    evidence_excerpt: str | None,
) -> str | None:
    if current_event_type:
        return current_event_type
    if opinion_type:
        return "audit_opinion_issue"
    if defect_level:
        return "internal_control_issue"

    text = _build_extract_text(title, summary, evidence_excerpt)
    if canonical_risk_key == "governance_instability":
        return "executive_change"
    if canonical_risk_key == "related_party_transaction":
        return "related_party_transaction"
    if canonical_risk_key == "litigation_compliance":
        if _contains_any(text, LITIGATION_KEYWORDS):
            return "litigation"
        if _contains_any(text, PENALTY_KEYWORDS):
            return "penalty_or_inquiry"
    if canonical_risk_key == "financing_pressure":
        if _contains_any(text, REPURCHASE_KEYWORDS):
            return "share_repurchase"
        if _contains_any(text, CONVERTIBLE_BOND_KEYWORDS):
            return "convertible_bond"
        if _contains_any(text, GUARANTEE_KEYWORDS):
            return "guarantee"

    return _infer_event_type_from_text(text)


def _serialize_extract(extract: DocumentExtractResult, feature: DocumentEventFeature | None = None) -> dict:
    payload: dict = {}
    try:
        payload = json.loads(extract.content)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    raw_event_type = feature.event_type if feature and feature.event_type else extract.event_type
    opinion_type = feature.opinion_type if feature and feature.opinion_type else extract.opinion_type
    summary = extract.problem_summary or payload.get("problem_summary") or extract.content
    evidence_excerpt = extract.evidence_excerpt or payload.get("evidence_excerpt") or extract.content
    event_type = _infer_event_type(
        current_event_type=raw_event_type,
        opinion_type=opinion_type,
        defect_level=feature.defect_level if feature and feature.defect_level else extract.defect_level,
        canonical_risk_key=extract.canonical_risk_key,
        title=extract.title,
        summary=summary,
        evidence_excerpt=evidence_excerpt,
    )
    return {
        "id": extract.id,
        "extract_type": extract.extract_type,
        "extract_version": extract.extract_version,
        "extract_family": extract.extract_family or "general",
        "title": clean_document_title(extract.title),
        "summary": summary,
        "problem_summary": summary,
        "parameters": extract.parameters or payload.get("parameters") or {},
        "applied_rules": extract.applied_rules or [],
        "evidence_excerpt": evidence_excerpt,
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


def _serialize_document_state(document) -> dict:
    metadata = dict(document.metadata_json or {})
    analysis_meta = dict(metadata.get("analysis_meta") or {})
    classification_meta = dict(metadata.get("classification_meta") or {})
    cleaning_meta = dict(metadata.get("cleaning_meta") or {})
    last_error = dict(metadata.get("last_error") or {})
    return {
        "id": document.id,
        "document_name": clean_document_title(document.document_name),
        "parse_status": document.parse_status,
        "classified_type": document.classified_type or document.document_type,
        "classification_source": document.classification_source,
        "classification_reason": classification_meta.get("classification_reason"),
        "classification_signals": classification_meta.get("classification_signals") or [],
        "analysis_status": metadata.get("analysis_status"),
        "analysis_mode": analysis_meta.get("analysis_mode"),
        "cleaning_summary": cleaning_meta,
        "last_error_code": last_error.get("code") or last_error.get("error_type"),
        "last_error_message": last_error.get("message"),
        "llm_diagnostics": analysis_meta.get("llm_diagnostics"),
        "financial_section_detected": cleaning_meta.get("financial_section_detected"),
        "financial_section_count": cleaning_meta.get("financial_section_count"),
        "sub_analysis_modes": cleaning_meta.get("sub_analysis_modes") or [],
    }
