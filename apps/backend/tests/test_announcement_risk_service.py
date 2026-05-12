from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.api.routes.enterprises import _display_event_type, _hide_generic_title_event
from app.services import announcement_risk_service as announcement_module
from app.services.announcement_risk_service import AnnouncementRiskService


class DummyEnterpriseRepository:
    events = []
    documents = []

    def __init__(self, _db):
        pass

    def get_external_events(self, _enterprise_id: int, official_only: bool = False):
        return list(self.events)

    def get_documents(self, _enterprise_id: int, official_only: bool = False):
        return list(self.documents)


def make_event(*, event_type: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        source="cninfo",
        event_type=event_type,
        title="2025年度内部控制审计报告",
        announcement_date=date.today(),
        event_date=date.today(),
        source_url="https://example.com/a.pdf",
        source_object_id="event-1",
        payload=payload,
        sync_status="parsed",
    )


def test_generic_title_match_without_primary_category_does_not_count(monkeypatch):
    DummyEnterpriseRepository.events = [
        make_event(
            event_type="announcement_title_match",
            payload={"event_analysis": {"summary": "已分析", "risk_points": ["需要关注内控缺陷"]}},
        )
    ]
    DummyEnterpriseRepository.documents = []
    monkeypatch.setattr(announcement_module, "EnterpriseRepository", DummyEnterpriseRepository)

    payload = AnnouncementRiskService().build_announcement_risks(None, 1)

    assert payload["matched_event_count"] == 0
    assert payload["announcement_risks"] == []


def test_title_match_with_primary_category_counts_as_specific_risk(monkeypatch):
    DummyEnterpriseRepository.events = [
        make_event(
            event_type="announcement_title_match",
            payload={
                "primary_title_match": {
                    "category_code": "accounting_audit",
                    "matched_keywords": ["内部控制审计报告"],
                    "risk_level": "medium",
                },
                "event_analysis": {"summary": "内部控制事项需关注", "risk_points": ["审计意见与内控执行需复核"]},
            },
        )
    ]
    DummyEnterpriseRepository.documents = []
    monkeypatch.setattr(announcement_module, "EnterpriseRepository", DummyEnterpriseRepository)

    payload = AnnouncementRiskService().build_announcement_risks(None, 1)

    assert payload["matched_event_count"] == 1
    assert payload["announcement_risks"][0]["event_category"] == "会计差错与审计意见"


def test_title_match_with_primary_category_without_analysis_does_not_count(monkeypatch):
    DummyEnterpriseRepository.events = [
        make_event(
            event_type="announcement_title_match",
            payload={
                "primary_title_match": {
                    "category_code": "accounting_audit",
                    "matched_keywords": ["内部控制审计报告"],
                    "risk_level": "medium",
                },
            },
        )
    ]
    DummyEnterpriseRepository.documents = []
    monkeypatch.setattr(announcement_module, "EnterpriseRepository", DummyEnterpriseRepository)

    payload = AnnouncementRiskService().build_announcement_risks(None, 1)

    assert payload["matched_event_count"] == 0
    assert payload["announcement_risks"] == []
    assert _hide_generic_title_event(
        "announcement_title_match",
        {"primary_title_match": {"category_code": "accounting_audit"}},
        None,
    ) is True


def test_enterprise_event_helpers_hide_or_relabel_generic_title_match():
    assert _hide_generic_title_event("announcement_title_match", {}, None) is True
    assert _hide_generic_title_event(
        "announcement_title_match",
        {"primary_title_match": {"category_code": "accounting_audit"}},
        {"risk_points": ["需要关注内控缺陷"]},
    ) is False
    assert (
        _display_event_type(
            "announcement_title_match",
            {"primary_title_match": {"category_code": "accounting_audit"}},
        )
        == "accounting_audit"
    )
