from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnterpriseProfile, FinancialIndicator, IndustryBenchmark
from app.services.industry_classifier_service import IndustryClassification, IndustryClassifierService


class IndustryBenchmarkService:
    METRICS = {
        "gross_margin": "gross_margin_benchmark",
        "ar_turnover": "ar_turnover_benchmark",
        "debt_ratio": "debt_ratio_benchmark",
    }
    MEAN_MIN_SAMPLE = 5
    DISTRIBUTION_MIN_SAMPLE = 8
    OFFICIAL_FINANCIAL_SOURCES = {"akshare"}

    def __init__(self, classifier: IndustryClassifierService | None = None) -> None:
        self.classifier = classifier or IndustryClassifierService()

    def build_comparison(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        financials: list[FinancialIndicator],
        benchmarks: list[IndustryBenchmark] | None = None,
    ) -> dict[str, Any]:
        classification = self.classifier.classify(enterprise)
        latest_year = self._latest_annual_year(financials)
        payload: dict[str, Any] = {
            "industry_code": classification.industry_code,
            "industry_name": classification.industry_name,
            "industry_source": classification.source,
        }
        if classification.industry_code == "unknown" or latest_year is None:
            for metric in self.METRICS:
                payload[metric] = self._unavailable(None, "unknown_industry" if classification.industry_code == "unknown" else "missing_company_metric")
            return payload

        benchmarks = benchmarks if benchmarks is not None else self._load_benchmarks(db, classification)
        company_values = self._latest_company_values(financials, latest_year)
        peer_values = self._load_peer_values(db, enterprise.id, classification, latest_year)

        for metric, benchmark_code in self.METRICS.items():
            company_value = company_values.get(metric)
            benchmark_value = self._benchmark_value(benchmarks, classification, benchmark_code)
            peers = peer_values.get(metric, [])
            payload[metric] = self._build_metric_comparison(
                company_value=company_value,
                benchmark_value=benchmark_value,
                peer_values=peers,
                metric=metric,
            )
        return payload

    def _load_benchmarks(self, db: Session, classification: IndustryClassification) -> list[IndustryBenchmark]:
        rows = list(db.scalars(select(IndustryBenchmark).where(IndustryBenchmark.source != "mock")).all())
        return [row for row in rows if self.classifier.classify(industry_tag=row.industry_tag).industry_code == classification.industry_code]

    def _load_peer_values(
        self,
        db: Session,
        enterprise_id: int,
        classification: IndustryClassification,
        latest_year: int,
    ) -> dict[str, list[float]]:
        stmt = (
            select(FinancialIndicator, EnterpriseProfile)
            .join(EnterpriseProfile, EnterpriseProfile.id == FinancialIndicator.enterprise_id)
            .where(
                FinancialIndicator.enterprise_id != enterprise_id,
                FinancialIndicator.period_type == "annual",
                FinancialIndicator.report_year == latest_year,
                FinancialIndicator.indicator_code.in_(list(self.METRICS.keys())),
                FinancialIndicator.source.in_(self.OFFICIAL_FINANCIAL_SOURCES),
            )
        )
        grouped: dict[str, list[float]] = {metric: [] for metric in self.METRICS}
        for indicator, peer in db.execute(stmt).all():
            if self.classifier.classify(peer).industry_code != classification.industry_code:
                continue
            grouped.setdefault(indicator.indicator_code, []).append(float(indicator.value))
        return grouped

    def _build_metric_comparison(
        self,
        *,
        company_value: float | None,
        benchmark_value: float | None,
        peer_values: list[float],
        metric: str,
    ) -> dict[str, Any]:
        sample_count = len(peer_values)
        if company_value is None:
            return self._unavailable(None, "missing_company_metric", sample_count=sample_count)

        dynamic_mean = mean(peer_values) if sample_count >= self.MEAN_MIN_SAMPLE else None
        industry_mean = benchmark_value if benchmark_value is not None else dynamic_mean
        if industry_mean is None:
            return self._unavailable(company_value, "insufficient_sample", sample_count=sample_count)

        gap = company_value - industry_mean
        gap_pct = gap / abs(industry_mean) if industry_mean else None
        zscore = None
        percentile = None
        std_dev = pstdev(peer_values) if sample_count >= self.DISTRIBUTION_MIN_SAMPLE else 0.0
        if sample_count >= self.DISTRIBUTION_MIN_SAMPLE and std_dev > 0:
            zscore = (company_value - mean(peer_values)) / std_dev
            percentile = sum(1 for value in peer_values if value <= company_value) / sample_count

        return {
            "company_value": company_value,
            "industry_mean": industry_mean,
            "gap": gap,
            "gap_pct": gap_pct,
            "zscore": zscore if self._is_finite(zscore) else None,
            "percentile": percentile if self._is_finite(percentile) else None,
            "available": True,
            "sample_count": sample_count,
            "source": "industry_benchmark" if benchmark_value is not None else "peer_financials",
            "unavailable_reason": None,
            "distribution_available": sample_count >= self.DISTRIBUTION_MIN_SAMPLE and std_dev > 0,
            "metric": metric,
        }

    def _benchmark_value(
        self,
        benchmarks: list[IndustryBenchmark],
        classification: IndustryClassification,
        metric_code: str,
    ) -> float | None:
        candidates = [
            row
            for row in benchmarks
            if row.metric_code == metric_code
            and self.classifier.classify(industry_tag=row.industry_tag).industry_code == classification.industry_code
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: (str(row.report_period), row.id or 0), reverse=True)
        return float(candidates[0].value)

    def _latest_annual_year(self, financials: list[FinancialIndicator]) -> int | None:
        years = [int(item.report_year) for item in financials if item.period_type == "annual"]
        return max(years) if years else None

    def _latest_company_values(self, financials: list[FinancialIndicator], latest_year: int) -> dict[str, float]:
        values: dict[str, float] = {}
        for item in financials:
            if item.period_type == "annual" and item.report_year == latest_year and item.indicator_code in self.METRICS:
                values[item.indicator_code] = float(item.value)
        return values

    def _unavailable(self, company_value: float | None, reason: str, *, sample_count: int = 0) -> dict[str, Any]:
        return {
            "company_value": company_value,
            "industry_mean": None,
            "gap": None,
            "gap_pct": None,
            "zscore": None,
            "percentile": None,
            "available": False,
            "sample_count": sample_count,
            "source": None,
            "unavailable_reason": reason,
            "distribution_available": False,
        }

    def _is_finite(self, value: float | None) -> bool:
        return value is not None and math.isfinite(value)
