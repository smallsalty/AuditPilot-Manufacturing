from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.api.routes.enterprises import get_enterprise_documents


def test_get_enterprise_documents_hides_partial_fallback_error_when_extracts_exist(monkeypatch) -> None:
    enterprise = SimpleNamespace(id=1)
    document = SimpleNamespace(
        id=7,
        document_name="2024年年度报告",
        document_type="annual_report",
        classified_type="annual_report",
        parse_status="parsed",
        source="upload",
        metadata_json={
            "analysis_status": "partial_fallback",
            "analysis_meta": {
                "analysis_mode": "hybrid_fallback",
                "analysis_version": "document-extract:v3",
                "analyzed_at": "2026-04-16T08:00:00+00:00",
                "analysis_groups": ["financial_analysis"],
            },
            "last_error": {
                "message": "模型未返回有效的结构化抽取结果。",
                "last_error_at": "2026-04-16T08:00:00+00:00",
            },
        },
        created_at=datetime.fromisoformat("2026-04-16T08:00:00+00:00"),
    )

    monkeypatch.setattr("app.api.routes.enterprises.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr("app.api.routes.enterprises.EnterpriseRepository.get_documents", lambda self, enterprise_id, official_only=True: [document])
    monkeypatch.setattr(
        "app.api.routes.enterprises.DocumentRepository.list_extracts",
        lambda self, document_id: [SimpleNamespace(extract_family="financial_statement", extract_version="document-extract:v3")],
    )
    monkeypatch.setattr("app.api.routes.enterprises.DocumentRepository.list_event_features", lambda self, document_id: [])

    items = get_enterprise_documents(1, db=None)

    assert len(items) == 1
    assert items[0]["analysis_status"] == "partial_fallback"
    assert items[0]["last_error_message"] is None
    assert items[0]["last_error_at"] is None
