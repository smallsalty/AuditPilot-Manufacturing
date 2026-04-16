from types import SimpleNamespace

from app.services.risk_analysis_service import RiskAnalysisService


class _ScalarResult:
    def all(self):
        return []


class _FakeDB:
    def __init__(self) -> None:
        self._next_id = 1

    def scalars(self, query):
        return _ScalarResult()

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1

    def execute(self, query) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = self._next_id
            self._next_id += 1

    def rollback(self) -> None:
        return None

    def get(self, model, ident):
        return None


def test_documents_only_enterprise_is_ready_for_risk_analysis() -> None:
    enterprise = SimpleNamespace(id=2, sync_status="synced")

    readiness = RiskAnalysisService.get_analysis_readiness(
        enterprise,
        financials=[],
        events=[],
        documents=[SimpleNamespace(id=8)],
    )

    assert readiness["risk_analysis_ready"] is True
    assert readiness["risk_analysis_reason"] == "documents_only_ready"


def test_run_completes_for_documents_only_enterprise(monkeypatch) -> None:
    service = RiskAnalysisService()
    db = _FakeDB()
    enterprise = SimpleNamespace(id=2, name="徐工机械", sync_status="synced", industry_tag="机械设备")
    document = SimpleNamespace(id=8, source="cninfo")

    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_latest_analysis_run", lambda self, enterprise_id: None)
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_financials", lambda self, enterprise_id, official_only=True: [])
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_external_events", lambda self, enterprise_id, official_only=True: [])
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_documents", lambda self, enterprise_id, official_only=True: [document])
    monkeypatch.setattr("app.services.risk_analysis_service.RiskRepository.clear_enterprise_results", lambda self, enterprise_id: None)
    monkeypatch.setattr(service.feature_engineering_service, "build_features", lambda financials, events, benchmarks, industry_comparison=None: {"latest_year": 2025})
    monkeypatch.setattr(service.rule_evaluator, "evaluate", lambda rule, features, **kwargs: None)
    monkeypatch.setattr(service, "_run_anomaly_detection", lambda enterprise_id, run_id, features, financials: None)
    monkeypatch.setattr(service.document_risk_service, "list_risks", lambda db, enterprise_id: [{"risk_name": "文档风险", "evidence_chain": []}])

    result = service.run(db, enterprise_id=2)

    assert result["status"] == "completed"
    assert "未使用财务指标规则" in result["summary"]
    assert result["results"][0]["risk_name"] == "文档风险"
