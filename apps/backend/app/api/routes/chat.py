from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.audit_qa_server import AuditQAServer
from app.core.db import get_db
from app.repositories.enterprise_repository import EnterpriseRepository
from app.schemas.chat import ChatRequest


router = APIRouter(prefix="/chat")


@router.post("/{enterprise_id}")
def chat(enterprise_id: int, payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
    if enterprise is None:
        raise HTTPException(status_code=404, detail="企业不存在。")
    return AuditQAServer().answer(db, enterprise, payload.question)
