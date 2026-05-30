from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import audit_focus as audit_focus_route
from app.models import AuditRecommendation, RiskIdentificationResult
from app.services import audit_focus_service
from app.services.audit_focus_service import AuditFocusService
from app.services.document_risk_service import DocumentRiskService
from app.services.risk_analysis_service import RiskAnalysisService


def test_financial_data_fixed_asset_rule_maps_to_formal_risk_title():
    risk_key = DocumentRiskService.RULE_CODE_TO_RISK_KEY["FIN_DATA_FIXED_ASSET_VOLATILITY"]

    assert risk_key != "uncategorized"
    assert DocumentRiskService.RISK_TITLES[risk_key] == "固定资产异常波动风险"


def test_new_financial_data_rules_map_to_formal_risk_titles():
    expected = {
        "FIN_DATA_DEDUCT_PROFIT_DEPENDENCE": "扣非利润偏低风险",
        "FIN_DATA_AR_TURNOVER_DECLINE": "应收账款周转放缓风险",
        "FIN_DATA_INVENTORY_TURNOVER_DECLINE": "存货周转放缓风险",
        "FIN_DATA_INTEREST_DEBT_PRESSURE": "有息负债压力风险",
        "FIN_DATA_EXPENSE_RATIO_INCREASE": "期间费用率上升风险",
    }

    for rule_code, title in expected.items():
        risk_key = DocumentRiskService.RULE_CODE_TO_RISK_KEY[rule_code]
        assert risk_key != "uncategorized"
        assert DocumentRiskService.RISK_TITLES[risk_key] == title


def test_financial_data_risk_persists_fixed_asset_audit_recommendation():
    top_risk = {
        "rule_code": "FIN_DATA_FIXED_ASSET_VOLATILITY",
        "risk_name": "固定资产异常波动",
        "risk_level": "中",
        "risk_score": 73.69,
        "judgment": "固定资产异常波动：中风险",
        "evidence": "近4季固定资产最大最小差/期初固定资产为 26.15%。",
        "periods": ["2025Q1", "2025Q2", "2025Q3", "2025Q4"],
    }

    class FakeDb:
        def __init__(self) -> None:
            self.added = []

        def add(self, item):
            self.added.append(item)

        def flush(self) -> None:
            for item in self.added:
                if isinstance(item, RiskIdentificationResult) and item.id is None:
                    item.id = 30

    service = RiskAnalysisService.__new__(RiskAnalysisService)
    service.financial_data_risk_service = SimpleNamespace(
        evaluate_indicators=lambda financials, industry_comparison=None: [top_risk],
        result_level_code=lambda risk: "MEDIUM",
    )
    service.evidence_summary_service = SimpleNamespace(summarize_evidence=lambda **kwargs: kwargs["text"])
    db = FakeDb()

    service._persist_financial_data_risk(db, enterprise_id=6, run_id=12, financials=[])

    recommendations = [item for item in db.added if isinstance(item, AuditRecommendation)]
    assert len(recommendations) == 1
    assert recommendations[0].risk_result_id == 30
    assert recommendations[0].focus_accounts == ["固定资产", "在建工程", "累计折旧", "资产减值损失"]
    assert recommendations[0].recommended_procedures == [
        "复核固定资产增减",
        "检查在建工程转固",
        "抽查资本化凭证",
        "复核折旧和减值",
    ]
    assert "financial_indicator" in recommendations[0].evidence_types


def test_financial_data_risk_persists_all_matches_with_separate_recommendations():
    risks = [
        {
            "rule_code": "FIN_DATA_EXPENSE_RATIO_INCREASE",
            "risk_name": "期间费用率上升",
            "risk_level": "中",
            "risk_score": 69.0,
            "judgment": "期间费用率上升：中风险",
            "evidence": "期间费用率由 6.00% 上升至 10.00%。",
            "periods": ["2025Q1", "2025Q2"],
        },
        {
            "rule_code": "FIN_DATA_INDUSTRY_DEVIATION",
            "risk_name": "行业对比偏离",
            "risk_level": "高",
            "risk_score": 88.0,
            "judgment": "行业对比偏离：高风险",
            "evidence": "2025Q2 毛利率高于龙头基准；存货周转率低于龙头基准。",
            "periods": ["2025Q2"],
        },
    ]

    class FakeDb:
        def __init__(self) -> None:
            self.added = []
            self.next_id = 30

        def add(self, item):
            self.added.append(item)

        def flush(self) -> None:
            for item in self.added:
                if isinstance(item, RiskIdentificationResult) and item.id is None:
                    item.id = self.next_id
                    self.next_id += 1

    service = RiskAnalysisService.__new__(RiskAnalysisService)
    service.financial_data_risk_service = SimpleNamespace(
        evaluate_indicators=lambda financials, industry_comparison=None: risks,
        result_level_code=lambda risk: "HIGH" if risk["risk_level"] == "高" else "MEDIUM",
    )
    service.evidence_summary_service = SimpleNamespace(summarize_evidence=lambda **kwargs: kwargs["text"])
    db = FakeDb()

    service._persist_financial_data_risk(db, enterprise_id=6, run_id=12, financials=[])

    results = [item for item in db.added if isinstance(item, RiskIdentificationResult)]
    recommendations = [item for item in db.added if isinstance(item, AuditRecommendation)]
    assert [item.rule_code for item in results] == [
        "FIN_DATA_EXPENSE_RATIO_INCREASE",
        "FIN_DATA_INDUSTRY_DEVIATION",
    ]
    assert [item.risk_result_id for item in recommendations] == [30, 31]
    assert results[0].evidence_chain[0]["evidence_type"] == "financial_indicator"
    assert results[0].evidence_chain[0]["source"] == "akshare"
    assert results[1].evidence_chain[0]["evidence_type"] == "industry_signal"
    assert results[1].evidence_chain[0]["source"] == "eastmoney_yjbb"


def test_audit_focus_refresh_bypasses_matching_snapshot(monkeypatch):
    risk = {
        "risk_name": "固定资产异常波动风险",
        "canonical_risk_key": "financial_fixed_asset_volatility",
        "risk_level": "MEDIUM",
        "risk_score": 73.69,
        "summary": "固定资产异常波动：中风险",
        "source_mode": "rule_only",
        "evidence_status": "rule_inferred",
        "evidence_types": ["financial_indicator"],
        "recommended_procedures": ["复核固定资产增减"],
        "evidence": [
            {
                "evidence_id": "FD-FIN_DATA_FIXED_ASSET_VOLATILITY",
                "title": "固定资产异常波动",
                "snippet": "近4季固定资产最大最小差/期初固定资产为 26.15%。",
                "content": "近4季固定资产最大最小差/期初固定资产为 26.15%。",
                "published_at": None,
            }
        ],
    }
    analysis_state = {"analysis_status": "completed", "last_run_at": None, "last_error": None}

    class DummyLLM:
        config_error = True

    class FakeDb:
        def add(self, item) -> None:
            self.item = item

        def commit(self) -> None:
            self.committed = True

    service = AuditFocusService(llm_client=DummyLLM())
    input_hash = service._input_hash(6, [risk])
    enterprise = SimpleNamespace(
        id=6,
        name="宁德时代",
        portrait={
            service.SNAPSHOT_KEY: {
                "input_hash": input_hash,
                "payload": {
                    "enterprise_id": 6,
                    "items": [{"id": "old", "title": "旧建议", "summary": "旧建议"}],
                    "recommendations": ["旧建议"],
                },
            }
        },
    )

    class FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        def get_by_id(self, enterprise_id):
            return enterprise if enterprise_id == 6 else None

    class FakeRiskAnalysis:
        def get_analysis_state(self, db, enterprise_id):
            return analysis_state

    class FakeDocumentRisk:
        def list_risks(self, db, enterprise_id):
            return [risk]

    monkeypatch.setattr(audit_focus_service, "EnterpriseRepository", FakeRepo)
    monkeypatch.setattr(audit_focus_service, "DocumentRiskService", lambda: FakeDocumentRisk())

    import app.services.risk_analysis_service as risk_analysis_module

    monkeypatch.setattr(risk_analysis_module, "RiskAnalysisService", FakeRiskAnalysis)

    cached = service.build_focus(FakeDb(), 6)
    refreshed = service.build_focus(FakeDb(), 6, refresh=True)

    assert cached["items"][0]["title"] == "旧建议"
    assert refreshed["items"][0]["title"] == "固定资产异常波动风险"
    assert refreshed["items"][0]["expanded_sections"][0]["items"][:4] == [
        "复核固定资产增减",
        "检查在建工程转固",
        "抽查资本化凭证",
        "复核折旧和减值",
    ]


def test_fixed_asset_focus_keeps_required_procedures_when_llm_returns_custom_items():
    class FakeLLM:
        config_error = False

        def chat_completion(self, *args, **kwargs):
            return {
                "targeted_advice": "先查固定资产波动，再看转固和减值。",
                "procedures": ["访谈设备管理负责人"],
                "evidence_to_obtain": ["设备台账"],
                "focus_accounts": ["固定资产"],
                "focus_processes": ["固定资产管理"],
                "rationale": "固定资产波动较大。",
            }

    risk = {
        "risk_name": "固定资产异常波动风险",
        "canonical_risk_key": "financial_fixed_asset_volatility",
        "risk_level": "MEDIUM",
        "risk_score": 73.69,
        "summary": "固定资产异常波动：中风险",
        "source_mode": "rule_only",
        "evidence_types": ["financial_indicator"],
        "evidence": [],
    }

    item = AuditFocusService(llm_client=FakeLLM())._build_focus_item(
        enterprise_name="宁德时代",
        risk=risk,
        index=1,
    )

    assert item["expanded_sections"][0]["items"][:4] == [
        "复核固定资产增减",
        "检查在建工程转固",
        "抽查资本化凭证",
        "复核折旧和减值",
    ]
    assert "访谈设备管理负责人" in item["expanded_sections"][0]["items"]


def test_audit_focus_reads_financial_analysis_snapshot_anomalies(monkeypatch):
    formal_risk = {
        "risk_name": "固定资产异常波动风险",
        "canonical_risk_key": "financial_fixed_asset_volatility",
        "risk_level": "MEDIUM",
        "risk_score": 73.69,
        "summary": "固定资产异常波动：中风险",
        "source_mode": "rule_only",
        "evidence_types": ["financial_indicator"],
        "evidence": [],
    }
    analysis_state = {"analysis_status": "completed", "last_run_at": None, "last_error": None}
    enterprise = SimpleNamespace(
        id=6,
        name="宁德时代",
        portrait={
            AuditFocusService.FINANCIAL_ANALYSIS_SNAPSHOT_KEY: {
                "anomalies": [
                    {
                        "document_id": 1,
                        "document_name": "2024年年度报告",
                        "title": "历史财报异常",
                        "summary": "旧报告里的异常。",
                        "canonical_risk_key": "cashflow_quality",
                        "fiscal_year": 2024,
                        "fiscal_quarter": 4,
                        "announcement_date": "2025-04-15",
                        "risk_score": 68.0,
                        "risk_level": "MEDIUM",
                    },
                    {
                        "document_id": 2,
                        "document_name": "2025年第三季度报告",
                        "title": "收入与成本同步增长",
                        "summary": "收入和成本同步增长，需要复核收入确认与成本结转。",
                        "canonical_risk_key": "revenue_recognition",
                        "metric_name": "营业收入",
                        "period": "2025Q3",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 3,
                        "announcement_date": "2025-10-30",
                        "risk_score": 76.0,
                        "risk_level": "MEDIUM",
                    },
                    {
                        "document_id": 2,
                        "document_name": "2025年第三季度报告",
                        "title": "应收账款减值风险",
                        "summary": "信用减值损失扩大，需要关注回款和坏账准备。",
                        "canonical_risk_key": "receivable_recoverability",
                        "metric_name": "应收账款",
                        "period": "2025Q3",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 3,
                        "announcement_date": "2025-10-30",
                        "risk_score": 78.0,
                        "risk_level": "MEDIUM",
                    },
                ],
                "focus_accounts": ["营业收入", "应收账款"],
                "recommended_procedures": [
                    "实施趋势分析并复核异常波动原因",
                    "结合附注与披露复核关键财务指标口径",
                ],
            }
        },
    )

    class DummyLLM:
        config_error = True

    class FakeDb:
        def add(self, item) -> None:
            self.item = item

        def commit(self) -> None:
            self.committed = True

    class FakeRepo:
        def __init__(self, db) -> None:
            self.db = db

        def get_by_id(self, enterprise_id):
            return enterprise if enterprise_id == 6 else None

    class FakeRiskAnalysis:
        def get_analysis_state(self, db, enterprise_id):
            return analysis_state

    class FakeDocumentRisk:
        def list_risks(self, db, enterprise_id):
            return [formal_risk]

    monkeypatch.setattr(audit_focus_service, "EnterpriseRepository", FakeRepo)
    monkeypatch.setattr(audit_focus_service, "DocumentRiskService", lambda: FakeDocumentRisk())

    import app.services.risk_analysis_service as risk_analysis_module

    monkeypatch.setattr(risk_analysis_module, "RiskAnalysisService", FakeRiskAnalysis)

    payload = AuditFocusService(llm_client=DummyLLM()).build_focus(FakeDb(), 6, refresh=True)

    titles = [item["title"] for item in payload["items"]]
    assert titles[:3] == ["固定资产异常波动风险", "收入与成本同步增长", "应收账款减值风险"]
    assert "历史财报异常" not in titles
    assert "financial_anomaly" in payload["evidence_types"]

    revenue_item = payload["items"][1]
    assert "执行收入截止测试" in revenue_item["expanded_sections"][0]["items"]
    assert "实施趋势分析并复核异常波动原因" in revenue_item["expanded_sections"][0]["items"]
    assert "财务报表附注" in revenue_item["expanded_sections"][1]["items"]


def test_audit_focus_input_hash_changes_with_financial_analysis_anomaly():
    service = AuditFocusService(llm_client=SimpleNamespace(config_error=True))

    def enterprise_with_summary(summary: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=6,
            portrait={
                service.FINANCIAL_ANALYSIS_SNAPSHOT_KEY: {
                    "anomalies": [
                        {
                            "document_id": 2,
                            "title": "应收账款减值风险",
                            "summary": summary,
                            "canonical_risk_key": "receivable_recoverability",
                            "fiscal_year": 2025,
                            "fiscal_quarter": 3,
                        }
                    ],
                    "recommended_procedures": ["实施趋势分析并复核异常波动原因"],
                }
            },
        )

    first = service._financial_analysis_risks_from_snapshot(enterprise_with_summary("回款压力扩大。"))
    second = service._financial_analysis_risks_from_snapshot(enterprise_with_summary("回款压力明显缓解。"))

    assert service._input_hash(6, first) != service._input_hash(6, second)


def test_audit_focus_route_passes_refresh_flag(monkeypatch):
    calls = {}

    class FakeService:
        def build_focus(self, db, enterprise_id, *, refresh=False):
            calls["enterprise_id"] = enterprise_id
            calls["refresh"] = refresh
            return {"enterprise_id": enterprise_id, "items": []}

    monkeypatch.setattr(audit_focus_route, "AuditFocusService", FakeService)

    payload = audit_focus_route.get_audit_focus(6, refresh=True, db=SimpleNamespace())

    assert payload == {"enterprise_id": 6, "items": []}
    assert calls == {"enterprise_id": 6, "refresh": True}
