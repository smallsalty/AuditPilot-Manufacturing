from pathlib import Path
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService


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
    return {"id": document.id, "document_name": document.document_name, "parse_status": document.parse_status}


@router.post("/documents/{document_id}/parse")
def parse_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        document = DocumentService().parse_document(db, document_id)
        return {"id": document.id, "document_name": document.document_name, "parse_status": document.parse_status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/{document_id}/extracts")
def get_document_extracts(document_id: int, db: Session = Depends(get_db)) -> dict:
    repository = DocumentRepository(db)
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    extracts = repository.list_extracts(document_id)
    return {
        "document_id": document_id,
        "extracts": [
            _serialize_extract(extract)
            for extract in extracts
        ],
    }


def _serialize_extract(extract) -> dict:
    try:
        payload = json.loads(extract.content)
        if not isinstance(payload, dict):
            raise ValueError("invalid extract payload")
    except Exception:
        payload = {
            "problem_summary": extract.content,
            "applied_rules": [],
            "evidence_excerpt": extract.content,
            "detail_level": "general",
            "financial_topics": [],
            "note_refs": [],
            "risk_points": [],
        }

    return {
        "id": extract.id,
        "extract_type": extract.extract_type,
        "title": payload.get("title") or extract.title,
        "problem_summary": payload.get("problem_summary") or extract.content,
        "applied_rules": payload.get("applied_rules") or [],
        "evidence_excerpt": payload.get("evidence_excerpt") or extract.content,
        "page_number": payload.get("page_number", extract.page_number),
        "keywords": payload.get("keywords") or extract.keywords,
        "detail_level": payload.get("detail_level") or "general",
        "financial_topics": payload.get("financial_topics") or [],
        "note_refs": payload.get("note_refs") or [],
        "risk_points": payload.get("risk_points") or [],
    }
