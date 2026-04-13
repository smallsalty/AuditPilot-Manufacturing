from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.base import Base


engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_phase1_sync_columns()
    ensure_phase2_document_columns()


def ensure_phase1_sync_columns() -> None:
    table_columns: dict[str, dict[str, str]] = {
        "enterprise_profile": {
            "source_url": "VARCHAR(512)",
            "source_priority": "INTEGER NOT NULL DEFAULT 0",
            "sync_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "parser_version": "VARCHAR(64)",
            "ingestion_time": "TIMESTAMP WITH TIME ZONE",
            "is_official_source": "BOOLEAN NOT NULL DEFAULT FALSE",
            "source_object_id": "VARCHAR(128)",
            "credit_code": "VARCHAR(64)",
            "company_name_aliases": "JSON",
            "latest_sync_at": "TIMESTAMP WITH TIME ZONE",
        },
        "document_meta": {
            "source_url": "VARCHAR(512)",
            "source_priority": "INTEGER NOT NULL DEFAULT 0",
            "sync_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "parser_version": "VARCHAR(64)",
            "ingestion_time": "TIMESTAMP WITH TIME ZONE",
            "is_official_source": "BOOLEAN NOT NULL DEFAULT FALSE",
            "source_object_id": "VARCHAR(128)",
            "announcement_date": "DATE",
            "report_period_label": "VARCHAR(32)",
            "fiscal_year": "INTEGER",
            "file_name": "VARCHAR(255)",
            "file_url": "VARCHAR(512)",
            "file_hash": "VARCHAR(128)",
            "mime_type": "VARCHAR(128)",
            "file_size": "INTEGER",
            "download_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "content_hash": "VARCHAR(128)",
            "raw_payload": "JSON",
        },
        "external_event": {
            "source_url": "VARCHAR(512)",
            "source_priority": "INTEGER NOT NULL DEFAULT 0",
            "sync_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
            "parser_version": "VARCHAR(64)",
            "ingestion_time": "TIMESTAMP WITH TIME ZONE",
            "is_official_source": "BOOLEAN NOT NULL DEFAULT FALSE",
            "source_object_id": "VARCHAR(128)",
            "announcement_date": "DATE",
            "content_hash": "VARCHAR(128)",
            "raw_payload": "JSON",
            "regulator": "VARCHAR(128)",
        },
    }
    indexes = [
        ("enterprise_profile", "ix_enterprise_profile_source_object_id", "(source_object_id)"),
        ("document_meta", "ix_document_meta_source_object_id", "(source_object_id)"),
        ("document_meta", "ix_document_meta_announcement_date", "(announcement_date)"),
        ("external_event", "ix_external_event_source_object_id", "(source_object_id)"),
        ("external_event", "ix_external_event_announcement_date", "(announcement_date)"),
    ]

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in table_columns.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
        for table_name, index_name, index_expression in indexes:
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {index_expression}"))


def ensure_phase2_document_columns() -> None:
    table_columns: dict[str, dict[str, str]] = {
        "document_meta": {
            "classified_type": "VARCHAR(64)",
            "classification_version": "VARCHAR(64)",
            "classification_source": "VARCHAR(32)",
        },
        "document_extract_result": {
            "extract_version": "VARCHAR(64)",
            "is_current": "BOOLEAN NOT NULL DEFAULT TRUE",
            "extract_family": "VARCHAR(64)",
            "problem_summary": "TEXT",
            "applied_rules": "JSON",
            "evidence_excerpt": "TEXT",
            "detail_level": "VARCHAR(32)",
            "fact_tags": "JSON",
            "page_start": "INTEGER",
            "page_end": "INTEGER",
            "section_title": "VARCHAR(255)",
            "paragraph_hash": "VARCHAR(64)",
            "evidence_span_id": "VARCHAR(128)",
            "metric_name": "VARCHAR(128)",
            "metric_value": "DOUBLE PRECISION",
            "metric_unit": "VARCHAR(32)",
            "compare_target": "VARCHAR(128)",
            "compare_value": "DOUBLE PRECISION",
            "period": "VARCHAR(32)",
            "fiscal_year": "INTEGER",
            "fiscal_quarter": "INTEGER",
            "event_type": "VARCHAR(64)",
            "event_date": "DATE",
            "subject": "VARCHAR(255)",
            "amount": "DOUBLE PRECISION",
            "counterparty": "VARCHAR(255)",
            "direction": "VARCHAR(32)",
            "severity": "VARCHAR(32)",
            "opinion_type": "VARCHAR(64)",
            "defect_level": "VARCHAR(64)",
            "conclusion": "TEXT",
            "affected_scope": "TEXT",
            "auditor_or_board_source": "VARCHAR(255)",
            "canonical_risk_key": "VARCHAR(64)",
        },
        "knowledge_chunk": {
            "source_version": "VARCHAR(64)",
            "is_current": "BOOLEAN NOT NULL DEFAULT TRUE",
        },
        "risk_identification_result": {
            "rule_code": "VARCHAR(64)",
        },
    }
    indexes = [
        ("document_extract_result", "ix_document_extract_result_extract_version", "(extract_version)"),
        ("document_extract_result", "ix_document_extract_result_is_current", "(is_current)"),
        ("document_extract_result", "ix_document_extract_result_paragraph_hash", "(paragraph_hash)"),
        ("document_extract_result", "ix_document_extract_result_evidence_span_id", "(evidence_span_id)"),
        ("document_extract_result", "ix_document_extract_result_canonical_risk_key", "(canonical_risk_key)"),
        ("knowledge_chunk", "ix_knowledge_chunk_source_version", "(source_version)"),
        ("knowledge_chunk", "ix_knowledge_chunk_is_current", "(is_current)"),
        ("risk_identification_result", "ix_risk_identification_result_rule_code", "(rule_code)"),
    ]

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in table_columns.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
        for table_name, index_name, index_expression in indexes:
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} {index_expression}"))
