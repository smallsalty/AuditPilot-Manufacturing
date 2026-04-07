from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.db import create_all


app = FastAPI(
    title="AuditPilot Manufacturing API",
    version="0.1.0",
    description="制造业上市公司智能风险识别与审计重点提示系统",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    create_all()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
