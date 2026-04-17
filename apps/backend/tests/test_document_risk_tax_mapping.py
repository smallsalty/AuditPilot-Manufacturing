from types import SimpleNamespace

from app.services.document_risk_service import DocumentRiskService


def test_document_risk_service_maps_tax_rule_code_to_canonical_key(monkeypatch) -> None:
    service = DocumentRiskService()
    result = SimpleNamespace(
        id=11,
        source_type="rule",
        rule_code="TAX_ETR_ABNORMAL",
        risk_score=88.0,
        llm_summary="税率异常",
        reasons=["本期有效税率明显偏离。"],
        risk_category="合规风险",
        risk_level="HIGH",
        feature_snapshot={},
        evidence_chain=[],
    )

    monkeypatch.setattr("app.services.document_risk_service.EnterpriseRepository.get_documents", lambda self, enterprise_id, official_only=True: [])
    monkeypatch.setattr("app.services.document_risk_service.RiskRepository.list_results", lambda self, enterprise_id: [result])
    monkeypatch.setattr("app.services.document_risk_service.RiskRepository.list_recommendations", lambda self, enterprise_id: [])
    monkeypatch.setattr("app.services.document_risk_service.DocumentRepository.list_overrides", lambda self, enterprise_id=None, scope=None: [])

    payload = service.list_risks(db=object(), enterprise_id=1)

    assert payload[0]["canonical_risk_key"] == "tax_effective_rate_anomaly"
    assert payload[0]["risk_name"] == "企业所得税有效税率异常风险"
