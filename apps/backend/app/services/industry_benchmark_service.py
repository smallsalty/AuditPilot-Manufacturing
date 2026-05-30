from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnterpriseProfile, FinancialIndicator, IndustryBenchmarkRefreshState, IndustryLeaderBenchmark, IndustryLeaderCompany


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
    MIN_DISPLAY_SAMPLE = 3

    def build_comparison(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        financials: list[FinancialIndicator],
    ) -> dict[str, Any]:
        period_meta = self._latest_company_period(financials)
        requested_period = period_meta["period"] if period_meta else None
        payload = self._empty_payload(status="missing", period=requested_period, reason="benchmark_not_refreshed")
        if requested_period is None:
            return payload

        state = db.scalar(
            select(IndustryBenchmarkRefreshState).where(
                IndustryBenchmarkRefreshState.enterprise_id == enterprise.id,
                IndustryBenchmarkRefreshState.period == requested_period,
            )
        )
        if state is None:
            return payload

        payload.update(
            {
                "status": "ready" if state.status == "ready" else "error",
                "industry_name": state.industry_name,
                "industry_code": state.board_code,
                "source": state.source,
                "period": state.period,
                "refreshed_at": state.refreshed_at.isoformat() if state.refreshed_at else None,
                "unavailable_reason": state.error_reason,
                "board_validation_status": state.board_validation_status,
            }
        )
        if state.status != "ready" or not state.industry_name:
            return payload

        leaders = list(
            db.scalars(
                select(IndustryLeaderCompany)
                .where(
                    IndustryLeaderCompany.industry_name == state.industry_name,
                    IndustryLeaderCompany.period == requested_period,
                )
                .order_by(IndustryLeaderCompany.rank)
            ).all()
        )
        benchmarks = {
            row.metric_code: row
            for row in db.scalars(
                select(IndustryLeaderBenchmark).where(
                    IndustryLeaderBenchmark.industry_name == state.industry_name,
                    IndustryLeaderBenchmark.period == requested_period,
                )
            ).all()
        }
        company_values = self._latest_company_values(financials, period_meta)
        payload["leader_companies"] = [
            {"rank": leader.rank, "ticker": leader.ticker, "name": leader.company_name}
            for leader in leaders
        ]
        payload["metrics"] = {
            metric: self._metric_payload(company_values.get(metric), benchmarks.get(metric))
            for metric in self.METRICS
        }
        return payload

    def _empty_payload(self, *, status: str, period: str | None, reason: str) -> dict[str, Any]:
        return {
            "status": status,
            "industry_name": None,
            "industry_code": None,
            "source": None,
            "period": period,
            "refreshed_at": None,
            "unavailable_reason": reason,
            "board_validation_status": None,
            "leader_companies": [],
            "metrics": {metric: self._metric_payload(None, None) for metric in self.METRICS},
        }

    def _metric_payload(self, company_value: float | None, benchmark: IndustryLeaderBenchmark | None) -> dict[str, Any]:
        leader_benchmark = self._finite(benchmark.leader_benchmark) if benchmark is not None else None
        sample_count = int(benchmark.sample_count or 0) if benchmark is not None else 0
        available = company_value is not None and leader_benchmark is not None and sample_count >= self.MIN_DISPLAY_SAMPLE
        gap = company_value - leader_benchmark if available else None
        return {
            "company_value": company_value,
            "leader_benchmark": leader_benchmark,
            "gap": gap,
            "gap_pct": gap / abs(leader_benchmark) if gap is not None and leader_benchmark else None,
            "sample_count": sample_count,
            "available": available,
        }

    def _latest_company_values(self, financials: list[FinancialIndicator], period_meta: dict[str, Any]) -> dict[str, float]:
        values: dict[str, float] = {}
        for item in financials:
            if item.report_period != period_meta["raw_period"] or item.period_type != period_meta["period_type"]:
                continue
            if item.indicator_code in self.METRICS and (number := self._finite(item.value)) is not None:
                values[item.indicator_code] = number
            if item.indicator_code == "net_profit" and (number := self._finite(item.value)) is not None:
                values["net_profit"] = number
        if "revenue_growth" not in values:
            growth = self._derive_revenue_growth(financials, period_meta)
            if growth is not None:
                values["revenue_growth"] = growth
        if "net_margin" not in values and values.get("revenue") not in (None, 0) and values.get("net_profit") is not None:
            values["net_margin"] = values["net_profit"] / abs(values["revenue"]) * 100.0
        return values

    def _derive_revenue_growth(self, financials: list[FinancialIndicator], period_meta: dict[str, Any]) -> float | None:
        current = self._metric_value(financials, period_meta, "revenue")
        previous = self._metric_value(
            financials,
            {
                "period_type": period_meta["period_type"],
                "year": int(period_meta["year"]) - 1,
                "quarter": period_meta["quarter"],
            },
            "revenue",
        )
        if current is None or previous in (None, 0):
            return None
        return (current - previous) / abs(previous) * 100.0

    def _metric_value(self, financials: list[FinancialIndicator], period_meta: dict[str, Any], code: str) -> float | None:
        for item in financials:
            if item.indicator_code != code or item.period_type != period_meta["period_type"]:
                continue
            if int(item.report_year) != int(period_meta["year"]):
                continue
            quarter = None if item.period_type == "annual" else item.report_quarter
            if quarter == period_meta.get("quarter"):
                return self._finite(item.value)
        return None

    def _latest_company_period(self, financials: list[FinancialIndicator]) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for item in financials:
            year = int(getattr(item, "report_year", 0) or 0)
            period_type = str(getattr(item, "period_type", "") or "")
            if year <= 0 or period_type not in {"annual", "quarterly"}:
                continue
            quarter = None if period_type == "annual" else getattr(item, "report_quarter", None) or self._quarter_from_raw_period(item.report_period)
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

    @staticmethod
    def _quarter_from_raw_period(report_period: str) -> int:
        text = str(report_period or "")
        month = int(text[4:6]) if len(text) >= 6 and text[4:6].isdigit() else 12
        return max(1, min(4, (month - 1) // 3 + 1))

    @staticmethod
    def _finite(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
