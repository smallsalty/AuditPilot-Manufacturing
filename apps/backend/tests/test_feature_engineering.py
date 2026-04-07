from datetime import date

from app.models import ExternalEvent, FinancialIndicator, IndustryBenchmark
from app.services.feature_engineering_service import FeatureEngineeringService


def test_feature_engineering_computes_growth_and_gaps() -> None:
    financials = [
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20231231",
            report_year=2023,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=100.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20241231",
            report_year=2024,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=120.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20231231",
            report_year=2023,
            indicator_code="accounts_receivable",
            indicator_name="应收账款",
            value=20.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20241231",
            report_year=2024,
            indicator_code="accounts_receivable",
            indicator_name="应收账款",
            value=30.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20241231",
            report_year=2024,
            indicator_code="net_profit",
            indicator_name="净利润",
            value=10.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="annual",
            report_period="20241231",
            report_year=2024,
            indicator_code="operating_cash_flow",
            indicator_name="经营现金流",
            value=3.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="quarterly",
            report_period="20240331",
            report_year=2024,
            report_quarter=1,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=20.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="quarterly",
            report_period="20240630",
            report_year=2024,
            report_quarter=2,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=20.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="quarterly",
            report_period="20240930",
            report_year=2024,
            report_quarter=3,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=20.0,
            source="test",
        ),
        FinancialIndicator(
            enterprise_id=1,
            period_type="quarterly",
            report_period="20241231",
            report_year=2024,
            report_quarter=4,
            indicator_code="revenue",
            indicator_name="营业收入",
            value=40.0,
            source="test",
        ),
    ]
    events = [
        ExternalEvent(
            enterprise_id=1,
            event_type="penalty",
            severity="MEDIUM",
            title="处罚",
            event_date=date(2024, 1, 1),
            source="test",
            summary="处罚",
        )
    ]
    benchmarks = [
        IndustryBenchmark(
            industry_tag="工程机械",
            report_period="202412",
            metric_code="demand_index_yoy",
            metric_name="景气度",
            value=-0.1,
            source="test",
        )
    ]

    features = FeatureEngineeringService().build_features(financials, events, benchmarks)

    assert round(features["revenue_growth_rate"], 2) == 0.20
    assert round(features["accounts_receivable_growth_rate"], 2) == 0.50
    assert round(features["ar_revenue_growth_gap"], 2) == 0.30
    assert round(features["operating_cf_profit_ratio"], 2) == 0.30
    assert round(features["q4_revenue_ratio"], 2) == 0.40
    assert features["penalty_count"] == 1.0

