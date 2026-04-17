from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.enterprise_repository import EnterpriseRepository


class TaxRiskService:
    EPSILON = 1e-6
    RULES = (
        "TAX_ETR_ABNORMAL",
        "TAX_CASHFLOW_MISMATCH",
        "DEFERRED_TAX_VOLATILITY",
        "TAX_PAYABLE_ACCRUAL",
    )
    RISK_DEFINITIONS = {
        "TAX_ETR_ABNORMAL": {
            "canonical_risk_key": "tax_effective_rate_anomaly",
            "risk_name": "企业所得税有效税率异常",
            "risk_category": "合规风险",
            "risk_level": "HIGH",
            "base_score": 88.0,
            "focus_accounts": ["所得税费用", "利润总额", "应交税费"],
            "focus_processes": ["所得税计提", "税务申报", "递延所得税复核"],
            "recommended_procedures": [
                "复核所得税费用计算底稿与纳税调整明细",
                "核对有效税率与法定税率差异的支持依据",
                "检查税收优惠、递延所得税和汇算清缴调整",
            ],
        },
        "TAX_CASHFLOW_MISMATCH": {
            "canonical_risk_key": "tax_cashflow_mismatch",
            "risk_name": "税费现金流匹配异常",
            "risk_category": "财务风险",
            "risk_level": "MEDIUM",
            "base_score": 76.0,
            "focus_accounts": ["支付各项税费的现金", "所得税费用", "税金及附加", "应交税费"],
            "focus_processes": ["税费支付", "现金流量编制", "税费截止测试"],
            "recommended_procedures": [
                "对税费支付现金与损益税费项目执行穿行复核",
                "检查应交税费变动与现金支付方向是否一致",
                "抽查纳税申报表、银行回单和总账勾稽关系",
            ],
        },
        "DEFERRED_TAX_VOLATILITY": {
            "canonical_risk_key": "deferred_tax_volatility",
            "risk_name": "递延所得税波动异常",
            "risk_category": "财务风险",
            "risk_level": "MEDIUM",
            "base_score": 74.0,
            "focus_accounts": ["递延所得税资产", "递延所得税负债", "资产总计"],
            "focus_processes": ["递延所得税确认", "会计估计复核", "税会差异复核"],
            "recommended_procedures": [
                "复核递延所得税资产和负债变动原因",
                "检查可抵扣暂时性差异和应纳税暂时性差异计算",
                "结合附注核对递延所得税调整与资产规模匹配关系",
            ],
        },
        "TAX_PAYABLE_ACCRUAL": {
            "canonical_risk_key": "tax_payable_accrual",
            "risk_name": "应交税费挂账异常",
            "risk_category": "合规风险",
            "risk_level": "HIGH",
            "base_score": 86.0,
            "focus_accounts": ["应交税费", "支付各项税费的现金", "所得税费用", "税金及附加", "营业收入"],
            "focus_processes": ["税费结转", "纳税申报", "负债截止测试"],
            "recommended_procedures": [
                "分析应交税费余额增长的具体税种与账龄",
                "核对税费支付、申报和结转是否存在跨期挂账",
                "结合收入增速判断应交税费增长是否具备经营支撑",
            ],
        },
    }

    def build_tax_risks(self, db: Session, enterprise_id: int) -> dict[str, Any]:
        enterprise_repo = EnterpriseRepository(db)
        enterprise = enterprise_repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        financials = enterprise_repo.get_financials(enterprise_id, official_only=True)
        period_rows = self._group_period_rows(financials)
        current_period, basis = self._select_basis_period(period_rows)
        diagnostics = {
            "evaluated_rules": [],
            "skipped_rules": [],
            "missing_indicators": [],
        }
        if current_period is None:
            return {
                "enterprise_id": enterprise_id,
                "as_of_period": None,
                "evaluation_basis": "latest_report",
                "diagnostics": diagnostics,
                "tax_risks": [],
            }

        current = period_rows[current_period]
        previous_period, previous = self._select_previous_period(period_rows, current_period, current)
        tax_risks: list[dict[str, Any]] = []

        for rule_code in self.RULES:
            result = getattr(self, f"_evaluate_{rule_code.lower()}")(current_period, current, previous_period, previous, period_rows)
            if result is None:
                diagnostics["evaluated_rules"].append(rule_code)
                continue
            if result.get("skipped"):
                diagnostics["skipped_rules"].append(
                    {
                        "rule_code": rule_code,
                        "reason": result["reason"],
                        "missing_indicators": result.get("missing_indicators", []),
                    }
                )
                diagnostics["missing_indicators"].extend(result.get("missing_indicators", []))
                continue
            diagnostics["evaluated_rules"].append(rule_code)
            tax_risks.append(result["risk"])

        diagnostics["missing_indicators"] = sorted(set(diagnostics["missing_indicators"]))
        return {
            "enterprise_id": enterprise_id,
            "as_of_period": current_period,
            "evaluation_basis": basis,
            "diagnostics": diagnostics,
            "tax_risks": tax_risks,
        }

    def _evaluate_tax_etr_abnormal(
        self,
        current_period: str,
        current: dict[str, Any],
        previous_period: str | None,
        previous: dict[str, Any] | None,
        period_rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        missing = self._missing(current, ["total_profit", "income_tax_expense"])
        if missing:
            return self._skip("缺少有效税率计算所需指标。", missing)

        total_profit = current["total_profit"]["value"]
        if total_profit <= self.EPSILON:
            return self._skip("利润总额小于等于 0，跳过有效税率规则。")

        etr = self._safe_divide(current["income_tax_expense"]["value"], total_profit)
        if etr is None:
            return self._skip("有效税率分母无效。")

        historical_rates = self._historical_metric(period_rows, "income_tax_expense", "total_profit", limit=3, exclude_period=current_period)
        history_median = median(historical_rates) if len(historical_rates) >= 2 else None
        deviation_to_statutory = abs(etr - 0.25)
        deviation_to_history = abs(etr - history_median) if history_median is not None else None
        out_of_range = etr < 0.10 or etr > 0.35
        history_trigger = deviation_to_statutory >= 0.10 and history_median is not None and deviation_to_history is not None and deviation_to_history >= 0.08
        if not (out_of_range or history_trigger):
            return None

        reasons = [f"本期有效税率为 {etr:.1%}，明显偏离法定税率 25%。"]
        if out_of_range:
            reasons.append("有效税率落入 10% 以下或 35% 以上的异常区间。")
        if history_trigger and history_median is not None and deviation_to_history is not None:
            reasons.append(f"与近三期中位数 {history_median:.1%} 的偏离达到 {deviation_to_history:.1%}。")

        metrics = [
            self._metric_item("effective_tax_rate", "有效税率", etr, "ratio", current_period),
            self._metric_item("income_tax_expense", "所得税费用", current["income_tax_expense"]["value"], current["income_tax_expense"].get("unit"), current_period),
            self._metric_item("total_profit", "利润总额", total_profit, current["total_profit"].get("unit"), current_period),
        ]
        if history_median is not None:
            metrics.append(self._metric_item("historical_etr_median", "近三期有效税率中位数", history_median, "ratio", current_period))

        return {
            "risk": self._build_risk(
                "TAX_ETR_ABNORMAL",
                current_period=current_period,
                reasons=reasons,
                summary=f"本期有效税率为 {etr:.1%}，与法定税率及历史水平存在显著偏离。",
                metrics=metrics,
                evidence_chain=[
                    self._evidence("有效税率测算", f"所得税费用 {current['income_tax_expense']['value']:.2f} / 利润总额 {total_profit:.2f} = {etr:.1%}", current_period),
                ],
            )
        }

    def _evaluate_tax_cashflow_mismatch(
        self,
        current_period: str,
        current: dict[str, Any],
        previous_period: str | None,
        previous: dict[str, Any] | None,
        period_rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        missing = self._missing(current, ["pay_all_tax_cash", "income_tax_expense", "operate_tax_surcharge"])
        if missing:
            return self._skip("缺少税费现金流匹配计算所需指标。", missing)

        nominal_tax = current["income_tax_expense"]["value"] + current["operate_tax_surcharge"]["value"]
        if abs(nominal_tax) <= self.EPSILON:
            return self._skip("名义税费合计接近 0，跳过税费现金流匹配规则。")

        paid_cash = current["pay_all_tax_cash"]["value"]
        ratio = self._safe_divide(paid_cash, nominal_tax)
        diff_ratio = self._safe_divide(abs(paid_cash - nominal_tax), abs(nominal_tax))
        if ratio is None or diff_ratio is None:
            return self._skip("税费现金流匹配分母无效。")

        if not ((ratio < 0.65 or ratio > 1.80) and diff_ratio >= 0.15):
            return None

        payable_direction_supported = True
        payable_delta = None
        if previous and "tax_payable" in current and "tax_payable" in previous:
            payable_delta = current["tax_payable"]["value"] - previous["tax_payable"]["value"]
            if ratio < 1:
                payable_direction_supported = payable_delta > 0
            elif ratio > 1:
                payable_direction_supported = payable_delta < 0
            if not payable_direction_supported:
                return None

        reasons = [
            f"本期支付各项税费现金为 {paid_cash:.2f}，与名义税费合计 {nominal_tax:.2f} 的匹配比为 {ratio:.2f}。",
            f"现金与名义税费差额占名义税费比例达到 {diff_ratio:.1%}。",
        ]
        if payable_delta is not None:
            reasons.append(f"应交税费同期变动为 {payable_delta:.2f}，与现金差异方向一致。")

        metrics = [
            self._metric_item("pay_all_tax_cash", "支付各项税费的现金", paid_cash, current["pay_all_tax_cash"].get("unit"), current_period),
            self._metric_item("nominal_tax_expense", "名义税费合计", nominal_tax, current["income_tax_expense"].get("unit"), current_period),
            self._metric_item("cash_match_ratio", "税费现金匹配比", ratio, "ratio", current_period),
            self._metric_item("tax_difference_ratio", "税费差额占比", diff_ratio, "ratio", current_period),
        ]
        if payable_delta is not None:
            metrics.append(self._metric_item("tax_payable_delta", "应交税费变动额", payable_delta, current["tax_payable"].get("unit"), current_period))

        return {
            "risk": self._build_risk(
                "TAX_CASHFLOW_MISMATCH",
                current_period=current_period,
                reasons=reasons,
                summary="税费现金支付与损益税费合计明显不匹配，需复核税费支付、截止和挂账处理。",
                metrics=metrics,
                evidence_chain=[
                    self._evidence("税费现金匹配测算", f"支付税费现金 {paid_cash:.2f} / 名义税费 {nominal_tax:.2f} = {ratio:.2f}", current_period),
                ],
            )
        }

    def _evaluate_deferred_tax_volatility(
        self,
        current_period: str,
        current: dict[str, Any],
        previous_period: str | None,
        previous: dict[str, Any] | None,
        period_rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        missing = self._missing(current, ["deferred_tax_asset", "deferred_tax_liability", "total_assets"])
        if missing:
            return self._skip("缺少递延所得税波动计算所需指标。", missing)
        if previous is None:
            return self._skip("缺少可比期间，跳过递延所得税波动规则。")
        previous_missing = self._missing(previous, ["deferred_tax_asset", "deferred_tax_liability"])
        if previous_missing:
            return self._skip("上期缺少递延所得税对比指标。", previous_missing)

        net_current = current["deferred_tax_asset"]["value"] - current["deferred_tax_liability"]["value"]
        net_previous = previous["deferred_tax_asset"]["value"] - previous["deferred_tax_liability"]["value"]
        delta = net_current - net_previous
        assets = current["total_assets"]["value"]
        if abs(assets) <= self.EPSILON or abs(net_previous) <= self.EPSILON:
            return self._skip("递延所得税波动规则缺少有效基线。")

        assets_ratio = self._safe_divide(abs(delta), abs(assets))
        change_ratio = self._safe_divide(abs(delta), abs(net_previous))
        if assets_ratio is None or change_ratio is None:
            return self._skip("递延所得税波动规则分母无效。")
        if not (assets_ratio >= 0.01 and change_ratio >= 0.50):
            return None

        reasons = [
            f"净递延所得税由 {net_previous:.2f} 变动至 {net_current:.2f}，变动额 {delta:.2f}。",
            f"变动额占总资产比例 {assets_ratio:.2%}，相对上期波动幅度 {change_ratio:.1%}。",
        ]
        metrics = [
            self._metric_item("net_deferred_tax", "净递延所得税", net_current, current["deferred_tax_asset"].get("unit"), current_period),
            self._metric_item("prev_net_deferred_tax", "上期净递延所得税", net_previous, previous["deferred_tax_asset"].get("unit"), previous_period or current_period),
            self._metric_item("net_deferred_tax_delta", "净递延所得税变动额", delta, current["deferred_tax_asset"].get("unit"), current_period),
            self._metric_item("deferred_tax_delta_assets_ratio", "递延所得税变动占总资产比", assets_ratio, "ratio", current_period),
            self._metric_item("deferred_tax_delta_change_ratio", "递延所得税相对波动幅度", change_ratio, "ratio", current_period),
        ]
        if "deferred_tax_cash_adjustment" in current:
            metrics.append(
                self._metric_item(
                    "deferred_tax_cash_adjustment",
                    "递延所得税调整",
                    current["deferred_tax_cash_adjustment"]["value"],
                    current["deferred_tax_cash_adjustment"].get("unit"),
                    current_period,
                )
            )

        return {
            "risk": self._build_risk(
                "DEFERRED_TAX_VOLATILITY",
                current_period=current_period,
                reasons=reasons,
                summary="递延所得税净额波动显著，需复核暂时性差异、确认依据和税会差异处理。",
                metrics=metrics,
                evidence_chain=[
                    self._evidence("净递延所得税波动", f"本期净递延所得税 {net_current:.2f}，上期 {net_previous:.2f}，变动 {delta:.2f}", current_period),
                ],
            )
        }

    def _evaluate_tax_payable_accrual(
        self,
        current_period: str,
        current: dict[str, Any],
        previous_period: str | None,
        previous: dict[str, Any] | None,
        period_rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        missing = self._missing(current, ["tax_payable", "pay_all_tax_cash", "income_tax_expense", "operate_tax_surcharge", "revenue"])
        if missing:
            return self._skip("缺少应交税费挂账规则所需指标。", missing)
        if previous is None:
            return self._skip("缺少可比期间，跳过应交税费挂账规则。")
        previous_missing = self._missing(previous, ["tax_payable", "revenue"])
        if previous_missing:
            return self._skip("上期缺少应交税费或收入数据。", previous_missing)

        payable_growth = self._growth_rate(current["tax_payable"]["value"], previous["tax_payable"]["value"])
        revenue_growth = self._growth_rate(current["revenue"]["value"], previous["revenue"]["value"])
        nominal_tax = current["income_tax_expense"]["value"] + current["operate_tax_surcharge"]["value"]
        if payable_growth is None or revenue_growth is None:
            return self._skip("应交税费挂账规则缺少有效同比基线。")
        if nominal_tax <= self.EPSILON:
            return self._skip("名义税费合计接近 0，跳过应交税费挂账规则。")

        cash_paid = current["pay_all_tax_cash"]["value"]
        if not (payable_growth >= 0.30 and cash_paid < 0.8 * nominal_tax and revenue_growth < 0.20):
            return None

        reasons = [
            f"应交税费同比增长 {payable_growth:.1%}，达到挂账异常阈值。",
            f"本期支付税费现金 {cash_paid:.2f}，低于名义税费合计 {nominal_tax:.2f} 的 80%。",
            f"营业收入同比增长 {revenue_growth:.1%}，不足以解释应交税费大幅增长。",
        ]
        metrics = [
            self._metric_item("tax_payable_growth_rate", "应交税费同比增速", payable_growth, "ratio", current_period),
            self._metric_item("revenue_growth_rate", "营业收入同比增速", revenue_growth, "ratio", current_period),
            self._metric_item("pay_all_tax_cash", "支付各项税费的现金", cash_paid, current["pay_all_tax_cash"].get("unit"), current_period),
            self._metric_item("nominal_tax_expense", "名义税费合计", nominal_tax, current["income_tax_expense"].get("unit"), current_period),
        ]

        return {
            "risk": self._build_risk(
                "TAX_PAYABLE_ACCRUAL",
                current_period=current_period,
                reasons=reasons,
                summary="应交税费增速显著高于经营增速，且税费现金支付不足，存在挂账或跨期确认风险。",
                metrics=metrics,
                evidence_chain=[
                    self._evidence("应交税费挂账测算", f"应交税费同比 {payable_growth:.1%}，税费现金支付覆盖率 {cash_paid / nominal_tax:.2f}", current_period),
                ],
            )
        }

    def _group_period_rows(self, financials: list[Any]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = defaultdict(dict)
        for item in financials:
            grouped[item.report_period][item.indicator_code] = {
                "value": float(item.value),
                "unit": item.unit,
                "period_type": item.period_type,
                "report_year": item.report_year,
                "report_quarter": item.report_quarter,
                "report_period": item.report_period,
            }
        return dict(grouped)

    def _select_basis_period(self, period_rows: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
        if not period_rows:
            return None, "latest_report"
        annual_periods = [period for period, row in period_rows.items() if any(item.get("period_type") == "annual" for item in row.values())]
        if annual_periods:
            return sorted(annual_periods)[-1], "latest_annual"
        return sorted(period_rows)[-1], "latest_report"

    def _select_previous_period(
        self,
        period_rows: dict[str, dict[str, Any]],
        current_period: str,
        current: dict[str, Any],
    ) -> tuple[str | None, dict[str, Any] | None]:
        current_year = next((item.get("report_year") for item in current.values()), None)
        current_quarter = next((item.get("report_quarter") for item in current.values() if item.get("report_quarter")), None)
        current_period_type = next((item.get("period_type") for item in current.values()), None)

        candidates = []
        for period, row in period_rows.items():
            if period >= current_period:
                continue
            year = next((item.get("report_year") for item in row.values()), None)
            quarter = next((item.get("report_quarter") for item in row.values() if item.get("report_quarter")), None)
            period_type = next((item.get("period_type") for item in row.values()), None)
            if current_period_type == "annual":
                if period_type == "annual":
                    candidates.append((period, row))
            else:
                if year == (current_year - 1 if current_year else None) and quarter == current_quarter:
                    return period, row
                if quarter == current_quarter:
                    candidates.append((period, row))
        if candidates:
            period, row = sorted(candidates, key=lambda item: item[0])[-1]
            return period, row
        earlier = sorted((period, row) for period, row in period_rows.items() if period < current_period)
        if not earlier:
            return None, None
        period, row = earlier[-1]
        return period, row

    def _historical_metric(
        self,
        period_rows: dict[str, dict[str, Any]],
        numerator_code: str,
        denominator_code: str,
        *,
        limit: int,
        exclude_period: str | None = None,
    ) -> list[float]:
        values: list[float] = []
        periods = [period for period in sorted(period_rows) if period != exclude_period]
        for period in periods[-limit:]:
            row = period_rows[period]
            if numerator_code not in row or denominator_code not in row:
                continue
            value = self._safe_divide(row[numerator_code]["value"], row[denominator_code]["value"])
            if value is None:
                continue
            values.append(value)
        return values

    def _safe_divide(self, numerator: float, denominator: float) -> float | None:
        if denominator is None or abs(float(denominator)) <= self.EPSILON:
            return None
        return float(numerator) / float(denominator)

    def _growth_rate(self, current: float, previous: float) -> float | None:
        if previous is None or abs(float(previous)) <= self.EPSILON:
            return None
        return (float(current) - float(previous)) / abs(float(previous))

    def _missing(self, row: dict[str, Any], indicator_codes: list[str]) -> list[str]:
        return [indicator for indicator in indicator_codes if indicator not in row]

    def _skip(self, reason: str, missing_indicators: list[str] | None = None) -> dict[str, Any]:
        return {"skipped": True, "reason": reason, "missing_indicators": missing_indicators or []}

    def _metric_item(self, metric_code: str, metric_name: str, value: float, unit: str | None, report_period: str) -> dict[str, Any]:
        return {
            "metric_code": metric_code,
            "metric_name": metric_name,
            "value": round(float(value), 6),
            "unit": unit,
            "report_period": report_period,
        }

    def _evidence(self, title: str, content: str, report_period: str) -> dict[str, Any]:
        return {
            "type": "metric",
            "title": title,
            "content": content,
            "source": "financial_indicator",
            "report_period": report_period,
        }

    def _build_risk(
        self,
        rule_code: str,
        *,
        current_period: str,
        reasons: list[str],
        summary: str,
        metrics: list[dict[str, Any]],
        evidence_chain: list[dict[str, Any]],
    ) -> dict[str, Any]:
        definition = self.RISK_DEFINITIONS[rule_code]
        return {
            "rule_code": rule_code,
            "canonical_risk_key": definition["canonical_risk_key"],
            "risk_name": definition["risk_name"],
            "risk_category": definition["risk_category"],
            "risk_level": definition["risk_level"],
            "risk_score": definition["base_score"],
            "summary": summary,
            "reasons": reasons,
            "report_period": current_period,
            "period_type": "annual" if current_period.endswith("1231") else "quarterly",
            "metrics": metrics,
            "evidence_chain": evidence_chain,
            "focus_accounts": definition["focus_accounts"],
            "focus_processes": definition["focus_processes"],
            "recommended_procedures": definition["recommended_procedures"],
        }
