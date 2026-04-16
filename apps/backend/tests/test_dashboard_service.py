from types import SimpleNamespace

from app.services.dashboard_service import DashboardService


class _FakeDB:
    pass


def test_dashboard_uses_final_risk_items_for_scores_and_top_risks(monkeypatch) -> None:
    enterprise = SimpleNamespace(id=1, name="三一重工", ticker="600031.SH", industry_tag="制造业", report_year=2026)
    final_risks = [
        {
            "id": 101,
            "risk_name": "应收账款回收与收入真实性风险",
            "canonical_risk_key": "receivable_recoverability",
            "risk_category": "document_risk",
            "risk_level": "HIGH",
            "risk_score": 94,
            "source_type": "document_rule",
        },
        {
            "id": 102,
            "risk_name": "诉讼处罚与合规风险",
            "canonical_risk_key": "litigation_compliance",
            "risk_category": "document_risk",
            "risk_level": "MEDIUM",
            "risk_score": 70,
            "source_type": "document_rule",
        },
    ]

    monkeypatch.setattr("app.services.dashboard_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr(
        "app.services.dashboard_service.RiskAnalysisService.get_analysis_state",
        lambda self, db, enterprise_id: {"analysis_status": "completed", "last_run_at": "2026-04-16T08:01:03+00:00", "last_error": None},
    )
    monkeypatch.setattr("app.services.dashboard_service.DocumentRiskService.list_risks", lambda self, db, enterprise_id: final_risks)

    payload = DashboardService().build_dashboard(_FakeDB(), enterprise_id=1)

    assert payload["score"] == {
        "total": 54.7,
        "financial": 94.0,
        "operational": 0.0,
        "compliance": 70.0,
    }
    assert payload["top_risks"] == [
        {
            "id": 101,
            "risk_name": "应收账款回收与收入真实性风险",
            "risk_level": "HIGH",
            "risk_score": 94.0,
            "source_type": "document_rule",
        },
        {
            "id": 102,
            "risk_name": "诉讼处罚与合规风险",
            "risk_level": "MEDIUM",
            "risk_score": 70.0,
            "source_type": "document_rule",
        },
    ]


def test_dashboard_filters_out_baseline_only_results(monkeypatch) -> None:
    enterprise = SimpleNamespace(id=2, name="徐工机械", ticker="000425.SZ", industry_tag="制造业", report_year=2026)
    baseline_only = [
        {
            "id": 301,
            "risk_name": "综合风险观察",
            "canonical_risk_key": "baseline_observation",
            "risk_category": "baseline",
            "risk_level": "LOW",
            "risk_score": 30,
            "source_type": "baseline",
            "source_mode": "baseline_observation",
            "is_baseline_observation": True,
        }
    ]

    monkeypatch.setattr("app.services.dashboard_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr(
        "app.services.dashboard_service.RiskAnalysisService.get_analysis_state",
        lambda self, db, enterprise_id: {"analysis_status": "completed", "last_run_at": "2026-04-16T07:55:26+00:00", "last_error": None},
    )
    monkeypatch.setattr("app.services.dashboard_service.DocumentRiskService.list_risks", lambda self, db, enterprise_id: baseline_only)

    payload = DashboardService().build_dashboard(_FakeDB(), enterprise_id=2)

    assert payload["score"] == {
        "total": 0,
        "financial": 0,
        "operational": 0,
        "compliance": 0,
    }
    assert payload["top_risks"] == []
    assert payload["trend"] == [{"report_period": "未分析", "risk_score": 0}]


def test_dashboard_respects_filtered_final_risks_after_overrides(monkeypatch) -> None:
    enterprise = SimpleNamespace(id=3, name="测试企业", ticker="688001.SH", industry_tag="制造业", report_year=2026)
    filtered_final_risks = [
        {
            "id": 401,
            "risk_name": "收入确认与收入真实性风险",
            "canonical_risk_key": "revenue_recognition",
            "risk_category": "document_risk",
            "risk_level": "HIGH",
            "risk_score": 88,
            "source_type": "document_rule",
        }
    ]

    monkeypatch.setattr("app.services.dashboard_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr(
        "app.services.dashboard_service.RiskAnalysisService.get_analysis_state",
        lambda self, db, enterprise_id: {"analysis_status": "completed", "last_run_at": None, "last_error": None},
    )
    monkeypatch.setattr("app.services.dashboard_service.DocumentRiskService.list_risks", lambda self, db, enterprise_id: filtered_final_risks)

    payload = DashboardService().build_dashboard(_FakeDB(), enterprise_id=3)

    assert payload["score"]["financial"] == 88.0
    assert payload["top_risks"] == [
        {
            "id": 401,
            "risk_name": "收入确认与收入真实性风险",
            "risk_level": "HIGH",
            "risk_score": 88.0,
            "source_type": "document_rule",
        }
    ]
    assert payload["trend"] == [{"report_period": "T1", "risk_score": 88.0}]
