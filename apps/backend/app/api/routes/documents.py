from pathlib import Path

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
            {
                "id": extract.id,
                "extract_type": extract.extract_type,
                "title": extract.title,
                "content": extract.content,
                "page_number": extract.page_number,
                "keywords": extract.keywords,
            }
            for extract in extracts
        ],
    }

