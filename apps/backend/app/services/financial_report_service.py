from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import FinancialIndicator
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.ingestion_service import IngestionService


class FinancialReportService:
    FIELD_MAPPING = {
        "revenue": "revenue",
        "net_profit": "net_profit",
        "deduct_net_profit": "deduct_net_profit",
        "gross_margin": "gross_margin",
        "net_margin": "net_margin",
        "debt_ratio": "debt_ratio",
        "operating_cash_flow": "ocf",
        "roe": "roe",
        "eps": "eps",
    }

    SNAPSHOT_FIELDS = (
        "revenue",
        "net_profit",
        "deduct_net_profit",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "ocf",
        "roe",
        "eps",
    )

    def __init__(self) -> None:
        self.enterprise_repo = EnterpriseRepository
        self.ingestion_service = IngestionService()

    def build_report(
        self,
        db: Session,
        enterprise_id: int,
        *,
        refresh: bool = False,
        include_quarterly: bool = True,
    ) -> dict[str, Any]:
        repo = self.enterprise_repo(db)
        enterprise = repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

        financials = repo.get_financials(enterprise_id, official_only=True)
        refresh_error: str | None = None
        stale = False

        if self._should_refresh(enterprise.report_year, financials, refresh=refresh):
            try:
                # Always persist the full quarterly set to avoid destructive partial refreshes.
                self.ingestion_service.ingest_financials(
                    db,
                    enterprise,
                    provider_name="akshare",
                    include_quarterly=True,
                    force_seed_fallback=False,
                )
                financials = repo.get_financials(enterprise_id, official_only=True)
            except Exception as exc:
                refresh_error = str(exc)
                if not financials:
                    raise ValueError(
                        "当前企业尚未获取到可用的官方财务数据，请先同步或检查 AkShare 数据源。"
                    ) from exc
                stale = True

        if not financials:
            raise ValueError("当前企业尚未获取到可用的官方财务数据，请先同步或检查 AkShare 数据源。")

        filtered_financials = self._filter_financials(financials, include_quarterly=include_quarterly)
        if not filtered_financials:
            raise ValueError("当前筛选条件下暂无可用财务数据。")

        documents = repo.get_documents(enterprise_id, official_only=True)
        document_periods = self._collect_document_periods(documents)
        rows = self._build_rows(filtered_financials, document_periods)
        rows_desc = sorted(rows, key=self._row_sort_key, reverse=True)
        rows_asc = list(reversed(rows_desc))
        latest_row = rows_desc[0]
        updated_at = self._resolve_updated_at(filtered_financials, documents)
        latest_period = latest_row["report_period"]
        period_range = {
            "start": rows_asc[0]["report_period"] if rows_asc else None,
            "end": rows_asc[-1]["report_period"] if rows_asc else None,
        }

        has_document_context = bool(documents)
        return {
            "enterprise_id": enterprise.id,
            "company_name": enterprise.name,
            "ticker": enterprise.ticker,
            "data_source": "AkShare + 巨潮资讯文档提取" if has_document_context else "AkShare",
            "period_range": period_range,
            "updated_at": updated_at,
            "stale": stale,
            "refresh_error": refresh_error,
            "latest_period": latest_period,
            "latest_metrics": self._build_latest_metrics(latest_row),
            "rows": rows_desc,
            "summaries": self._build_summaries(rows_desc),
        }

    def _should_refresh(
        self,
        report_year: int,
        financials: list[FinancialIndicator],
        *,
        refresh: bool,
    ) -> bool:
        if refresh or not financials:
            return True
        latest_year = max((int(item.report_year) for item in financials), default=0)
        return latest_year < int(report_year)

    def _filter_financials(
        self,
        financials: list[FinancialIndicator],
        *,
        include_quarterly: bool,
    ) -> list[FinancialIndicator]:
        if include_quarterly:
            return financials
        return [item for item in financials if item.period_type == "annual"]

    def _build_rows(
        self,
        financials: list[FinancialIndicator],
        document_periods: set[str],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in financials:
            label = self._period_label(item.report_year, item.report_quarter, item.period_type, item.report_period)
            row = grouped.setdefault(
                label,
                {
                    "year": int(item.report_year),
                    "quarter": self._quarter_label(item.report_quarter, item.period_type, item.report_period),
                    "report_period": label,
                    "revenue": None,
                    "revenue_yoy": None,
                    "revenue_qoq": None,
                    "net_profit": None,
                    "deduct_net_profit": None,
                    "gross_margin": None,
                    "net_margin": None,
                    "debt_ratio": None,
                    "ocf": None,
                    "roe": None,
                    "eps": None,
                    "source": "AkShare + CNINFO" if label in document_periods else "AkShare",
                },
            )
            field_name = self.FIELD_MAPPING.get(item.indicator_code)
            if field_name:
                row[field_name] = float(item.value)

        rows = list(grouped.values())
        rows.sort(key=self._row_sort_key)
        self._populate_growth_fields(rows)
        return rows

    def _populate_growth_fields(self, rows_asc: list[dict[str, Any]]) -> None:
        for index, row in enumerate(rows_asc):
            previous_row = rows_asc[index - 1] if index > 0 else None
            yoy_row = self._find_yoy_row(rows_asc, row)

            revenue = self._number(row.get("revenue"))
            previous_revenue = self._number(previous_row.get("revenue") if previous_row else None)
            yoy_revenue = self._number(yoy_row.get("revenue") if yoy_row else None)

            if row["quarter"] != "FY" and revenue is not None and previous_revenue not in (None, 0):
                row["revenue_qoq"] = self._growth_rate(revenue, previous_revenue)
            else:
                row["revenue_qoq"] = None

            if revenue is not None and yoy_revenue not in (None, 0):
                row["revenue_yoy"] = self._growth_rate(revenue, yoy_revenue)
            else:
                row["revenue_yoy"] = None

    def _find_yoy_row(
        self,
        rows_asc: list[dict[str, Any]],
        row: dict[str, Any],
    ) -> dict[str, Any] | None:
        target_year = int(row["year"]) - 1
        target_quarter = row["quarter"]
        for candidate in rows_asc:
            if candidate["year"] == target_year and candidate["quarter"] == target_quarter:
                return candidate
        return None

    def _build_latest_metrics(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {"report_period": row["report_period"]}
        for field_name in self.SNAPSHOT_FIELDS:
            payload[field_name] = row.get(field_name)
        return payload

    def _build_summaries(self, rows_desc: list[dict[str, Any]]) -> list[dict[str, str]]:
        latest = rows_desc[0]
        previous = rows_desc[1] if len(rows_desc) > 1 else None
        items: list[str] = []

        revenue = self._number(latest.get("revenue"))
        if revenue is not None:
            items.append(
                f"{latest['report_period']}营业收入为{self._format_money(revenue)}，同比{self._format_change(latest.get('revenue_yoy'))}。"
            )

        latest_profit = self._number(latest.get("net_profit"))
        previous_profit = self._number(previous.get("net_profit") if previous else None)
        if latest_profit is not None and previous_profit is not None:
            direction = "改善" if latest_profit >= previous_profit else "下滑"
            items.append(
                f"归母净利润较{previous['report_period']}{direction}，变动额为{self._format_money(latest_profit - previous_profit)}。"
            )

        latest_ocf = self._number(latest.get("ocf"))
        if latest_ocf is not None and latest_profit is not None:
            same_direction = latest_ocf >= 0 and latest_profit >= 0
            items.append(
                f"经营现金流为{self._format_money(latest_ocf)}，与利润方向{'一致' if same_direction else '不一致'}。"
            )

        margin_summary = self._trend_summary("毛利率", latest.get("gross_margin"), previous.get("gross_margin") if previous else None)
        if margin_summary:
            items.append(margin_summary)

        debt_summary = self._trend_summary("资产负债率", latest.get("debt_ratio"), previous.get("debt_ratio") if previous else None)
        if debt_summary:
            items.append(debt_summary)

        return [{"text": text} for text in items[:5]]

    def _trend_summary(self, label: str, current: Any, previous: Any) -> str | None:
        current_value = self._number(current)
        previous_value = self._number(previous)
        if current_value is None or previous_value is None:
            return None
        if current_value == previous_value:
            return f"{label}与上一期持平。"
        direction = "上升" if current_value > previous_value else "下降"
        return f"{label}较上一期{direction}{abs(current_value - previous_value):.2f}个百分点。"

    def _resolve_updated_at(self, financials: list[FinancialIndicator], documents: list[Any]) -> str | None:
        latest: datetime | None = None
        for item in financials:
            for candidate in (getattr(item, "updated_at", None), getattr(item, "created_at", None)):
                if isinstance(candidate, datetime) and (latest is None or candidate > latest):
                    latest = candidate
        for document in documents:
            for candidate in (
                getattr(document, "updated_at", None),
                getattr(document, "created_at", None),
                getattr(document, "ingestion_time", None),
            ):
                if isinstance(candidate, datetime) and (latest is None or candidate > latest):
                    latest = candidate
        return latest.isoformat() if latest else None

    def _collect_document_periods(self, documents: list[Any]) -> set[str]:
        periods: set[str] = set()
        for document in documents:
            period = self._normalize_document_period(
                getattr(document, "report_period_label", None),
                getattr(document, "fiscal_year", None),
                getattr(document, "document_name", None),
            )
            if period:
                periods.add(period)
        return periods

    def _normalize_document_period(
        self,
        label: Any,
        fiscal_year: Any,
        document_name: Any,
    ) -> str | None:
        text = str(label or document_name or "").strip()
        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else (int(fiscal_year) if fiscal_year else None)
        if year is None:
            return None
        normalized = text.replace(" ", "").upper()
        if "Q1" in normalized or "一季" in text or "第一季度" in text:
            return f"{year}Q1"
        if "Q2" in normalized or "半年" in text or "中报" in text or "半年度" in text or "第二季度" in text:
            return f"{year}Q2"
        if "Q3" in normalized or "三季" in text or "第三季度" in text:
            return f"{year}Q3"
        if "FY" in normalized or "年度" in text or "年报" in text:
            return f"{year}FY"
        return None

    def _period_label(
        self,
        report_year: int,
        report_quarter: int | None,
        period_type: str,
        report_period: str,
    ) -> str:
        if period_type == "annual":
            return f"{int(report_year)}FY"
        quarter = report_quarter or self._quarter_from_raw_period(report_period)
        return f"{int(report_year)}Q{quarter}"

    def _quarter_label(self, report_quarter: int | None, period_type: str, report_period: str) -> str:
        if period_type == "annual":
            return "FY"
        quarter = report_quarter or self._quarter_from_raw_period(report_period)
        return f"Q{quarter}"

    def _quarter_from_raw_period(self, report_period: str) -> int:
        month = int(str(report_period)[4:6]) if len(str(report_period)) >= 6 else 12
        return max(1, min(4, (month - 1) // 3 + 1))

    def _row_sort_key(self, row: dict[str, Any]) -> tuple[int, int]:
        quarter_order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}
        return int(row["year"]), quarter_order.get(str(row["quarter"]), 0)

    def _growth_rate(self, current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return ((current - previous) / abs(previous)) * 100.0

    def _number(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _format_money(self, value: float) -> str:
        absolute = abs(value)
        if absolute >= 100000000:
            return f"{value / 100000000:.2f}亿元"
        if absolute >= 10000:
            return f"{value / 10000:.2f}万元"
        return f"{value:.2f}元"

    def _format_change(self, value: Any) -> str:
        number = self._number(value)
        if number is None:
            return "--"
        return f"{number:+.2f}%"
