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
