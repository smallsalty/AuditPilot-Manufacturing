from types import SimpleNamespace

from app.models import AuditRecommendation, RiskIdentificationResult
from app.services.risk_analysis_service import RiskAnalysisService


class _ScalarResult:
    def all(self):
        return []


class _FakeDB:
    def __init__(self) -> None:
        self._next_id = 1
        self.added = []

    def scalars(self, query):
        return _ScalarResult()

    def add(self, obj) -> None:
        self.added.append(obj)
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

    def flush(self) -> None:
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


def test_run_persists_tax_risk_results_into_standard_pipeline(monkeypatch) -> None:
    service = RiskAnalysisService()
    db = _FakeDB()
    enterprise = SimpleNamespace(id=3, name="测试企业", sync_status="synced", industry_tag="制造业")
    financial = SimpleNamespace(id=1, period_type="annual", report_year=2024, indicator_code="revenue", value=100.0)

    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_by_id", lambda self, enterprise_id: enterprise)
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_latest_analysis_run", lambda self, enterprise_id: None)
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_financials", lambda self, enterprise_id, official_only=True: [financial])
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_external_events", lambda self, enterprise_id, official_only=True: [])
    monkeypatch.setattr("app.services.risk_analysis_service.EnterpriseRepository.get_documents", lambda self, enterprise_id, official_only=True: [])
    monkeypatch.setattr("app.services.risk_analysis_service.RiskRepository.clear_enterprise_results", lambda self, enterprise_id: None)
    monkeypatch.setattr(service.industry_benchmark_service, "build_comparison", lambda db, enterprise, financials, benchmarks: {})
    monkeypatch.setattr(service.feature_engineering_service, "build_features", lambda financials, events, benchmarks, industry_comparison=None: {"latest_year": 2024})
    monkeypatch.setattr(service.rule_evaluator, "evaluate", lambda rule, features, **kwargs: None)
    monkeypatch.setattr(service, "_run_anomaly_detection", lambda enterprise_id, run_id, features, financials: None)
    monkeypatch.setattr(
        service.tax_risk_service,
        "build_tax_risks",
        lambda db, enterprise_id: {
            "enterprise_id": enterprise_id,
            "as_of_period": "20241231",
            "evaluation_basis": "latest_annual",
            "diagnostics": {"evaluated_rules": ["TAX_ETR_ABNORMAL"], "skipped_rules": [], "missing_indicators": []},
            "tax_risks": [
                {
                    "rule_code": "TAX_ETR_ABNORMAL",
                    "canonical_risk_key": "tax_effective_rate_anomaly",
                    "risk_name": "企业所得税有效税率异常",
                    "risk_category": "合规风险",
                    "risk_level": "HIGH",
                    "risk_score": 88.0,
                    "summary": "税率异常",
                    "reasons": ["本期有效税率显著偏离。"],
                    "report_period": "20241231",
                    "period_type": "annual",
                    "metrics": [{"metric_code": "effective_tax_rate", "metric_name": "有效税率", "value": 0.45, "unit": "ratio", "report_period": "20241231"}],
                    "evidence_chain": [{"title": "有效税率测算", "content": "45%", "report_period": "20241231"}],
                    "focus_accounts": ["所得税费用"],
                    "focus_processes": ["税务申报"],
                    "recommended_procedures": ["复核税率差异原因"],
                }
            ],
        },
    )

    def _list_risks(_db, enterprise_id):
        return [
            {"risk_name": obj.risk_name, "rule_code": obj.rule_code, "evidence_chain": obj.evidence_chain}
            for obj in db.added
            if isinstance(obj, RiskIdentificationResult)
        ]

    monkeypatch.setattr(service.document_risk_service, "list_risks", _list_risks)

    result = service.run(db, enterprise_id=3)

    persisted_results = [obj for obj in db.added if isinstance(obj, RiskIdentificationResult)]
    persisted_recommendations = [obj for obj in db.added if isinstance(obj, AuditRecommendation)]
    assert result["status"] == "completed"
    assert any(item["rule_code"] == "TAX_ETR_ABNORMAL" for item in result["results"])
    assert any(obj.rule_code == "TAX_ETR_ABNORMAL" for obj in persisted_results)
    assert any("所得税费用" in obj.recommendation_text for obj in persisted_recommendations)
