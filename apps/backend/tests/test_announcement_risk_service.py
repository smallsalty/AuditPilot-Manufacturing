from datetime import date, timedelta
from types import SimpleNamespace

from app.providers.audit.announcement_event_matcher import AnnouncementEventMatcher
from app.services.announcement_risk_service import AnnouncementRiskService


def test_matcher_alias_and_exclude_behavior() -> None:
    matcher = AnnouncementEventMatcher()

    matched = matcher.match_title_categories("关于收到年报问询函的公告")
    excluded = matcher.match_title_categories("股东大会通知")

    assert any(item["category_code"] == "regulatory_litigation" for item in matched)
    assert matched[0]["matched_keywords"] == ["问询函"]
    assert excluded == []


def test_matcher_selects_primary_category_when_multiple_signals_exist() -> None:
    matcher = AnnouncementEventMatcher()

    primary = matcher.select_primary_match("关于控股股东股份冻结及被立案调查的公告")

    assert primary is not None
    assert primary["category_code"] == "regulatory_litigation"
    assert "股权变动、质押冻结与控制权风险" in primary["secondary_categories"]


def test_announcement_risk_service_aggregates_recent_and_repeat_events(monkeypatch) -> None:
    service = AnnouncementRiskService()
    today = date.today()
    events = [
        SimpleNamespace(
            source="cninfo",
            title="关于公司收到行政处罚决定书的公告",
            announcement_date=today - timedelta(days=10),
            event_date=today - timedelta(days=10),
            source_url="https://example.com/a1.pdf",
            source_object_id="a1",
            payload={
                "primary_title_match": {
                    "category_code": "regulatory_litigation",
                    "risk_level": "high",
                    "matched_keywords": ["行政处罚"],
                    "secondary_categories": [],
                },
                "title_matches": [
                    {
                        "category_code": "regulatory_litigation",
                        "category_name": "监管处罚与诉讼仲裁",
                        "matched_keywords": ["行政处罚"],
                        "title": "关于公司收到行政处罚决定书的公告",
                    }
                ],
            },
        ),
        SimpleNamespace(
            source="cninfo",
            title="关于公司被立案调查的公告",
            announcement_date=today - timedelta(days=25),
            event_date=today - timedelta(days=25),
            source_url="https://example.com/a2.pdf",
            source_object_id="a2",
            payload={
                "primary_title_match": {
                    "category_code": "regulatory_litigation",
                    "risk_level": "high",
                    "matched_keywords": ["立案"],
                    "secondary_categories": [],
                },
                "title_matches": [
                    {
                        "category_code": "regulatory_litigation",
                        "category_name": "监管处罚与诉讼仲裁",
                        "matched_keywords": ["立案"],
                        "title": "关于公司被立案调查的公告",
                    }
                ],
            },
        ),
    ]

    monkeypatch.setattr(
        "app.services.announcement_risk_service.EnterpriseRepository.get_external_events",
        lambda self, enterprise_id, official_only=True: events,
    )
    monkeypatch.setattr(
        "app.services.announcement_risk_service.EnterpriseRepository.get_documents",
        lambda self, enterprise_id, official_only=True: [],
    )

    payload = service.build_announcement_risks(db=None, enterprise_id=1)

    assert payload["matched_event_count"] == 2
    assert payload["high_risk_event_count"] == 2
    assert payload["announcement_risk_score"] > 0
    assert "重复发生" in payload["announcement_risks"][0]["explanation"] or "重复发生" in payload["announcement_risks"][1]["explanation"]
