from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class EnterpriseProfile(TimestampMixin, Base):
    __tablename__ = "enterprise_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False)
    industry_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    sub_industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange: Mapped[str] = mapped_column(String(32), default="SSE", nullable=False)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    listed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    portrait: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    financial_indicators: Mapped[list["FinancialIndicator"]] = relationship(back_populates="enterprise")
    external_events: Mapped[list["ExternalEvent"]] = relationship(back_populates="enterprise")
    documents: Mapped[list["DocumentMeta"]] = relationship(back_populates="enterprise")


class FinancialIndicator(TimestampMixin, Base):
    __tablename__ = "financial_indicator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    report_period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    report_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indicator_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="seed")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    enterprise: Mapped["EnterpriseProfile"] = relationship(back_populates="financial_indicators")


class ExternalEvent(TimestampMixin, Base):
    __tablename__ = "external_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    enterprise: Mapped["EnterpriseProfile"] = relationship(back_populates="external_events")


class DocumentMeta(TimestampMixin, Base):
    __tablename__ = "document_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False, default="annual_report")
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="upload")
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    enterprise: Mapped["EnterpriseProfile"] = relationship(back_populates="documents")
    extracts: Mapped[list["DocumentExtractResult"]] = relationship(back_populates="document")


class DocumentExtractResult(TimestampMixin, Base):
    __tablename__ = "document_extract_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document_meta.id"), nullable=False, index=True)
    extract_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    document: Mapped["DocumentMeta"] = relationship(back_populates="extracts")


class BusinessTransaction(TimestampMixin, Base):
    __tablename__ = "business_transaction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    process_name: Mapped[str] = mapped_column(String(128), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AuditRule(TimestampMixin, Base):
    __tablename__ = "audit_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    focus_accounts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    focus_processes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_procedures: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RiskIdentificationResult(TimestampMixin, Base):
    __tablename__ = "risk_identification_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_run.id"), nullable=True, index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("audit_rule.id"), nullable=True, index=True)
    risk_name: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_chain: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    feature_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditRecommendation(TimestampMixin, Base):
    __tablename__ = "audit_recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_run.id"), nullable=True, index=True)
    risk_result_id: Mapped[int | None] = mapped_column(ForeignKey("risk_identification_result.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    focus_accounts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    focus_processes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_procedures: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)


class AuditChatRecord(TimestampMixin, Base):
    __tablename__ = "audit_chat_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    suggested_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class RiskAlertRecord(TimestampMixin, Base):
    __tablename__ = "risk_alert_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_run.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MacroIndicator(TimestampMixin, Base):
    __tablename__ = "macro_indicator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    indicator_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")


class IndustryBenchmark(TimestampMixin, Base):
    __tablename__ = "industry_benchmark"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry_tag: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    report_period: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="mock")


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)


class AnalysisRun(TimestampMixin, Base):
    __tablename__ = "analysis_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[int] = mapped_column(ForeignKey("enterprise_profile.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

