from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import EnterpriseProfile, FinancialIndicator
from app.models.base import Base
from app.services.tax_risk_service import TaxRiskService


def _build_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _seed_enterprise(db: Session, enterprise_id: int = 1) -> None:
    db.add(
        EnterpriseProfile(
            id=enterprise_id,
            name="测试企业",
            ticker="600000.SH",
            report_year=2024,
            industry_tag="制造业",
            exchange="SSE",
        )
    )
    db.commit()


def _add_indicator(
    db: Session,
    *,
    enterprise_id: int,
    report_period: str,
    report_year: int,
    indicator_code: str,
    value: float,
    period_type: str = "annual",
    report_quarter: int | None = None,
    unit: str = "cny",
) -> None:
    db.add(
        FinancialIndicator(
            enterprise_id=enterprise_id,
            period_type=period_type,
            report_period=report_period,
            report_year=report_year,
            report_quarter=report_quarter,
            indicator_code=indicator_code,
            indicator_name=indicator_code,
            value=value,
            unit=unit,
            source="akshare",
        )
    )


def test_tax_risk_service_hits_all_four_rules_for_latest_annual() -> None:
    db = _build_session()
    _seed_enterprise(db)
    for code, value in {
        "revenue": 100.0,
        "total_profit": 100.0,
        "income_tax_expense": 45.0,
        "operate_tax_surcharge": 10.0,
        "pay_all_tax_cash": 20.0,
        "deferred_tax_asset": 300.0,
        "deferred_tax_liability": 20.0,
        "deferred_tax_cash_adjustment": 80.0,
        "tax_payable": 200.0,
        "total_assets": 10000.0,
    }.items():
        _add_indicator(db, enterprise_id=1, report_period="20241231", report_year=2024, indicator_code=code, value=value)
    for code, value in {
        "revenue": 95.0,
        "total_profit": 100.0,
        "income_tax_expense": 24.0,
        "operate_tax_surcharge": 9.0,
        "pay_all_tax_cash": 32.0,
        "deferred_tax_asset": 50.0,
        "deferred_tax_liability": 10.0,
        "tax_payable": 100.0,
        "total_assets": 9000.0,
    }.items():
        _add_indicator(db, enterprise_id=1, report_period="20231231", report_year=2023, indicator_code=code, value=value)
    for code, value in {
        "total_profit": 100.0,
        "income_tax_expense": 25.0,
    }.items():
        _add_indicator(db, enterprise_id=1, report_period="20221231", report_year=2022, indicator_code=code, value=value)
    db.commit()

    payload = TaxRiskService().build_tax_risks(db, 1)

    assert payload["evaluation_basis"] == "latest_annual"
    assert payload["as_of_period"] == "20241231"
    assert {item["rule_code"] for item in payload["tax_risks"]} == {
        "TAX_ETR_ABNORMAL",
        "TAX_CASHFLOW_MISMATCH",
        "DEFERRED_TAX_VOLATILITY",
        "TAX_PAYABLE_ACCRUAL",
    }
    etr_item = next(item for item in payload["tax_risks"] if item["rule_code"] == "TAX_ETR_ABNORMAL")
    assert etr_item["canonical_risk_key"] == "tax_effective_rate_anomaly"
    assert etr_item["risk_category"] == "合规风险"
    assert any(metric["metric_code"] == "effective_tax_rate" for metric in etr_item["metrics"])


def test_tax_risk_service_skips_rules_safely_when_required_values_missing() -> None:
    db = _build_session()
    _seed_enterprise(db)
    _add_indicator(db, enterprise_id=1, report_period="20241231", report_year=2024, indicator_code="total_profit", value=-10.0)
    _add_indicator(db, enterprise_id=1, report_period="20241231", report_year=2024, indicator_code="income_tax_expense", value=5.0)
    db.commit()

    payload = TaxRiskService().build_tax_risks(db, 1)

    assert payload["tax_risks"] == []
    skipped = {item["rule_code"]: item for item in payload["diagnostics"]["skipped_rules"]}
    assert skipped["TAX_ETR_ABNORMAL"]["reason"] == "利润总额小于等于 0，跳过有效税率规则。"
    assert "pay_all_tax_cash" in payload["diagnostics"]["missing_indicators"]
    assert "tax_payable" in payload["diagnostics"]["missing_indicators"]


def test_tax_risk_service_falls_back_to_latest_report_when_no_annual_data() -> None:
    db = _build_session()
    _seed_enterprise(db)
    for code, value in {
        "revenue": 100.0,
        "tax_payable": 160.0,
        "pay_all_tax_cash": 20.0,
        "income_tax_expense": 20.0,
        "operate_tax_surcharge": 10.0,
    }.items():
        _add_indicator(
            db,
            enterprise_id=1,
            report_period="20240930",
            report_year=2024,
            report_quarter=3,
            period_type="quarterly",
            indicator_code=code,
            value=value,
        )
    for code, value in {
        "revenue": 95.0,
        "tax_payable": 100.0,
    }.items():
        _add_indicator(
            db,
            enterprise_id=1,
            report_period="20230930",
            report_year=2023,
            report_quarter=3,
            period_type="quarterly",
            indicator_code=code,
            value=value,
        )
    db.commit()

    payload = TaxRiskService().build_tax_risks(db, 1)

    assert payload["evaluation_basis"] == "latest_report"
    assert payload["as_of_period"] == "20240930"
    assert any(item["rule_code"] == "TAX_PAYABLE_ACCRUAL" for item in payload["tax_risks"])
