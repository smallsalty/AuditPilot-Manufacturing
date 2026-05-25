from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyIndustryMapping, EnterpriseProfile, FinancialIndicator, IndustryBenchmark, IndustryBenchmarkSnapshot
from app.services.industry_classifier_service import IndustryClassifierService
from app.services.industry_taxonomy_service import IndustryReference, IndustryTaxonomyService


class IndustryBenchmarkService:
    METRICS = (
        "revenue_growth",
        "gross_margin",
        "net_margin",
        "revenue",
        "ar_turnover",
        "inventory_turnover",
        "debt_ratio",
        "expense_ratio",
    )
    MIN_DISPLAY_SAMPLE = 5

    def __init__(self, classifier: IndustryClassifierService | None = None) -> None:
        self.classifier = classifier or IndustryClassifierService()
        self.taxonomy = IndustryTaxonomyService(self.classifier)

    def build_comparison(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        financials: list[FinancialIndicator],
        benchmarks: list[IndustryBenchmark] | None = None,
    ) -> dict[str, Any]:
        del benchmarks
        classification = self.classifier.classify(enterprise)
        period_meta = self._latest_company_period(financials)
        latest_year = period_meta["year"] if period_meta else None
        requested_period = period_meta["period"] if period_meta else None
        references = self._candidate_references(db, enterprise, classification)
        original_industry = references[0].original_industry if references else classification.industry_name
        fallback_reference = references[0] if references else None

        payload: dict[str, Any] = {
            "industry_code": classification.industry_code,
            "industry_name": classification.industry_name,
            "industry_source": classification.source,
            "latest_year": latest_year,
            "reference_industry_name": fallback_reference.industry_name if fallback_reference else classification.industry_name,
            "industry_level": fallback_reference.industry_level if fallback_reference else None,
            "fallback_used": fallback_reference.fallback_used if fallback_reference else False,
            "original_industry": original_industry,
            "cache_state": "missing",
            "cache_updated_at": None,
        }

        company_values = self._latest_company_values(financials, period_meta) if period_meta else {}
        snapshots = self._load_snapshots(db, references, requested_period)
        selected_snapshots: dict[str, IndustryBenchmarkSnapshot | None] = {}
        available_reference_keys: list[tuple[str, str, bool]] = []

        for metric in self.METRICS:
            snapshot = self._select_snapshot(snapshots, references, metric, requested_period)
            selected_snapshots[metric] = snapshot
            metric_payload = self._build_metric_payload(
                metric=metric,
                company_value=company_values.get(metric),
                snapshot=snapshot,
                requested_period=requested_period,
            )
            payload[metric] = metric_payload
            if metric_payload["available"] and snapshot is not None:
                available_reference_keys.append((snapshot.industry_name, snapshot.industry_level, snapshot.fallback_used))

        if available_reference_keys:
            reference_name, reference_level, fallback_used = Counter(available_reference_keys).most_common(1)[0][0]
            payload.update(
                {
                    "reference_industry_name": reference_name,
                    "industry_level": reference_level,
                    "fallback_used": fallback_used,
                    "cache_state": "hit" if all(payload[metric]["available"] for metric in self.METRICS) else "partial_hit",
                }
            )
        elif snapshots:
            payload["cache_state"] = "insufficient"

        cache_updated_at = self._latest_snapshot_update(selected_snapshots.values())
        if cache_updated_at:
            payload["cache_updated_at"] = cache_updated_at.isoformat()
        return payload

    def _candidate_references(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        classification: Any,
    ) -> list[IndustryReference]:
        fallback_references = self.taxonomy.candidates(enterprise, classification)
        ticker = self._ticker_symbol(getattr(enterprise, "ticker", ""))
        if not ticker:
            return fallback_references

        rows = list(
            db.scalars(
                select(CompanyIndustryMapping).where(CompanyIndustryMapping.ticker == ticker)
            ).all()
        )
        if not rows:
            return fallback_references

        original_industry = self.taxonomy.original_industry(enterprise, classification)
        references: list[IndustryReference] = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: self._mapping_source_rank(item.source)):
            industry_name = str(row.industry_name or "").strip()
            normalized = self._normalize(industry_name)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            industry_level = row.industry_level or "mapped"
            references.append(
                IndustryReference(
                    industry_name=industry_name,
                    industry_level=industry_level,
                    fallback_used=self._normalize(industry_name) != self._normalize(original_industry),
                    industry_code=row.industry_code or self.taxonomy.industry_code(industry_name, industry_level),
                    original_industry=original_industry,
                    rank=len(references),
                )
            )
        for reference in fallback_references:
            normalized = self._normalize(reference.industry_name)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            references.append(reference)
        return references

    def _load_snapshots(
        self,
        db: Session,
        references: list[IndustryReference],
        requested_period: str | None,
    ) -> list[IndustryBenchmarkSnapshot]:
        if not references:
            return []
        names = sorted({reference.industry_name for reference in references})
        stmt = select(IndustryBenchmarkSnapshot).where(
            IndustryBenchmarkSnapshot.industry_name.in_(names),
            IndustryBenchmarkSnapshot.metric.in_(self.METRICS),
        )
        rows = list(db.scalars(stmt).all())
        if requested_period is None:
            return rows
        requested_rank = self._period_rank(requested_period)
        return [
            row
            for row in rows
            if self._period_rank(row.period) <= requested_rank or row.period == requested_period
        ]

    def _select_snapshot(
        self,
        snapshots: list[IndustryBenchmarkSnapshot],
        references: list[IndustryReference],
        metric: str,
        requested_period: str | None,
    ) -> IndustryBenchmarkSnapshot | None:
        insufficient: IndustryBenchmarkSnapshot | None = None
        rows = [row for row in snapshots if row.metric == metric]
        for reference in references:
            matched = [
                row
                for row in rows
                if self._normalize(row.industry_name) == self._normalize(reference.industry_name)
            ]
            matched.sort(
                key=lambda row: (
                    0 if row.sample_count >= self.MIN_DISPLAY_SAMPLE else 1,
                    0 if requested_period and row.period == requested_period else 1,
                    0 if self._normalize(row.industry_level) == self._normalize(reference.industry_level) else 1,
                    -self._period_rank(row.period),
                    -(row.id or 0),
                )
            )
            for row in matched:
                if row.sample_count >= self.MIN_DISPLAY_SAMPLE and self._reference_value(row) is not None:
                    return row
                if insufficient is None:
                    insufficient = row
        return insufficient

    def _build_metric_payload(
        self,
        *,
        metric: str,
        company_value: float | None,
        snapshot: IndustryBenchmarkSnapshot | None,
        requested_period: str | None,
    ) -> dict[str, Any]:
        if snapshot is None:
            return self._unavailable(company_value, "cache_missing", metric=metric, requested_period=requested_period)

        sample_count = int(snapshot.sample_count or 0)
        reference_value = self._reference_value(snapshot)
        industry_values = {
            "industry_mean": self._finite(snapshot.mean),
            "industry_median": self._finite(snapshot.median),
            "p25": self._finite(snapshot.p25),
            "p75": self._finite(snapshot.p75),
        }
        if sample_count < self.MIN_DISPLAY_SAMPLE or reference_value is None:
            return self._unavailable(
                company_value,
                "insufficient_sample",
                metric=metric,
                requested_period=requested_period,
                snapshot=snapshot,
                include_industry_values=False,
            )
        if company_value is None:
            return self._unavailable(
                None,
                "missing_company_metric",
                metric=metric,
                requested_period=requested_period,
                snapshot=snapshot,
                include_industry_values=True,
            )

        gap = company_value - reference_value
        gap_pct = gap / abs(reference_value) if reference_value else None
        return {
            "company_value": company_value,
            **industry_values,
            "gap": gap,
            "gap_pct": gap_pct,
            "zscore": None,
            "percentile": None,
            "available": True,
            "sample_count": sample_count,
            "confidence": snapshot.confidence,
            "source": snapshot.source,
            "unavailable_reason": None,
            "distribution_available": sample_count >= self.MIN_DISPLAY_SAMPLE,
            "metric": metric,
            "period": snapshot.period,
            "requested_period": requested_period,
            "actual_peer_period_range": list(snapshot.actual_peer_period_range or []),
            "period_aligned": bool(snapshot.period_aligned),
            "industry_name": snapshot.industry_name,
            "industry_level": snapshot.industry_level,
            "fallback_used": bool(snapshot.fallback_used),
            "aggregation_method": snapshot.aggregation_method,
        }

    def _unavailable(
        self,
        company_value: float | None,
        reason: str,
        *,
        metric: str,
        requested_period: str | None,
        snapshot: IndustryBenchmarkSnapshot | None = None,
        include_industry_values: bool = False,
    ) -> dict[str, Any]:
        industry_mean = self._finite(snapshot.mean) if snapshot is not None and include_industry_values else None
        industry_median = self._finite(snapshot.median) if snapshot is not None and include_industry_values else None
        p25 = self._finite(snapshot.p25) if snapshot is not None and include_industry_values else None
        p75 = self._finite(snapshot.p75) if snapshot is not None and include_industry_values else None
        return {
            "company_value": company_value,
            "industry_mean": industry_mean,
            "industry_median": industry_median,
            "p25": p25,
            "p75": p75,
            "gap": None,
            "gap_pct": None,
            "zscore": None,
            "percentile": None,
            "available": False,
            "sample_count": int(snapshot.sample_count or 0) if snapshot is not None else 0,
            "confidence": snapshot.confidence if snapshot is not None else "unavailable",
            "source": snapshot.source if snapshot is not None else None,
            "unavailable_reason": reason,
            "distribution_available": False,
            "metric": metric,
            "period": snapshot.period if snapshot is not None else requested_period,
            "requested_period": requested_period,
            "actual_peer_period_range": list(snapshot.actual_peer_period_range or []) if snapshot is not None else [],
            "period_aligned": bool(snapshot.period_aligned) if snapshot is not None else False,
            "industry_name": snapshot.industry_name if snapshot is not None else None,
            "industry_level": snapshot.industry_level if snapshot is not None else None,
            "fallback_used": bool(snapshot.fallback_used) if snapshot is not None else False,
            "aggregation_method": snapshot.aggregation_method if snapshot is not None else None,
        }

    def _latest_company_values(
        self,
        financials: list[FinancialIndicator],
        period_meta: dict[str, Any] | None,
    ) -> dict[str, float]:
        if period_meta is None:
            return {}
        values: dict[str, float] = {}
        selected_period = period_meta["raw_period"]
        selected_period_type = period_meta["period_type"]
        for item in financials:
            if item.report_period != selected_period or item.period_type != selected_period_type:
                continue
            if item.indicator_code in self.METRICS:
                number = self._finite(getattr(item, "value", None))
                if number is not None:
                    values[item.indicator_code] = number
        if "revenue_growth" not in values:
            revenue_growth = self._derive_revenue_growth(financials, period_meta)
            if revenue_growth is not None:
                values["revenue_growth"] = revenue_growth
        if "net_margin" not in values:
            net_profit = values.get("net_profit")
            revenue = values.get("revenue")
            if net_profit is not None and revenue not in (None, 0):
                values["net_margin"] = (net_profit / abs(revenue)) * 100.0
        return {metric: values[metric] for metric in self.METRICS if metric in values}

    def _derive_revenue_growth(
        self,
        financials: list[FinancialIndicator],
        period_meta: dict[str, Any],
    ) -> float | None:
        current_revenue = self._metric_value(financials, period_meta, "revenue")
        if current_revenue is None:
            return None
        comparable = {
            "period_type": period_meta["period_type"],
            "year": int(period_meta["year"]) - 1,
            "quarter": period_meta["quarter"],
        }
        previous_revenue = self._metric_value(financials, comparable, "revenue")
        if previous_revenue in (None, 0):
            return None
        return ((current_revenue - previous_revenue) / abs(previous_revenue)) * 100.0

    def _metric_value(
        self,
        financials: list[FinancialIndicator],
        period_meta: dict[str, Any],
        indicator_code: str,
    ) -> float | None:
        for item in financials:
            if item.indicator_code != indicator_code:
                continue
            if item.period_type != period_meta["period_type"]:
                continue
            if int(item.report_year) != int(period_meta["year"]):
                continue
            quarter = None if item.period_type == "annual" else item.report_quarter
            if quarter != period_meta.get("quarter"):
                continue
            return self._finite(item.value)
        return None

    def _latest_company_period(self, financials: list[FinancialIndicator]) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for item in financials:
            year = int(getattr(item, "report_year", 0) or 0)
            if year <= 0:
                continue
            period_type = str(getattr(item, "period_type", "") or "")
            quarter = None if period_type == "annual" else getattr(item, "report_quarter", None)
            if quarter is None and period_type != "annual":
                quarter = self._quarter_from_raw_period(getattr(item, "report_period", ""))
            rank = 5 if period_type == "annual" else int(quarter or 0)
            candidates.append(
                {
                    "year": year,
                    "quarter": quarter,
                    "period_type": period_type,
                    "raw_period": item.report_period,
                    "period": f"{year}FY" if period_type == "annual" else f"{year}Q{quarter}",
                    "rank": year * 10 + rank,
                }
            )
        return max(candidates, key=lambda item: item["rank"]) if candidates else None

    def _latest_snapshot_update(self, snapshots: Any) -> datetime | None:
        latest: datetime | None = None
        for snapshot in snapshots:
            if snapshot is None:
                continue
            for candidate in (getattr(snapshot, "updated_at", None), getattr(snapshot, "created_at", None)):
                if isinstance(candidate, datetime) and (latest is None or candidate > latest):
                    latest = candidate
        return latest

    def _reference_value(self, snapshot: IndustryBenchmarkSnapshot) -> float | None:
        return self._finite(snapshot.median) if self._finite(snapshot.median) is not None else self._finite(snapshot.mean)

    @staticmethod
    def _quarter_from_raw_period(report_period: str) -> int:
        text = str(report_period or "")
        month = int(text[4:6]) if len(text) >= 6 and text[4:6].isdigit() else 12
        return max(1, min(4, (month - 1) // 3 + 1))

    @staticmethod
    def _period_rank(period: str | None) -> int:
        text = str(period or "").upper()
        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else 0
        if "FY" in text or text.endswith("1231"):
            return year * 10 + 5
        quarter_match = re.search(r"Q([1-4])", text)
        if quarter_match:
            return year * 10 + int(quarter_match.group(1))
        if len(text) >= 6 and text[4:6].isdigit():
            month = int(text[4:6])
            return year * 10 + max(1, min(4, (month - 1) // 3 + 1))
        return year * 10

    @staticmethod
    def _finite(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _normalize(value: str | None) -> str:
        return re.sub(r"[\s（）()_\-/]+", "", str(value or "").strip()).upper()

    @staticmethod
    def _ticker_symbol(value: str) -> str:
        normalized = str(value or "").strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]
        normalized = normalized.replace("SH", "").replace("SZ", "")
        digits = "".join(char for char in normalized if char.isdigit())
        return digits.zfill(6) if digits else ""

    @staticmethod
    def _mapping_source_rank(source: str) -> int:
        order = {
            "eastmoney_board": 0,
            "cninfo_industry_change": 1,
            "cninfo_profile": 2,
        }
        return order.get(source, 99)
