from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.audit_focus_service import AuditFocusService


router = APIRouter(prefix="/audit-focus")


@router.get("/{enterprise_id}")
def get_audit_focus(enterprise_id: int, db: Session = Depends(get_db)) -> dict:
    return AuditFocusService().build_focus(db, enterprise_id)

