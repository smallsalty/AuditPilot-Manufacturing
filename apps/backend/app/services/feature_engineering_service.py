from collections import defaultdict

import pandas as pd

from app.models import ExternalEvent, FinancialIndicator, IndustryBenchmark


class FeatureEngineeringService:
    def build_features(
        self,
        financials: list[FinancialIndicator],
        events: list[ExternalEvent],
        industry_benchmarks: list[IndustryBenchmark],
    ) -> dict[str, float]:
        rows = [
            {
                "period_type": item.period_type,
                "report_period": item.report_period,
                "report_year": item.report_year,
                "report_quarter": item.report_quarter,
                "indicator_code": item.indicator_code,
                "value": item.value,
            }
            for item in financials
        ]
        if not rows:
            return {}
        df = pd.DataFrame(rows)
        annual_df = df[df["period_type"] == "annual"]
        quarterly_df = df[df["period_type"] == "quarterly"]
        features: dict[str, float] = {}

        latest_year = int(annual_df["report_year"].max()) if not annual_df.empty else int(df["report_year"].max())
        prev_year = latest_year - 1

        def metric(year: int, code: str, period_type: str = "annual") -> float | None:
            subset = df[
                (df["report_year"] == year)
                & (df["indicator_code"] == code)
                & (df["period_type"] == period_type)
            ]
            if subset.empty:
                return None
            return float(subset.iloc[0]["value"])

        def growth(code: str) -> float:
            current = metric(latest_year, code)
            previous = metric(prev_year, code)
            if current is None or previous in (None, 0):
                return 0.0
            return (current - previous) / abs(previous)

        def delta(code: str) -> float:
            current = metric(latest_year, code)
            previous = metric(prev_year, code)
            if current is None or previous is None:
                return 0.0
            return current - previous

        features["latest_year"] = float(latest_year)
        features["revenue_growth_rate"] = growth("revenue")
        features["net_profit_growth_rate"] = growth("net_profit")
        features["inventory_growth_rate"] = growth("inventory")
        features["accounts_receivable_growth_rate"] = growth("accounts_receivable")
        features["inventory_turnover_delta"] = delta("inventory_turnover")
        features["ar_turnover_delta"] = delta("ar_turnover")
        features["gross_margin_volatility"] = abs(delta("gross_margin"))
        features["debt_ratio_delta"] = delta("debt_ratio")
        features["expense_ratio_delta"] = delta("expense_ratio")
        latest_profit = metric(latest_year, "net_profit") or 0.0
        latest_ocf = metric(latest_year, "operating_cash_flow") or 0.0
        features["operating_cf_profit_ratio"] = latest_ocf / latest_profit if latest_profit else 0.0
        features["ar_revenue_growth_gap"] = (
            features["accounts_receivable_growth_rate"] - features["revenue_growth_rate"]
        )
        features["inventory_revenue_growth_gap"] = features["inventory_growth_rate"] - features["revenue_growth_rate"]

        if not quarterly_df.empty:
            latest_q_year = int(quarterly_df["report_year"].max())
            revenue_rows = quarterly_df[
                (quarterly_df["report_year"] == latest_q_year) & (quarterly_df["indicator_code"] == "revenue")
            ]
            q_map = {int(row.report_quarter): float(row.value) for row in revenue_rows.itertuples()}
            total = sum(q_map.values()) or 1.0
            features["q4_revenue_ratio"] = q_map.get(4, 0.0) / total
        else:
            features["q4_revenue_ratio"] = 0.0

        annual_profit_series = defaultdict(float)
        annual_ocf_series = defaultdict(float)
        for row in annual_df.itertuples():
            if row.indicator_code == "net_profit":
                annual_profit_series[int(row.report_year)] = float(row.value)
            if row.indicator_code == "operating_cash_flow":
                annual_ocf_series[int(row.report_year)] = float(row.value)

        years_desc = sorted(annual_profit_series.keys(), reverse=True)
        features["consecutive_losses"] = 0.0
        for year in years_desc:
            if annual_profit_series.get(year, 0.0) < 0:
                features["consecutive_losses"] += 1.0
            else:
                break

        features["operating_cf_negative_streak"] = 0.0
        for year in years_desc:
            if annual_ocf_series.get(year, 0.0) < 0:
                features["operating_cf_negative_streak"] += 1.0
            else:
                break

        features["short_term_debt_pressure"] = 1.0 if (metric(latest_year, "debt_ratio") or 0) >= 65 else 0.0

        event_counts = defaultdict(int)
        for event in events:
            event_counts[event.event_type] += 1
        features["major_litigation_count"] = float(event_counts["litigation"])
        features["penalty_count"] = float(event_counts["penalty"])
        features["negative_sentiment_count"] = float(event_counts["negative_news"])
        features["executive_change_count"] = float(event_counts["executive_change"])
        features["related_party_complexity_score"] = float(event_counts["related_party"])

        demand_index = 0.0
        for benchmark in industry_benchmarks:
            if benchmark.metric_code == "demand_index_yoy":
                demand_index = benchmark.value
        features["industry_demand_down_inventory_up"] = (
            1.0 if demand_index < 0 and features["inventory_growth_rate"] > 0 else 0.0
        )
        return features

