from __future__ import annotations

from typing import Any

from app.ai.risk_agent_skill_registry import RiskAgentSkillRegistry


class FinancialDataRiskService:
    AGENT_SKILL = RiskAgentSkillRegistry.get("data_risk_analysis").key

    FIELD_MAPPING = {
        "revenue": "revenue",
        "net_profit": "net_profit",
        "gross_margin": "gross_margin",
        "net_margin": "net_margin",
        "ar_turnover": "ar_turnover",
        "inventory_turnover": "inventory_turnover",
        "debt_ratio": "debt_ratio",
        "operating_cash_flow": "ocf",
        "fixed_assets": "fixed_assets",
    }

    def evaluate_rows(
        self,
        rows: list[dict[str, Any]],
        industry_comparison: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        quarterly_rows = [row for row in rows if row.get("quarter") != "FY"]
        quarterly_rows.sort(key=self._row_sort_key)
        recent = quarterly_rows[-4:]

        risks: list[dict[str, Any]] = []
        if len(recent) >= 2:
            revenue_risk = self._revenue_volatility(recent)
            if revenue_risk:
                risks.append(revenue_risk)
            cash_risk = self._profit_cash_mismatch(recent)
            if cash_risk:
                risks.append(cash_risk)
            margin_risk = self._margin_decline(recent)
            if margin_risk:
                risks.append(margin_risk)
            leverage_risk = self._leverage_pressure(recent)
            if leverage_risk:
                risks.append(leverage_risk)
            fixed_asset_risk = self._fixed_asset_volatility(recent)
            if fixed_asset_risk:
                risks.append(fixed_asset_risk)

        industry_risk = self._industry_deviation(industry_comparison)
        if industry_risk:
            risks.append(industry_risk)
        return sorted(risks, key=lambda item: float(item["risk_score"]), reverse=True)

    def evaluate_indicators(
        self,
        financials: list[Any],
        industry_comparison: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in financials:
            if getattr(item, "period_type", None) == "annual":
                continue
            code = str(getattr(item, "indicator_code", "") or "")
            field_name = self.FIELD_MAPPING.get(code)
            if not field_name:
                continue
            year = int(getattr(item, "report_year", 0) or 0)
            quarter = getattr(item, "report_quarter", None) or self._quarter_from_period(getattr(item, "report_period", ""))
            label = f"{year}Q{quarter}"
            row = grouped.setdefault(
                label,
                {
                    "year": year,
                    "quarter": f"Q{quarter}",
                    "report_period": label,
                    "revenue": None,
                    "revenue_qoq": None,
                    "net_profit": None,
                    "gross_margin": None,
                    "net_margin": None,
                    "ar_turnover": None,
                    "inventory_turnover": None,
                    "debt_ratio": None,
                    "ocf": None,
                    "fixed_assets": None,
                },
            )
            row[field_name] = self._number(getattr(item, "value", None))
        rows = sorted(grouped.values(), key=self._row_sort_key)
        self.populate_revenue_qoq(rows)
        return self.evaluate_rows(rows, industry_comparison=industry_comparison)

    def max_score(self, risks: list[dict[str, Any]]) -> float:
        return max((float(risk.get("risk_score") or 0) for risk in risks), default=0.0)

    def populate_revenue_qoq(self, rows: list[dict[str, Any]]) -> None:
        rows.sort(key=self._row_sort_key)
        for index, row in enumerate(rows):
            previous = rows[index - 1] if index > 0 else None
            revenue = self._number(row.get("revenue"))
            previous_revenue = self._number(previous.get("revenue") if previous else None)
            row["revenue_qoq"] = (
                ((revenue - previous_revenue) / abs(previous_revenue)) * 100.0
                if revenue is not None and previous_revenue not in (None, 0)
                else row.get("revenue_qoq")
            )

    def _revenue_volatility(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = [
            (row, abs(float(row["revenue_qoq"])))
            for row in rows
            if self._number(row.get("revenue_qoq")) is not None and abs(float(row["revenue_qoq"])) >= 30
        ]
        if not candidates:
            return None
        row, max_abs = max(candidates, key=lambda item: item[1])
        score = min(100.0, 60.0 + (max_abs - 30.0) * 0.8)
        return self._risk(
            "FIN_DATA_REVENUE_VOLATILITY",
            "收入波动异常",
            score,
            f"{row['report_period']} 收入环比波动 {float(row['revenue_qoq']):+.2f}%。",
            rows,
        )

    def _profit_cash_mismatch(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        mismatches = [
            row
            for row in rows
            if self._number(row.get("net_profit")) is not None
            and self._number(row.get("ocf")) is not None
            and float(row["net_profit"]) > 0
            and float(row["ocf"]) < 0
        ]
        total_profit = sum(float(row["net_profit"]) for row in rows if self._number(row.get("net_profit")) is not None)
        total_ocf = sum(float(row["ocf"]) for row in rows if self._number(row.get("ocf")) is not None)
        ratio = total_ocf / total_profit if total_profit > 0 else None
        if not mismatches and (ratio is None or ratio >= 0.8):
            return None

        score = 75.0
        evidence = ""
        if mismatches:
            row = mismatches[-1]
            score = 82.0
            evidence = f"{row['report_period']} 净利为正但经营现金流为负。"
        if ratio is not None and ratio < 0.8:
            score = max(score, min(100.0, 75.0 + (0.8 - ratio) * 25.0))
            evidence = f"近4季经营现金流/净利为 {ratio:.2f}，低于 0.80。"
        return self._risk("FIN_DATA_PROFIT_CASH_MISMATCH", "利润现金错配", score, evidence, rows)

    def _margin_decline(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        first = rows[0]
        latest = rows[-1]
        gross_change = self._delta(latest.get("gross_margin"), first.get("gross_margin"))
        net_change = self._delta(latest.get("net_margin"), first.get("net_margin"))
        if (gross_change is None or gross_change > -5) and (net_change is None or net_change > -3):
            return None
        score = 65.0
        evidence_parts = []
        if gross_change is not None and gross_change <= -5:
            score = max(score, min(100.0, 65.0 + abs(gross_change + 5.0) * 3.0))
            evidence_parts.append(f"毛利率较近4季首期下降 {abs(gross_change):.2f} 个百分点")
        if net_change is not None and net_change <= -3:
            score = max(score, min(100.0, 65.0 + abs(net_change + 3.0) * 4.0))
            evidence_parts.append(f"净利率较近4季首期下降 {abs(net_change):.2f} 个百分点")
        return self._risk("FIN_DATA_MARGIN_DECLINE", "利润率下滑", score, "；".join(evidence_parts) + "。", rows)

    def _leverage_pressure(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        first = self._number(rows[0].get("debt_ratio"))
        latest = self._number(rows[-1].get("debt_ratio"))
        if latest is None:
            return None
        change = latest - first if first is not None else None
        if latest < 65 and (change is None or change < 5):
            return None
        score = 70.0
        evidence_parts = []
        if latest >= 65:
            score = max(score, min(100.0, 70.0 + (latest - 65.0) * 1.2))
            evidence_parts.append(f"最新资产负债率 {latest:.2f}%")
        if change is not None and change >= 5:
            score = max(score, min(100.0, 70.0 + (change - 5.0) * 2.0))
            evidence_parts.append(f"近4季上升 {change:.2f} 个百分点")
        return self._risk("FIN_DATA_LEVERAGE_PRESSURE", "杠杆压力", score, "；".join(evidence_parts) + "。", rows)

    def _fixed_asset_volatility(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        values = [self._number(row.get("fixed_assets")) for row in rows]
        values = [value for value in values if value is not None]
        if len(values) < 2 or values[0] == 0:
            return None
        ratio = (max(values) - min(values)) / abs(values[0])
        if ratio < 0.15:
            return None
        score = min(100.0, 60.0 + (ratio - 0.15) * 120.0)
        return self._risk(
            "FIN_DATA_FIXED_ASSET_VOLATILITY",
            "固定资产异常波动",
            score,
            f"近4季固定资产最大最小差/期初固定资产为 {ratio:.2%}。",
            rows,
        )

    def _industry_deviation(self, industry_comparison: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(industry_comparison, dict):
            return None

        hits: list[str] = []
        gross_margin = self._comparison_metric(industry_comparison, "gross_margin")
        if (
            self._metric_available(gross_margin)
            and self._gte(gross_margin.get("gap"), 8.0)
        ):
            hits.append(self._format_industry_hit("毛利率高于龙头基准", gross_margin, percent_gap=False))

        ar_turnover = self._comparison_metric(industry_comparison, "ar_turnover")
        if (
            self._metric_available(ar_turnover)
            and self._lte(ar_turnover.get("gap_pct"), -0.30)
        ):
            hits.append(self._format_industry_hit("应收账款周转率低于龙头基准", ar_turnover, percent_gap=True))

        debt_ratio = self._comparison_metric(industry_comparison, "debt_ratio")
        if (
            self._metric_available(debt_ratio)
            and self._gte(debt_ratio.get("gap"), 10.0)
        ):
            hits.append(self._format_industry_hit("资产负债率高于龙头基准", debt_ratio, percent_gap=False))

        if len(hits) < 2:
            return None

        period = str(industry_comparison.get("period") or "行业对比")
        score = 88.0 if len(hits) >= 3 else 78.0
        return self._risk(
            "FIN_DATA_INDUSTRY_DEVIATION",
            "行业对比偏离",
            score,
            "；".join(hits) + "。",
            [],
            periods=[period],
        )

    def _risk(
        self,
        rule_code: str,
        risk_name: str,
        score: float,
        evidence: str,
        rows: list[dict[str, Any]],
        *,
        periods: list[str] | None = None,
    ) -> dict[str, Any]:
        rounded_score = round(score, 2)
        return {
            "rule_code": rule_code,
            "risk_name": risk_name,
            "risk_level": self._risk_level(rounded_score),
            "risk_score": rounded_score,
            "judgment": f"{risk_name}：{self._risk_level(rounded_score)}风险",
            "evidence": evidence,
            "periods": periods if periods is not None else [str(row.get("report_period")) for row in rows],
            "agent_skill": self.AGENT_SKILL,
        }

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= 80:
            return "高"
        if score >= 60:
            return "中"
        return "低"

    @staticmethod
    def _risk_level_code(level: str) -> str:
        if level == "高":
            return "HIGH"
        if level == "中":
            return "MEDIUM"
        return "LOW"

    def result_level_code(self, risk: dict[str, Any]) -> str:
        return self._risk_level_code(str(risk.get("risk_level") or "低"))

    def _delta(self, current: Any, previous: Any) -> float | None:
        current_value = self._number(current)
        previous_value = self._number(previous)
        if current_value is None or previous_value is None:
            return None
        return current_value - previous_value

    def _comparison_metric(self, comparison: dict[str, Any], metric: str) -> dict[str, Any]:
        metrics = comparison.get("metrics")
        value = metrics.get(metric) if isinstance(metrics, dict) else None
        return value if isinstance(value, dict) else {}

    def _metric_available(self, metric: dict[str, Any]) -> bool:
        return bool(metric.get("available"))

    def _format_industry_hit(self, label: str, metric: dict[str, Any], *, percent_gap: bool) -> str:
        company_value = self._number(metric.get("company_value"))
        leader_benchmark = self._number(metric.get("leader_benchmark"))
        gap = self._number(metric.get("gap_pct" if percent_gap else "gap"))
        if gap is None:
            return label
        gap_text = f"{gap * 100:.2f}%" if percent_gap else f"{gap:.2f}个百分点"
        if company_value is None or leader_benchmark is None:
            return f"{label} {gap_text}"
        return f"{label} {gap_text}（公司 {company_value:.2f}，龙头基准 {leader_benchmark:.2f}）"

    def _gte(self, value: Any, threshold: float) -> bool:
        number = self._number(value)
        return number is not None and number >= threshold

    def _lte(self, value: Any, threshold: float) -> bool:
        number = self._number(value)
        return number is not None and number <= threshold

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _quarter_from_period(report_period: Any) -> int:
        text = str(report_period or "")
        month = int(text[4:6]) if len(text) >= 6 and text[4:6].isdigit() else 12
        return max(1, min(4, (month - 1) // 3 + 1))

    @staticmethod
    def _row_sort_key(row: dict[str, Any]) -> tuple[int, int]:
        quarter_order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}
        return int(row.get("year") or 0), quarter_order.get(str(row.get("quarter")), 0)
