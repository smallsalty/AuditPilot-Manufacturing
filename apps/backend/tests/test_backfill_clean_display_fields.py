from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta, EnterpriseProfile
from app.models.base import Base
from app.scripts.backfill_clean_display_fields import backfill_clean_display_fields


def test_backfill_clean_display_fields_is_idempotent(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        enterprise = EnterpriseProfile(
            name="Test Enterprise",
            ticker="000001",
            report_year=2024,
            industry_tag="Manufacturing",
            exchange="SSE",
        )
        db.add(enterprise)
        db.flush()

        document = DocumentMeta(
            enterprise_id=enterprise.id,
            document_name="<em>2025年</em>半<em>年度报告</em><em>2025年</em>半<em>年度报告</em><em>摘要</em>",
            document_type="annual_summary",
            file_name="<em>2025年</em>半<em>年度报告</em>.pdf",
            source="cninfo",
            parse_status="parsed",
        )
        db.add(document)
        db.flush()

        extract = DocumentExtractResult(
            document_id=document.id,
            extract_type="document_issue",
            title="<em>2025年</em>半<em>年度报告</em>",
            subject="<em>2025年</em>半<em>年度报告</em>",
            content=json.dumps({"title": "<em>2025年</em>半<em>年度报告</em>", "subject": "<em>2025年</em>半<em>年度报告</em>"}, ensure_ascii=False),
        )
        db.add(extract)
        db.flush()

        feature = DocumentEventFeature(
            enterprise_id=enterprise.id,
            document_id=document.id,
            extract_id=extract.id,
            feature_type="event",
            subject="<em>2025年</em>半<em>年度报告</em>",
            payload={"subject": "<em>2025年</em>半<em>年度报告</em>"},
        )
        db.add(feature)
        db.commit()

    monkeypatch.setattr("app.scripts.backfill_clean_display_fields.SessionLocal", testing_session_local)

    first = backfill_clean_display_fields(enterprise_id=1)
    second = backfill_clean_display_fields(enterprise_id=1)

    assert first["documents_updated"] == 1
    assert first["extracts_updated"] == 1
    assert first["features_updated"] == 1
    assert second == {"documents_updated": 0, "extracts_updated": 0, "features_updated": 0}

    with testing_session_local() as db:
        document = db.get(DocumentMeta, 1)
        extract = db.get(DocumentExtractResult, 1)
        feature = db.get(DocumentEventFeature, 1)

        assert document.document_name
        assert "<em>" not in document.document_name
        assert "<em>" not in document.file_name
        assert "<em>" not in extract.title
        assert "<em>" not in extract.subject
        assert "<em>" not in feature.subject
