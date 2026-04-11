from fastapi import APIRouter

from app.api.routes import audit_focus, chat, companies, documents, enterprises, ingestion, reports, risk_analysis, sync


api_router = APIRouter()
api_router.include_router(enterprises.router, tags=["enterprises"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(ingestion.router, tags=["ingestion"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(risk_analysis.router, tags=["risk-analysis"])
api_router.include_router(audit_focus.router, tags=["audit-focus"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(sync.router, tags=["sync"])
