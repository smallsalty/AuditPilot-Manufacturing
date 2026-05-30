from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EnterpriseProfile, IndustryBenchmarkRefreshState, IndustryLeaderBenchmark, IndustryLeaderCompany


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoardValidation:
    status: str
    board_code: str | None = None


@dataclass
class PeerFinancialRecord:
    ticker: str
    name: str | None
    actual_period: str
    revenue: float | None = None
    previous_revenue: float | None = None
    operating_cost: float | None = None
    gross_profit: float | None = None
    net_profit: float | None = None
    expenses: float | None = None
    average_ar: float | None = None
    average_inventory: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None


class EastmoneyBoardValidationClient:
    HOSTS = ("17.push2.eastmoney.com", "29.push2.eastmoney.com", "push2.eastmoney.com")
    UT = "bd1d9ddb04089700cf9c27f6f7426281"

    def validate(self, industry_name: str, ticker: str) -> BoardValidation:
        had_response = False
        for host in self.HOSTS:
            try:
                boards = self._request_json(
                    host,
                    {
                        "pn": "1",
                        "pz": "1000",
                        "po": "1",
                        "np": "1",
                        "ut": self.UT,
                        "fltt": "2",
                        "invt": "2",
                        "fid": "f3",
                        "fs": "m:90 t:2 f:!50",
                        "fields": "f12,f14",
                    },
                )
                had_response = True
                board = next((item for item in boards if str(item.get("f14") or "").strip() == industry_name), None)
                if board is None:
                    continue
                board_code = str(board.get("f12") or "").strip() or None
                if board_code is None:
                    return BoardValidation(status="not_matched")
                members = self._request_json(
                    host,
                    {
                        "pn": "1",
                        "pz": "500",
                        "po": "1",
                        "np": "1",
                        "ut": self.UT,
                        "fltt": "2",
                        "invt": "2",
                        "fid": "f3",
                        "fs": f"b:{board_code} f:!50",
                        "fields": "f12,f14",
                    },
                )
                member_codes = {str(item.get("f12") or "").strip() for item in members}
                return BoardValidation(status="verified" if ticker in member_codes else "not_matched", board_code=board_code)
            except Exception:
                continue
        return BoardValidation(status="not_matched" if had_response else "unavailable")

    def _request_json(self, host: str, params: dict[str, str]) -> list[dict[str, Any]]:
        timeout = httpx.Timeout(5.0, connect=3.0)
        with httpx.Client(timeout=timeout, trust_env=False, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = client.get(f"https://{host}/api/qt/clist/get", params=params)
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("diff") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []


class IndustryBenchmarkRefreshService:
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
    SOURCE = "eastmoney_yjbb"
    LEADER_LIMIT = 5
    MIN_DISPLAY_SAMPLE = 3
    CANDIDATE_LIMIT = 15
    FETCH_BATCH_SIZE = 5

    def __init__(self, ak_module: Any | None = None, board_client: EastmoneyBoardValidationClient | None = None) -> None:
        self.ak_module = ak_module
        self.board_client = board_client or EastmoneyBoardValidationClient()

    def refresh(
        self,
        db: Session,
        *,
        enterprise_ids: Iterable[int] | None = None,
        period: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        enterprises = self._load_enterprises(db, enterprise_ids=enterprise_ids, limit=limit)
        summary: dict[str, Any] = {
            "enterprise_count": len(enterprises),
            "ready_count": 0,
            "failed_count": 0,
            "leader_count": 0,
            "benchmark_count": 0,
            "failures": [],
            "collection_log": [],
        }
        if not enterprises:
            return summary

        requested_period = period or self._default_period(enterprises)
        try:
            companies = self._load_yjbb_companies(self._akshare(), requested_period)
        except Exception as exc:
            logger.warning("industry benchmark yjbb load failed period=%s error=%s", requested_period, exc)
            for enterprise in enterprises:
                self._replace_state(
                    db,
                    enterprise=enterprise,
                    period=requested_period,
                    status="failed",
                    error_reason="eastmoney_yjbb_unavailable",
                )
                summary["failed_count"] += 1
                summary["failures"].append({"enterprise_id": enterprise.id, "error": "eastmoney_yjbb_unavailable"})
            db.commit()
            return summary

        for enterprise in enterprises:
            target_ticker = self._ticker_symbol(enterprise.ticker)
            target = next((company for company in companies if company["ticker"] == target_ticker), None)
            if target is None or not target.get("industry_name"):
                self._replace_state(
                    db,
                    enterprise=enterprise,
                    period=requested_period,
                    status="failed",
                    error_reason="target_industry_missing",
                )
                summary["failed_count"] += 1
                summary["failures"].append({"enterprise_id": enterprise.id, "error": "target_industry_missing"})
                continue

            industry_name = str(target["industry_name"])
            validation = self.board_client.validate(industry_name, target_ticker)
            candidates = self._rank_candidates(companies, industry_name=industry_name, target_ticker=target_ticker)
            leaders = self._fetch_leaders(self._akshare(), candidates, requested_period)
            collection = {
                "enterprise_id": enterprise.id,
                "ticker": target_ticker,
                "period": requested_period,
                "industry_name": industry_name,
                "candidate_count": len(candidates),
                "leader_count": len(leaders),
                "board_validation_status": validation.status,
                "status": "ready" if len(leaders) >= self.MIN_DISPLAY_SAMPLE else "failed",
            }
            summary["collection_log"].append(collection)
            logger.info("industry_benchmark_collection_status %s", collection)

            if len(leaders) < self.MIN_DISPLAY_SAMPLE:
                self._replace_state(
                    db,
                    enterprise=enterprise,
                    period=requested_period,
                    industry_name=industry_name,
                    board_code=validation.board_code,
                    board_validation_status=validation.status,
                    status="failed",
                    error_reason="insufficient_leader_sample",
                )
                summary["failed_count"] += 1
                summary["failures"].append({"enterprise_id": enterprise.id, "error": "insufficient_leader_sample"})
                continue

            benchmark_count = self._replace_industry_benchmark(db, industry_name=industry_name, period=requested_period, leaders=leaders)
            self._replace_state(
                db,
                enterprise=enterprise,
                period=requested_period,
                industry_name=industry_name,
                board_code=validation.board_code,
                board_validation_status=validation.status,
                status="ready",
            )
            summary["ready_count"] += 1
            summary["leader_count"] += len(leaders)
            summary["benchmark_count"] += benchmark_count

        db.commit()
        return summary

    def _load_yjbb_companies(self, ak_module: Any, period: str) -> list[dict[str, Any]]:
        df = ak_module.stock_yjbb_em(date=self._period_date(period))
        if df is None or getattr(df, "empty", True):
            return []
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        code_column = self._first_existing_column(normalized, ["股票代码", "SECURITY_CODE"])
        name_column = self._first_existing_column(normalized, ["股票简称", "SECURITY_NAME_ABBR"])
        industry_column = self._first_existing_column(normalized, ["所处行业", "BOARD_NAME"])
        revenue_column = self._first_existing_column(normalized, ["营业总收入-营业总收入", "TOTAL_OPERATE_INCOME"])
        profit_column = self._first_existing_column(normalized, ["净利润-净利润", "PARENT_NETPROFIT"])
        if not code_column or not industry_column:
            return []

        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _, item in normalized.iterrows():
            ticker = self._ticker_symbol(item.get(code_column))
            if not ticker or not ticker.startswith(("0", "3", "6")) or ticker in seen:
                continue
            seen.add(ticker)
            industry_name = self._clean_text(item.get(industry_column))
            if not industry_name:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": self._clean_text(item.get(name_column)) if name_column else None,
                    "industry_name": industry_name,
                    "revenue": self._coerce_number(item.get(revenue_column)) if revenue_column else None,
                    "net_profit": self._coerce_number(item.get(profit_column)) if profit_column else None,
                }
            )
        return rows

    def _rank_candidates(self, companies: list[dict[str, Any]], *, industry_name: str, target_ticker: str) -> list[dict[str, Any]]:
        candidates = [company for company in companies if company["industry_name"] == industry_name and company["ticker"] != target_ticker]

        def rank(company: dict[str, Any]) -> tuple[int, float, int, float, str]:
            revenue = self._finite(company.get("revenue"))
            net_profit = self._finite(company.get("net_profit"))
            return (
                0 if revenue is not None else 1,
                -(revenue or 0.0),
                0 if net_profit is not None else 1,
                -(net_profit or 0.0),
                str(company["ticker"]),
            )

        return sorted(candidates, key=rank)[: self.CANDIDATE_LIMIT]

    def _fetch_leaders(self, ak_module: Any, candidates: list[dict[str, Any]], period: str) -> list[PeerFinancialRecord]:
        leaders: list[PeerFinancialRecord] = []
        for start in range(0, len(candidates), self.FETCH_BATCH_SIZE):
            batch = candidates[start : start + self.FETCH_BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                records = list(executor.map(lambda company: self._fetch_peer_record(ak_module, company, period), batch))
            leaders.extend(record for record in records if record is not None)
            if len(leaders) >= self.LEADER_LIMIT:
                break
        return leaders[: self.LEADER_LIMIT]

    def _fetch_peer_record(self, ak_module: Any, company: dict[str, Any], period: str) -> PeerFinancialRecord | None:
        exchange_symbol = self._exchange_symbol(str(company["ticker"]))
        try:
            profit_df = ak_module.stock_profit_sheet_by_report_em(symbol=exchange_symbol)
            balance_df = ak_module.stock_balance_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return None
        profit_records = self._statement_records(profit_df)
        balance_records = self._statement_records(balance_df)
        profit_current = self._exact_period_record(profit_records, period)
        balance_current = self._exact_period_record(balance_records, period)
        if profit_current is None or balance_current is None:
            return None
        profit_previous_year = self._exact_period_record(profit_records, self._previous_year_period(period))
        balance_previous = self._previous_record(balance_records, period)
        revenue = self._first_number(profit_current, ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "TOTALOPERATEREVE"])
        cost = self._first_number(profit_current, ["OPERATE_COST", "TOTAL_OPERATE_COST"])
        gross_profit = self._first_number(profit_current, ["GROSS_PROFIT"])
        if gross_profit is None and revenue is not None and cost is not None:
            gross_profit = revenue - cost
        expenses = [
            self._first_number(profit_current, ["SALE_EXPENSE"]),
            self._first_number(profit_current, ["MANAGE_EXPENSE"]),
            self._first_number(profit_current, ["RESEARCH_EXPENSE", "ME_RESEARCH_EXPENSE"]),
            self._first_number(profit_current, ["FINANCE_EXPENSE"]),
        ]
        expense_total = sum(value for value in expenses if value is not None) if any(value is not None for value in expenses) else None
        return PeerFinancialRecord(
            ticker=str(company["ticker"]),
            name=self._clean_text(company.get("name")),
            actual_period=period,
            revenue=revenue,
            previous_revenue=self._first_number(profit_previous_year, ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "TOTALOPERATEREVE"]),
            operating_cost=cost,
            gross_profit=gross_profit,
            net_profit=self._first_number(profit_current, ["PARENT_NETPROFIT", "NETPROFIT"]),
            expenses=expense_total,
            average_ar=self._average_positive(
                self._first_number(balance_current, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"]),
                self._first_number(balance_previous, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"]),
            ),
            average_inventory=self._average_positive(
                self._first_number(balance_current, ["INVENTORY"]),
                self._first_number(balance_previous, ["INVENTORY"]),
            ),
            total_assets=self._first_number(balance_current, ["TOTAL_ASSETS"]),
            total_liabilities=self._first_number(balance_current, ["TOTAL_LIABILITIES"]),
        )

    def _replace_industry_benchmark(self, db: Session, *, industry_name: str, period: str, leaders: list[PeerFinancialRecord]) -> int:
        db.execute(delete(IndustryLeaderCompany).where(IndustryLeaderCompany.industry_name == industry_name, IndustryLeaderCompany.period == period))
        db.execute(delete(IndustryLeaderBenchmark).where(IndustryLeaderBenchmark.industry_name == industry_name, IndustryLeaderBenchmark.period == period))
        metrics_by_leader = [(record, self._record_metrics(record)) for record in leaders]
        for rank, (record, metrics) in enumerate(metrics_by_leader, start=1):
            db.add(
                IndustryLeaderCompany(
                    industry_name=industry_name,
                    period=period,
                    rank=rank,
                    ticker=record.ticker,
                    company_name=record.name,
                    revenue=record.revenue,
                    net_profit=record.net_profit,
                    metrics_json=metrics,
                    source=self.SOURCE,
                )
            )
        for metric in self.METRICS:
            values = [metrics[metric] for _, metrics in metrics_by_leader if metric in metrics]
            db.add(
                IndustryLeaderBenchmark(
                    industry_name=industry_name,
                    period=period,
                    metric_code=metric,
                    leader_benchmark=sum(values) / len(values) if len(values) >= self.MIN_DISPLAY_SAMPLE else None,
                    sample_count=len(values),
                    source=self.SOURCE,
                )
            )
        return len(self.METRICS)

    def _record_metrics(self, record: PeerFinancialRecord) -> dict[str, float]:
        metrics = {
            "revenue_growth": self._growth(record.revenue, record.previous_revenue),
            "gross_margin": self._percent(record.gross_profit, record.revenue),
            "net_margin": self._percent(record.net_profit, record.revenue),
            "revenue": self._finite(record.revenue),
            "ar_turnover": self._ratio(record.revenue, record.average_ar),
            "inventory_turnover": self._ratio(record.operating_cost, record.average_inventory),
            "debt_ratio": self._percent(record.total_liabilities, record.total_assets),
            "expense_ratio": self._percent(record.expenses, record.revenue),
        }
        return {metric: value for metric, value in metrics.items() if value is not None and math.isfinite(value)}

    def _replace_state(
        self,
        db: Session,
        *,
        enterprise: EnterpriseProfile,
        period: str,
        status: str,
        industry_name: str | None = None,
        board_code: str | None = None,
        board_validation_status: str | None = None,
        error_reason: str | None = None,
    ) -> None:
        db.execute(
            delete(IndustryBenchmarkRefreshState).where(
                IndustryBenchmarkRefreshState.enterprise_id == enterprise.id,
                IndustryBenchmarkRefreshState.period == period,
            )
        )
        db.add(
            IndustryBenchmarkRefreshState(
                enterprise_id=enterprise.id,
                ticker=self._ticker_symbol(enterprise.ticker),
                period=period,
                industry_name=industry_name,
                board_code=board_code,
                source=self.SOURCE,
                status=status,
                board_validation_status=board_validation_status,
                error_reason=error_reason,
                refreshed_at=datetime.now(timezone.utc),
            )
        )

    def _load_enterprises(self, db: Session, *, enterprise_ids: Iterable[int] | None, limit: int | None) -> list[EnterpriseProfile]:
        stmt = select(EnterpriseProfile).order_by(EnterpriseProfile.id)
        if enterprise_ids:
            stmt = stmt.where(EnterpriseProfile.id.in_(list(enterprise_ids)))
        if limit:
            stmt = stmt.limit(limit)
        return list(db.scalars(stmt).all())

    def _statement_records(self, df: Any) -> dict[str, Any]:
        if df is None or getattr(df, "empty", True):
            return {}
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME"])
        if not date_column:
            return {}
        records: dict[str, Any] = {}
        for _, item in normalized.iterrows():
            period = self._label_period(item.get(date_column))
            if period:
                records[period] = item
        return records

    @staticmethod
    def _exact_period_record(records: dict[str, Any], period: str) -> Any | None:
        return records.get(period)

    def _previous_record(self, records: dict[str, Any], period: str) -> Any | None:
        previous = [key for key in records if self._period_rank(key) < self._period_rank(period)]
        return records[max(previous, key=self._period_rank)] if previous else None

    @staticmethod
    def _first_existing_column(df: Any, candidates: list[str]) -> str | None:
        columns = set(getattr(df, "columns", []))
        return next((candidate for candidate in candidates if candidate in columns), None)

    @classmethod
    def _first_number(cls, record: Any | None, candidates: list[str]) -> float | None:
        if record is None:
            return None
        return next((number for candidate in candidates if (number := cls._coerce_number(record.get(candidate))) is not None), None)

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(str(value).strip().replace(",", ""))
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text and text.lower() not in {"nan", "none", "null", "--", "-"} else None

    @classmethod
    def _average_positive(cls, current: Any, previous: Any) -> float | None:
        values = [value for value in (cls._finite(current), cls._finite(previous)) if value is not None and value > 0]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _finite(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _ratio(cls, numerator: Any, denominator: Any) -> float | None:
        numerator_value = cls._finite(numerator)
        denominator_value = cls._finite(denominator)
        if numerator_value is None or denominator_value in (None, 0):
            return None
        return numerator_value / denominator_value

    @classmethod
    def _percent(cls, numerator: Any, denominator: Any) -> float | None:
        ratio = cls._ratio(numerator, denominator)
        return ratio * 100.0 if ratio is not None else None

    @classmethod
    def _growth(cls, current: Any, previous: Any) -> float | None:
        current_value = cls._finite(current)
        previous_value = cls._finite(previous)
        if current_value is None or previous_value in (None, 0):
            return None
        return ((current_value - previous_value) / abs(previous_value)) * 100.0

    @staticmethod
    def _ticker_symbol(value: Any) -> str:
        normalized = str(value or "").strip().upper().split(".", 1)[0].replace("SH", "").replace("SZ", "")
        digits = "".join(char for char in normalized if char.isdigit())
        return digits.zfill(6) if digits else ""

    @classmethod
    def _exchange_symbol(cls, ticker: str) -> str:
        symbol = cls._ticker_symbol(ticker)
        return f"{'SH' if symbol.startswith(('5', '6', '9')) else 'SZ'}{symbol}"

    @staticmethod
    def _period_date(period: str) -> str:
        text = str(period or "").upper()
        year = text[:4]
        if "Q1" in text:
            return f"{year}0331"
        if "Q2" in text:
            return f"{year}0630"
        if "Q3" in text:
            return f"{year}0930"
        return f"{year}1231"

    @staticmethod
    def _previous_year_period(period: str) -> str:
        text = str(period or "").upper()
        year = int(text[:4])
        return f"{year - 1}{text[4:]}"

    @staticmethod
    def _label_period(value: Any) -> str | None:
        try:
            import pandas as pd

            timestamp = pd.to_datetime(value)
        except Exception:
            return None
        if pd.isna(timestamp):
            return None
        month = int(timestamp.month)
        return f"{int(timestamp.year)}FY" if month == 12 else f"{int(timestamp.year)}Q{max(1, min(4, (month - 1) // 3 + 1))}"

    @staticmethod
    def _period_rank(period: str) -> int:
        text = str(period or "").upper()
        year = int(text[:4]) if text[:4].isdigit() else 0
        return year * 10 + (5 if "FY" in text else int(text.split("Q", 1)[1][:1]) if "Q" in text else 0)

    @staticmethod
    def _default_period(enterprises: list[EnterpriseProfile]) -> str:
        return f"{max(int(enterprise.report_year) for enterprise in enterprises)}FY"

    def _akshare(self) -> Any:
        if self.ak_module is not None:
            return self.ak_module
        if not settings.akshare_enable:
            raise RuntimeError("AkShare is disabled by settings.akshare_enable")
        import akshare as ak

        return ak
