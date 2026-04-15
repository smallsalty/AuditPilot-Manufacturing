from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.sync import CompanySyncRequest
from app.services.audit_sync_service import AuditSyncService


router = APIRouter()


@router.post("/sync/company")
def sync_company(
    payload: CompanySyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        # Sync only persists official documents/events.
        # Parsing remains an explicit manual action and must not be triggered implicitly here.
        result = AuditSyncService().sync_company(
            db=db,
            company_id=payload.company_id,
            sources=payload.sources,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
