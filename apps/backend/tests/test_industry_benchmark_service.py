from types import SimpleNamespace

from app.services.industry_benchmark_service import IndustryBenchmarkService
from app.services.industry_classifier_service import IndustryClassifierService


def test_industry_classifier_normalizes_existing_industry_names() -> None:
    classifier = IndustryClassifierService()

    a = classifier.classify(industry_tag="工程机械")
    b = classifier.classify(sub_industry="专用设备制造")
    unknown = classifier.classify(industry_tag="未覆盖行业")

    assert a.industry_code == "construction_machinery"
    assert b.industry_code == "construction_machinery"
    assert unknown.industry_code == "unknown"


def test_metric_comparison_does_not_use_zero_when_sample_is_insufficient() -> None:
    service = IndustryBenchmarkService()

    result = service._build_metric_comparison(
        company_value=30.0,
        benchmark_value=None,
        peer_values=[20.0, 21.0, 22.0, 23.0],
        metric="gross_margin",
    )

    assert result["available"] is False
    assert result["industry_mean"] is None
    assert result["zscore"] is None
    assert result["percentile"] is None
    assert result["unavailable_reason"] == "insufficient_sample"


def test_benchmark_mean_can_be_available_while_distribution_is_gated() -> None:
    service = IndustryBenchmarkService()

    result = service._build_metric_comparison(
        company_value=30.0,
        benchmark_value=22.0,
        peer_values=[20.0, 21.0, 22.0, 23.0, 24.0],
        metric="gross_margin",
    )

    assert result["available"] is True
    assert result["industry_mean"] == 22.0
    assert result["source"] == "industry_benchmark"
    assert result["zscore"] is None
    assert result["percentile"] is None
    assert result["distribution_available"] is False


def test_distribution_metrics_require_eight_peer_samples() -> None:
    service = IndustryBenchmarkService()

    result = service._build_metric_comparison(
        company_value=30.0,
        benchmark_value=None,
        peer_values=[10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0],
        metric="gross_margin",
    )

    assert result["available"] is True
    assert result["zscore"] is not None
    assert result["percentile"] == 1.0
