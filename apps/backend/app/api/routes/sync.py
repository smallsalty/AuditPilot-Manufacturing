from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.schemas.sync import CompanySyncRequest
from app.services.audit_sync_service import AuditSyncService
from app.services.document_service import DocumentService


router = APIRouter()


def _process_parse_queue_in_background(company_id: int) -> None:
    with SessionLocal() as db:
        DocumentService().process_parse_queue(db, enterprise_id=company_id)


@router.post("/sync/company")
def sync_company(
    payload: CompanySyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = AuditSyncService().sync_company(
            db=db,
            company_id=payload.company_id,
            sources=payload.sources,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        background_tasks.add_task(_process_parse_queue_in_background, payload.company_id)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
