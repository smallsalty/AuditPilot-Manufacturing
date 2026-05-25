from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CompanyIndustryMapping, EnterpriseProfile, IndustryBenchmarkSnapshot, IndustrySamplePool
from app.services.industry_taxonomy_service import IndustryReference, IndustryTaxonomyService


logger = logging.getLogger(__name__)


@dataclass
class PeerFinancialRecord:
    ticker: str
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
    name: str | None = None


@dataclass
class MetricSample:
    ticker: str
    value: float
    actual_period: str
    numerator: float | None = None
    denominator: float | None = None
    sample_name: str | None = None


@dataclass
class CompanyIndustryMappingRecord:
    ticker: str
    company_name: str | None
    source: str
    standard: str
    industry_code: str | None
    industry_name: str
    industry_level: str | None = None
    effective_date: date | None = None
    raw_payload: dict[str, Any] | None = None


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
    MIN_DISPLAY_SAMPLE = 5
    PEER_LIMIT = 80
    WEIGHTED_METRICS = {
        "revenue_growth",
        "gross_margin",
        "net_margin",
        "ar_turnover",
        "inventory_turnover",
        "debt_ratio",
        "expense_ratio",
    }
    CNINFO_BROAD_STANDARD_CODES = {"008001", "008002"}
    CNINFO_PEER_SOURCE = "cninfo_broad_industry"
    EASTMONEY_PEER_SOURCE = "eastmoney_board"

    def __init__(self, taxonomy: IndustryTaxonomyService | None = None, ak_module: Any | None = None) -> None:
        self.taxonomy = taxonomy or IndustryTaxonomyService()
        self.ak_module = ak_module

    def refresh(
        self,
        db: Session,
        *,
        enterprise_ids: Iterable[int] | None = None,
        period: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        ak_module = self._akshare()
        enterprises = self._load_enterprises(db, enterprise_ids=enterprise_ids, limit=limit)
        summary: dict[str, Any] = {
            "enterprise_count": len(enterprises),
            "mapping_count": 0,
            "sample_count": 0,
            "snapshot_count": 0,
            "industry_count": 0,
            "failures": [],
            "collection_log": [],
        }
        board_error: str | None = None
        try:
            board_rows = self._load_industry_boards(ak_module)
        except Exception:
            board_rows = []
            board_error = "industry_board_load_failed"
        if not board_rows and board_error is None:
            board_error = "industry_board_empty"

        refreshed_keys: set[tuple[str, str, str]] = set()

        for enterprise in enterprises:
            requested_period = period or f"{int(enterprise.report_year)}FY"
            mappings = self._resolve_company_mappings(ak_module, enterprise, board_rows)
            if mappings:
                self._replace_company_mappings(db, enterprise, mappings)
                summary["mapping_count"] += len(mappings)
            references = self._references_from_mappings(enterprise, mappings)
            target_ticker = self._ticker_symbol(enterprise.ticker)
            for reference in references:
                key = (reference.industry_name, reference.industry_level, requested_period)
                if key in refreshed_keys:
                    continue
                refreshed_keys.add(key)
                collection_entry: dict[str, Any] = {
                    "enterprise_id": enterprise.id,
                    "ticker": target_ticker,
                    "period": requested_period,
                    "industry_name": reference.industry_name,
                    "industry_code": reference.industry_code,
                    "peer_source": self.EASTMONEY_PEER_SOURCE,
                    "candidate_count": 0,
                    "scanned_count": 0,
                    "matched_peer_count": 0,
                    "financial_attempted_count": 0,
                    "financial_success_count": 0,
                    "sample_row_count": 0,
                    "snapshot_count": 0,
                    "status": "started",
                }
                try:
                    board = self._board_for_reference(board_rows, reference)
                    peer_source = self.EASTMONEY_PEER_SOURCE
                    peer_rows: list[dict[str, str]] = []
                    industry_code = board.get("code") if board else reference.industry_code
                    collection_entry["industry_code"] = industry_code

                    if board_error:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": board_error,
                            }
                        )
                    elif board is None:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": "industry_board_not_matched",
                            }
                        )
                    else:
                        try:
                            peer_rows = self._load_peer_rows(ak_module, board["symbol"], target_ticker)
                            collection_entry["candidate_count"] = len(peer_rows)
                            collection_entry["scanned_count"] = len(peer_rows)
                            collection_entry["matched_peer_count"] = len(peer_rows)
                        except Exception as exc:
                            summary["failures"].append(
                                {
                                    "enterprise_id": enterprise.id,
                                    "industry_name": reference.industry_name,
                                    "period": requested_period,
                                    "error": f"industry_peer_load_failed:{exc}",
                                }
                            )
                    if not peer_rows:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": "industry_peer_empty",
                            }
                        )
                        if self._reference_matches_cninfo_broad(reference, mappings):
                            cninfo_stats = {
                                "candidate_count": 0,
                                "scanned_count": 0,
                                "matched_peer_count": 0,
                            }
                            peer_rows = self._load_cninfo_peer_rows(
                                ak_module=ak_module,
                                target_ticker=target_ticker,
                                target_mappings=mappings,
                                stats=cninfo_stats,
                            )
                            peer_source = self.CNINFO_PEER_SOURCE
                            industry_code = reference.industry_code
                            collection_entry.update(cninfo_stats)
                            collection_entry["peer_source"] = peer_source
                            collection_entry["industry_code"] = industry_code
                            board = {
                                "name": reference.industry_name,
                                "code": reference.industry_code,
                                "symbol": reference.industry_name,
                                "normalized": self._normalize(reference.industry_name),
                            }
                        if not peer_rows:
                            summary["failures"].append(
                                {
                                    "enterprise_id": enterprise.id,
                                    "industry_name": reference.industry_name,
                                    "period": requested_period,
                                    "error": "cninfo_peer_empty",
                                }
                            )
                            self._record_collection_status(summary, collection_entry, "peer_empty")
                            continue

                    if board is None:
                        self._record_collection_status(summary, collection_entry, "board_missing")
                        continue
                    collection_entry["financial_attempted_count"] = min(len(peer_rows), self.PEER_LIMIT)
                    records = self._fetch_peer_records(ak_module, peer_rows, requested_period)
                    collection_entry["financial_success_count"] = len(records)
                    if not records:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": "industry_peer_financial_empty",
                            }
                        )
                        self._record_collection_status(summary, collection_entry, "financial_empty")
                        continue
                    if len(records) < self.MIN_DISPLAY_SAMPLE:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": "industry_peer_insufficient",
                            }
                        )
                        self._record_collection_status(summary, collection_entry, "insufficient_sample")
                        continue
                    sample_rows = self._build_sample_pool_rows(
                        requested_period=requested_period,
                        reference=reference,
                        board=board,
                        records=records,
                        industry_source=peer_source,
                    )
                    if not sample_rows:
                        summary["failures"].append(
                            {
                                "enterprise_id": enterprise.id,
                                "industry_name": reference.industry_name,
                                "period": requested_period,
                                "error": "industry_sample_empty",
                            }
                        )
                        self._record_collection_status(summary, collection_entry, "sample_empty")
                        continue
                    self._replace_sample_pool(
                        db,
                        industry_source=peer_source,
                        industry_code=industry_code,
                        industry_name=reference.industry_name,
                        period=requested_period,
                        sample_rows=sample_rows,
                    )
                    db.flush()
                    samples_by_metric = self._load_metric_samples_from_pool(
                        db,
                        industry_source=peer_source,
                        industry_code=industry_code,
                        industry_name=reference.industry_name,
                        period=requested_period,
                    )
                    snapshots = self.build_snapshots_from_samples(
                        reference=reference,
                        requested_period=requested_period,
                        samples_by_metric=samples_by_metric,
                        industry_code=industry_code,
                    )
                    self._replace_snapshots(db, snapshots)
                    summary["sample_count"] += len(sample_rows)
                    summary["snapshot_count"] += len(snapshots)
                    summary["industry_count"] += 1 if snapshots else 0
                    collection_entry["sample_row_count"] = len(sample_rows)
                    collection_entry["snapshot_count"] = len(snapshots)
                    self._record_collection_status(summary, collection_entry, "success")
                except Exception as exc:  # pragma: no cover - defensive around flaky provider calls
                    summary["failures"].append(
                        {
                            "enterprise_id": enterprise.id,
                            "industry_name": reference.industry_name,
                            "period": requested_period,
                            "error": str(exc),
                        }
                    )
                    self._record_collection_status(summary, collection_entry, "exception")
        db.commit()
        return summary

    def _record_collection_status(
        self,
        summary: dict[str, Any],
        collection_entry: dict[str, Any],
        status: str,
    ) -> None:
        entry = dict(collection_entry)
        entry["status"] = status
        summary["collection_log"].append(entry)
        logger.info(
            "industry_benchmark_collection_status "
            "enterprise_id=%s ticker=%s period=%s industry_name=%s industry_code=%s "
            "peer_source=%s candidate_count=%s scanned_count=%s matched_peer_count=%s "
            "financial_attempted_count=%s financial_success_count=%s sample_row_count=%s "
            "snapshot_count=%s status=%s",
            entry.get("enterprise_id"),
            entry.get("ticker"),
            entry.get("period"),
            entry.get("industry_name"),
            entry.get("industry_code"),
            entry.get("peer_source"),
            entry.get("candidate_count"),
            entry.get("scanned_count"),
            entry.get("matched_peer_count"),
            entry.get("financial_attempted_count"),
            entry.get("financial_success_count"),
            entry.get("sample_row_count"),
            entry.get("snapshot_count"),
            entry.get("status"),
        )

    def build_snapshots(
        self,
        *,
        reference: IndustryReference,
        requested_period: str,
        records: list[PeerFinancialRecord],
        industry_code: str | None = None,
    ) -> list[IndustryBenchmarkSnapshot]:
        snapshots: list[IndustryBenchmarkSnapshot] = []
        for metric in self.METRICS:
            samples = self._metric_samples(metric, records)
            stats = self._metric_stats(metric, samples, requested_period)
            snapshots.append(
                IndustryBenchmarkSnapshot(
                    industry_code=industry_code or reference.industry_code,
                    industry_name=reference.industry_name,
                    industry_level=reference.industry_level,
                    original_industry=reference.original_industry,
                    fallback_used=reference.fallback_used,
                    period=requested_period,
                    metric=metric,
                    mean=stats["mean"],
                    median=stats["median"],
                    p25=stats["p25"],
                    p75=stats["p75"],
                    sample_count=stats["sample_count"],
                    confidence=stats["confidence"],
                    period_aligned=stats["period_aligned"],
                    actual_peer_period_range=stats["actual_peer_period_range"],
                    aggregation_method=stats["aggregation_method"],
                    source="akshare_snapshot",
                    metadata_json=stats["metadata_json"],
                )
            )
        return snapshots

    def build_snapshots_from_samples(
        self,
        *,
        reference: IndustryReference,
        requested_period: str,
        samples_by_metric: dict[str, list[MetricSample]],
        industry_code: str | None = None,
    ) -> list[IndustryBenchmarkSnapshot]:
        snapshots: list[IndustryBenchmarkSnapshot] = []
        for metric in self.METRICS:
            stats = self._metric_stats(metric, samples_by_metric.get(metric, []), requested_period)
            snapshots.append(
                IndustryBenchmarkSnapshot(
                    industry_code=industry_code or reference.industry_code,
                    industry_name=reference.industry_name,
                    industry_level=reference.industry_level,
                    original_industry=reference.original_industry,
                    fallback_used=reference.fallback_used,
                    period=requested_period,
                    metric=metric,
                    mean=stats["mean"],
                    median=stats["median"],
                    p25=stats["p25"],
                    p75=stats["p75"],
                    sample_count=stats["sample_count"],
                    confidence=stats["confidence"],
                    period_aligned=stats["period_aligned"],
                    actual_peer_period_range=stats["actual_peer_period_range"],
                    aggregation_method=stats["aggregation_method"],
                    source="akshare_sample_pool",
                    metadata_json=stats["metadata_json"],
                )
            )
        return snapshots

    def _metric_samples(self, metric: str, records: list[PeerFinancialRecord]) -> list[MetricSample]:
        samples: list[MetricSample] = []
        for record in records:
            sample = self._record_metric_sample(metric, record)
            if sample is None or not self._is_reasonable(metric, sample.value):
                continue
            samples.append(sample)
        return samples

    def _record_metric_sample(self, metric: str, record: PeerFinancialRecord) -> MetricSample | None:
        revenue = self._positive(record.revenue)
        if metric == "revenue":
            return MetricSample(record.ticker, revenue, record.actual_period, sample_name=record.name) if revenue is not None else None
        if metric == "revenue_growth":
            previous = self._positive(record.previous_revenue)
            if revenue is None or previous is None:
                return None
            return MetricSample(record.ticker, ((revenue / previous) - 1.0) * 100.0, record.actual_period, revenue, previous, record.name)
        if metric == "gross_margin":
            gross_profit = self._finite(record.gross_profit)
            if revenue is None or gross_profit is None:
                return None
            return MetricSample(record.ticker, gross_profit / revenue * 100.0, record.actual_period, gross_profit, revenue, record.name)
        if metric == "net_margin":
            net_profit = self._finite(record.net_profit)
            if revenue is None or net_profit is None:
                return None
            return MetricSample(record.ticker, net_profit / revenue * 100.0, record.actual_period, net_profit, revenue, record.name)
        if metric == "ar_turnover":
            average_ar = self._positive(record.average_ar)
            if revenue is None or average_ar is None:
                return None
            return MetricSample(record.ticker, revenue / average_ar, record.actual_period, revenue, average_ar, record.name)
        if metric == "inventory_turnover":
            cost = self._positive(record.operating_cost)
            average_inventory = self._positive(record.average_inventory)
            if cost is None or average_inventory is None:
                return None
            return MetricSample(record.ticker, cost / average_inventory, record.actual_period, cost, average_inventory, record.name)
        if metric == "debt_ratio":
            liabilities = self._finite(record.total_liabilities)
            assets = self._positive(record.total_assets)
            if liabilities is None or assets is None:
                return None
            return MetricSample(record.ticker, liabilities / assets * 100.0, record.actual_period, liabilities, assets, record.name)
        if metric == "expense_ratio":
            expenses = self._finite(record.expenses)
            if revenue is None or expenses is None:
                return None
            return MetricSample(record.ticker, expenses / revenue * 100.0, record.actual_period, expenses, revenue, record.name)
        return None

    def _metric_stats(self, metric: str, samples: list[MetricSample], requested_period: str) -> dict[str, Any]:
        sample_count = len(samples)
        confidence = self._confidence(sample_count)
        actual_periods = sorted({sample.actual_period for sample in samples if sample.actual_period})
        period_aligned = bool(actual_periods) and actual_periods == [requested_period]
        metadata = {
            "requested_period": requested_period,
            "included_tickers": [sample.ticker for sample in samples[:60]],
            "raw_sample_count": sample_count,
        }
        if sample_count < self.MIN_DISPLAY_SAMPLE:
            return {
                "mean": None,
                "median": None,
                "p25": None,
                "p75": None,
                "sample_count": sample_count,
                "confidence": confidence,
                "period_aligned": period_aligned,
                "actual_peer_period_range": self._period_range(actual_periods),
                "aggregation_method": "weighted_ratio" if metric in self.WEIGHTED_METRICS else "distribution",
                "metadata_json": metadata,
            }

        values = self._winsorize([sample.value for sample in samples])
        p25 = self._percentile(values, 25)
        median = self._percentile(values, 50)
        p75 = self._percentile(values, 75)
        if metric == "revenue":
            mean_value = sum(values) / len(values) if values else None
            aggregation_method = "winsorized_distribution"
        else:
            numerator = sum(sample.numerator or 0.0 for sample in samples)
            denominator = sum(sample.denominator or 0.0 for sample in samples)
            mean_value = self._weighted_value(metric, numerator, denominator)
            aggregation_method = "weighted_ratio"
        return {
            "mean": mean_value,
            "median": median,
            "p25": p25,
            "p75": p75,
            "sample_count": sample_count,
            "confidence": confidence,
            "period_aligned": period_aligned,
            "actual_peer_period_range": self._period_range(actual_periods),
            "aggregation_method": aggregation_method,
            "metadata_json": metadata,
        }

    def _fetch_peer_records(self, ak_module: Any, peer_codes: list[Any], requested_period: str) -> list[PeerFinancialRecord]:
        records: list[PeerFinancialRecord] = []
        for item in peer_codes[: self.PEER_LIMIT]:
            code = item.get("ticker") if isinstance(item, dict) else str(item)
            record = self._fetch_peer_record(ak_module, code, requested_period)
            if record is not None:
                if isinstance(item, dict):
                    record.name = item.get("name")
                records.append(record)
        return records

    def _fetch_peer_record(self, ak_module: Any, code: str, requested_period: str) -> PeerFinancialRecord | None:
        exchange_symbol = self._exchange_symbol(code)
        try:
            profit_df = ak_module.stock_profit_sheet_by_report_em(symbol=exchange_symbol)
            balance_df = ak_module.stock_balance_sheet_by_report_em(symbol=exchange_symbol)
        except Exception:
            return None
        profit_records = self._statement_records(profit_df)
        balance_records = self._statement_records(balance_df)
        profit_current = self._select_period_record(profit_records, requested_period)
        if profit_current is None:
            return None
        actual_period = profit_current["period"]
        balance_current = self._select_period_record(balance_records, actual_period)
        balance_previous = self._previous_record(balance_records, actual_period)
        profit_previous_year = self._same_period_previous_year(profit_records, actual_period)

        revenue = self._first_number(profit_current["record"], ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "TOTALOPERATEREVE"])
        cost = self._first_number(profit_current["record"], ["OPERATE_COST", "TOTAL_OPERATE_COST"])
        gross_profit = self._first_number(profit_current["record"], ["GROSS_PROFIT"])
        if gross_profit is None and revenue is not None and cost is not None:
            gross_profit = revenue - cost
        expenses = sum(
            value
            for value in (
                self._first_number(profit_current["record"], ["SALE_EXPENSE"]),
                self._first_number(profit_current["record"], ["MANAGE_EXPENSE"]),
                self._first_number(profit_current["record"], ["RESEARCH_EXPENSE", "ME_RESEARCH_EXPENSE"]),
                self._first_number(profit_current["record"], ["FINANCE_EXPENSE"]),
            )
            if value is not None
        )
        previous_revenue = (
            self._first_number(profit_previous_year["record"], ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "TOTALOPERATEREVE"])
            if profit_previous_year
            else None
        )
        balance_record = balance_current["record"] if balance_current else {}
        previous_balance_record = balance_previous["record"] if balance_previous else {}

        ar_current = self._first_number(balance_record, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"])
        ar_previous = self._first_number(previous_balance_record, ["ACCOUNTS_RECE", "ACCOUNT_RECE", "ACCOUNTS_RECEIVABLE"])
        inventory_current = self._first_number(balance_record, ["INVENTORY"])
        inventory_previous = self._first_number(previous_balance_record, ["INVENTORY"])
        return PeerFinancialRecord(
            ticker=code,
            actual_period=actual_period,
            revenue=revenue,
            previous_revenue=previous_revenue,
            operating_cost=cost,
            gross_profit=gross_profit,
            net_profit=self._first_number(profit_current["record"], ["PARENT_NETPROFIT", "NETPROFIT"]),
            expenses=expenses if expenses != 0 else None,
            average_ar=self._average_positive(ar_current, ar_previous),
            average_inventory=self._average_positive(inventory_current, inventory_previous),
            total_assets=self._first_number(balance_record, ["TOTAL_ASSETS"]),
            total_liabilities=self._first_number(balance_record, ["TOTAL_LIABILITIES"]),
        )

    def _load_enterprises(
        self,
        db: Session,
        *,
        enterprise_ids: Iterable[int] | None,
        limit: int | None,
    ) -> list[EnterpriseProfile]:
        stmt = select(EnterpriseProfile).order_by(EnterpriseProfile.id)
        if enterprise_ids:
            stmt = stmt.where(EnterpriseProfile.id.in_(list(enterprise_ids)))
        if limit:
            stmt = stmt.limit(limit)
        return list(db.scalars(stmt).all())

    def _resolve_company_mappings(
        self,
        ak_module: Any,
        enterprise: EnterpriseProfile,
        board_rows: list[dict[str, str]],
    ) -> list[CompanyIndustryMappingRecord]:
        ticker = self._ticker_symbol(enterprise.ticker)
        if not ticker:
            return []
        mappings: list[CompanyIndustryMappingRecord] = []
        mappings.extend(self._resolve_cninfo_profile_mapping(ak_module, enterprise, ticker))
        mappings.extend(self._resolve_cninfo_change_mappings(ak_module, enterprise, ticker))
        mappings.extend(self._resolve_eastmoney_board_mapping(ak_module, enterprise, ticker, board_rows))
        return self._dedupe_company_mappings(mappings)

    def _resolve_cninfo_profile_mapping(
        self,
        ak_module: Any,
        enterprise: EnterpriseProfile,
        ticker: str,
    ) -> list[CompanyIndustryMappingRecord]:
        if not hasattr(ak_module, "stock_profile_cninfo"):
            return []
        try:
            df = ak_module.stock_profile_cninfo(symbol=ticker)
        except Exception:
            return []
        record = self._first_dataframe_record(df)
        if record is None:
            return []
        industry_name = self._clean_text(record.get("所属行业"))
        if not industry_name:
            return []
        return [
            CompanyIndustryMappingRecord(
                ticker=ticker,
                company_name=self._clean_text(record.get("公司名称")) or enterprise.name,
                source="cninfo_profile",
                standard="巨潮/证监会行业",
                industry_code=None,
                industry_name=industry_name,
                industry_level="primary",
                raw_payload=self._jsonable_record(record),
            )
        ]

    def _resolve_cninfo_change_mappings(
        self,
        ak_module: Any,
        enterprise: EnterpriseProfile,
        ticker: str,
    ) -> list[CompanyIndustryMappingRecord]:
        if not hasattr(ak_module, "stock_industry_change_cninfo"):
            return []
        try:
            df = ak_module.stock_industry_change_cninfo(
                symbol=ticker,
                start_date="20000101",
                end_date=datetime.now(timezone.utc).strftime("%Y%m%d"),
            )
        except Exception:
            return []
        if df is None or getattr(df, "empty", True):
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        latest_by_standard: dict[str, tuple[date | None, CompanyIndustryMappingRecord]] = {}
        for _, record in normalized.iterrows():
            standard_code = self._clean_text(record.get("分类标准编码"))
            if standard_code not in self.CNINFO_BROAD_STANDARD_CODES:
                continue
            industry_name = self._best_cninfo_industry_name(record)
            if not industry_name:
                continue
            effective_date = self._to_date(record.get("变更日期"))
            mapping = CompanyIndustryMappingRecord(
                ticker=ticker,
                company_name=self._clean_text(record.get("机构名称")) or self._clean_text(record.get("新证券简称")) or enterprise.name,
                source="cninfo_industry_change",
                standard=self._clean_text(record.get("分类标准")) or f"cninfo:{standard_code}",
                industry_code=self._clean_text(record.get("行业编码")),
                industry_name=industry_name,
                industry_level="primary" if standard_code == "008001" else "broad",
                effective_date=effective_date,
                raw_payload=self._jsonable_record(record),
            )
            previous = latest_by_standard.get(standard_code)
            if previous is None or self._date_rank(effective_date) >= self._date_rank(previous[0]):
                latest_by_standard[standard_code] = (effective_date, mapping)
        return [item[1] for item in latest_by_standard.values()]

    def _resolve_eastmoney_board_mapping(
        self,
        ak_module: Any,
        enterprise: EnterpriseProfile,
        ticker: str,
        board_rows: list[dict[str, str]],
    ) -> list[CompanyIndustryMappingRecord]:
        if not hasattr(ak_module, "stock_individual_info_em"):
            return []
        try:
            df = ak_module.stock_individual_info_em(symbol=ticker)
        except Exception:
            return []
        mapping = self._key_value_mapping(df)
        industry_name = mapping.get("行业") or mapping.get("所属行业")
        if not industry_name:
            return []
        board = self._match_board(board_rows, industry_name) if board_rows else None
        return [
            CompanyIndustryMappingRecord(
                ticker=ticker,
                company_name=mapping.get("股票简称") or enterprise.name,
                source="eastmoney_board",
                standard="东方财富行业",
                industry_code=board.get("code") if board else None,
                industry_name=board.get("name") if board else industry_name,
                industry_level="board",
                raw_payload={"stock_individual_info_em": mapping},
            )
        ]

    def _replace_company_mappings(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        mappings: list[CompanyIndustryMappingRecord],
    ) -> None:
        ticker = self._ticker_symbol(enterprise.ticker)
        sources = sorted({mapping.source for mapping in mappings})
        if not ticker or not sources:
            return
        db.execute(
            delete(CompanyIndustryMapping).where(
                CompanyIndustryMapping.ticker == ticker,
                CompanyIndustryMapping.source.in_(sources),
            )
        )
        for mapping in mappings:
            db.add(
                CompanyIndustryMapping(
                    ticker=mapping.ticker,
                    company_name=mapping.company_name,
                    source=mapping.source,
                    standard=mapping.standard,
                    industry_code=mapping.industry_code,
                    industry_name=mapping.industry_name,
                    industry_level=mapping.industry_level,
                    effective_date=mapping.effective_date,
                    raw_payload=mapping.raw_payload,
                )
            )

    def _references_from_mappings(
        self,
        enterprise: EnterpriseProfile,
        mappings: list[CompanyIndustryMappingRecord],
    ) -> list[IndustryReference]:
        classification = self.taxonomy.classify(enterprise)
        original_industry = self.taxonomy.original_industry(enterprise, classification)
        references: list[IndustryReference] = []
        seen: set[str] = set()
        ordered_mappings = sorted(mappings, key=lambda item: self._mapping_source_rank(item.source))
        for mapping in ordered_mappings:
            self._append_reference(
                references,
                seen,
                industry_name=mapping.industry_name,
                industry_level=mapping.industry_level or "mapped",
                industry_code=mapping.industry_code,
                original_industry=original_industry,
            )
        for reference in self.taxonomy.candidates(enterprise, classification):
            key = self._normalize(reference.industry_name)
            if not key or key in seen:
                continue
            seen.add(key)
            references.append(reference)
        return references

    def _append_reference(
        self,
        references: list[IndustryReference],
        seen: set[str],
        *,
        industry_name: str,
        industry_level: str,
        industry_code: str | None,
        original_industry: str,
    ) -> None:
        normalized = self._normalize(industry_name)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        references.append(
            IndustryReference(
                industry_name=industry_name,
                industry_level=industry_level,
                fallback_used=self._normalize(industry_name) != self._normalize(original_industry),
                industry_code=industry_code or self.taxonomy.industry_code(industry_name, industry_level),
                original_industry=original_industry,
                rank=len(references),
            )
        )

    def _board_for_reference(
        self,
        board_rows: list[dict[str, str]],
        reference: IndustryReference,
    ) -> dict[str, str] | None:
        if not board_rows:
            return None
        return self._match_board(board_rows, reference.industry_name)

    def _reference_matches_cninfo_broad(
        self,
        reference: IndustryReference,
        mappings: list[CompanyIndustryMappingRecord],
    ) -> bool:
        for target in self._cninfo_broad_targets(mappings):
            if target.industry_code and reference.industry_code and self._normalize(target.industry_code) == self._normalize(reference.industry_code):
                return True
            if self._normalize(target.industry_name) == self._normalize(reference.industry_name):
                return True
        return False

    def _cninfo_broad_targets(
        self,
        mappings: list[CompanyIndustryMappingRecord],
    ) -> list[CompanyIndustryMappingRecord]:
        targets: list[CompanyIndustryMappingRecord] = []
        for mapping in mappings:
            if mapping.source == "cninfo_industry_change":
                raw_standard_code = self._clean_text((mapping.raw_payload or {}).get("分类标准编码"))
                if raw_standard_code in self.CNINFO_BROAD_STANDARD_CODES or mapping.industry_code:
                    targets.append(mapping)
            elif mapping.source == "cninfo_profile" and mapping.industry_name:
                targets.append(mapping)
        return self._dedupe_company_mappings(targets)

    def _load_cninfo_peer_rows(
        self,
        *,
        ak_module: Any,
        target_ticker: str,
        target_mappings: list[CompanyIndustryMappingRecord],
        stats: dict[str, int] | None = None,
    ) -> list[dict[str, str]]:
        if stats is not None:
            stats.setdefault("candidate_count", 0)
            stats.setdefault("scanned_count", 0)
            stats.setdefault("matched_peer_count", 0)
        targets = self._cninfo_broad_targets(target_mappings)
        if not targets or not hasattr(ak_module, "stock_info_a_code_name"):
            return []
        try:
            df = ak_module.stock_info_a_code_name()
        except Exception:
            return []
        if df is None or getattr(df, "empty", True):
            return []

        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        if stats is not None:
            stats["candidate_count"] = len(normalized)
        code_column = self._first_existing_column(normalized, ["code", "证券代码", "A股代码", "代码"])
        name_column = self._first_existing_column(normalized, ["name", "证券简称", "A股简称", "名称"])
        if not code_column:
            return []

        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for _, record in normalized.iterrows():
            code = self._ticker_symbol(str(record.get(code_column)))
            if not code or code == target_ticker or code in seen:
                continue
            if stats is not None:
                stats["scanned_count"] += 1
            name = self._clean_text(record.get(name_column)) if name_column else None
            matched = self._candidate_matches_cninfo_targets(ak_module, code, name, targets)
            if matched is None:
                continue
            seen.add(code)
            rows.append(
                {
                    "ticker": code,
                    "name": name or matched.company_name or code,
                    "industry_code": matched.industry_code or "",
                    "industry_name": matched.industry_name,
                    "source": "stock_info_a_code_name",
                }
            )
            if stats is not None:
                stats["matched_peer_count"] = len(rows)
            if len(rows) >= self.PEER_LIMIT:
                break
        return rows

    def _candidate_matches_cninfo_targets(
        self,
        ak_module: Any,
        code: str,
        name: str | None,
        targets: list[CompanyIndustryMappingRecord],
    ) -> CompanyIndustryMappingRecord | None:
        peer = SimpleNamespace(name=name or code, ticker=code)
        for mapping in self._resolve_cninfo_change_mappings(ak_module, peer, code):
            if self._mapping_matches_any_target(mapping, targets):
                return mapping

        for mapping in self._resolve_cninfo_profile_mapping(ak_module, peer, code):
            if self._mapping_matches_any_target(mapping, targets):
                return mapping
        return None

    def _mapping_matches_any_target(
        self,
        mapping: CompanyIndustryMappingRecord,
        targets: list[CompanyIndustryMappingRecord],
    ) -> bool:
        for target in targets:
            if mapping.industry_code and target.industry_code and self._normalize(mapping.industry_code) == self._normalize(target.industry_code):
                return True
            if self._normalize(mapping.industry_name) == self._normalize(target.industry_name):
                return True
        return False

    def _build_sample_pool_rows(
        self,
        *,
        requested_period: str,
        reference: IndustryReference,
        board: dict[str, str],
        records: list[PeerFinancialRecord],
        industry_source: str,
    ) -> list[IndustrySamplePool]:
        industry_code = board.get("code") or reference.industry_code
        rows: list[IndustrySamplePool] = []
        for metric in self.METRICS:
            for sample in self._metric_samples(metric, records):
                rows.append(
                    IndustrySamplePool(
                        industry_source=industry_source,
                        industry_code=industry_code,
                        industry_name=reference.industry_name,
                        period=requested_period,
                        sample_ticker=sample.ticker,
                        sample_name=sample.sample_name,
                        metric=metric,
                        value=sample.value,
                        numerator=sample.numerator,
                        denominator=sample.denominator,
                        actual_period=sample.actual_period,
                        source="akshare",
                        metadata_json={
                            "industry_source": industry_source,
                            "board_symbol": board.get("symbol"),
                            "board_name": board.get("name"),
                            "reference_level": reference.industry_level,
                        },
                    )
                )
        return rows

    def _replace_sample_pool(
        self,
        db: Session,
        *,
        industry_source: str,
        industry_code: str | None,
        industry_name: str,
        period: str,
        sample_rows: list[IndustrySamplePool],
    ) -> None:
        stmt = delete(IndustrySamplePool).where(
            IndustrySamplePool.industry_source == industry_source,
            IndustrySamplePool.industry_name == industry_name,
            IndustrySamplePool.period == period,
        )
        if industry_code:
            stmt = stmt.where(IndustrySamplePool.industry_code == industry_code)
        db.execute(stmt)
        for row in sample_rows:
            db.add(row)

    def _load_metric_samples_from_pool(
        self,
        db: Session,
        *,
        industry_source: str,
        industry_code: str | None,
        industry_name: str,
        period: str,
    ) -> dict[str, list[MetricSample]]:
        stmt = select(IndustrySamplePool).where(
            IndustrySamplePool.industry_source == industry_source,
            IndustrySamplePool.industry_name == industry_name,
            IndustrySamplePool.period == period,
            IndustrySamplePool.metric.in_(self.METRICS),
        )
        if industry_code:
            stmt = stmt.where(IndustrySamplePool.industry_code == industry_code)
        rows = list(db.scalars(stmt).all())
        samples: dict[str, list[MetricSample]] = {metric: [] for metric in self.METRICS}
        for row in rows:
            value = self._finite(row.value)
            metric = str(row.metric)
            if value is None or metric not in samples or not self._is_reasonable(metric, value):
                continue
            samples[metric].append(
                MetricSample(
                    ticker=row.sample_ticker,
                    value=value,
                    actual_period=row.actual_period,
                    numerator=self._finite(row.numerator),
                    denominator=self._finite(row.denominator),
                    sample_name=row.sample_name,
                )
            )
        return samples

    def _dedupe_company_mappings(
        self,
        mappings: list[CompanyIndustryMappingRecord],
    ) -> list[CompanyIndustryMappingRecord]:
        deduped: list[CompanyIndustryMappingRecord] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for mapping in sorted(mappings, key=lambda item: self._mapping_source_rank(item.source)):
            normalized_name = self._normalize(mapping.industry_name)
            if not normalized_name:
                continue
            key = (
                mapping.ticker,
                mapping.source,
                mapping.standard,
                self._normalize(mapping.industry_code),
                normalized_name,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(mapping)
        return deduped

    def _best_cninfo_industry_name(self, record: Any) -> str | None:
        for column in ("行业大类", "行业中类", "行业次类", "行业门类"):
            value = self._clean_text(record.get(column) if hasattr(record, "get") else None)
            if value:
                return value
        return None

    def _key_value_mapping(self, df: Any) -> dict[str, str]:
        if df is None or getattr(df, "empty", True):
            return {}
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        key_column = self._first_existing_column(normalized, ["item", "项目"])
        value_column = self._first_existing_column(normalized, ["value", "值"])
        if not key_column or not value_column:
            return {}
        mapping: dict[str, str] = {}
        for _, record in normalized.iterrows():
            key = self._clean_text(record.get(key_column))
            value = self._clean_text(record.get(value_column))
            if key and value:
                mapping[key] = value
        return mapping

    def _first_dataframe_record(self, df: Any) -> Any | None:
        if df is None or getattr(df, "empty", True):
            return None
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        return normalized.iloc[0]

    def _jsonable_record(self, record: Any) -> dict[str, Any]:
        if record is None:
            return {}
        items = record.items() if hasattr(record, "items") else []
        return {str(key): self._jsonable_value(value) for key, value in items}

    def _jsonable_value(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            if value != value:
                return None
        except Exception:
            pass
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _to_date(self, value: Any) -> date | None:
        timestamp = self._to_timestamp(value)
        if timestamp is None:
            return None
        return date(int(timestamp.year), int(timestamp.month), int(timestamp.day))

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        try:
            if value != value:
                return None
        except Exception:
            pass
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null", "--", "-"}:
            return None
        return text

    @staticmethod
    def _date_rank(value: date | None) -> int:
        return value.toordinal() if value is not None else 0

    @staticmethod
    def _mapping_source_rank(source: str) -> int:
        order = {
            "eastmoney_board": 0,
            "cninfo_industry_change": 1,
            "cninfo_profile": 2,
        }
        return order.get(source, 99)

    def _load_industry_boards(self, ak_module: Any) -> list[dict[str, str]]:
        df = ak_module.stock_board_industry_name_em()
        if df is None or getattr(df, "empty", True):
            return []
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        name_column = self._first_existing_column(normalized, ["板块名称", "行业名称", "名称"])
        code_column = self._first_existing_column(normalized, ["板块代码", "行业代码", "代码"])
        if not name_column:
            return []
        rows: list[dict[str, str]] = []
        for _, record in normalized.iterrows():
            name = str(record.get(name_column) or "").strip()
            if not name:
                continue
            code = str(record.get(code_column) or "").strip() if code_column else ""
            rows.append({"name": name, "code": code, "symbol": name, "normalized": self._normalize(name)})
        return rows

    def _match_board(self, rows: list[dict[str, str]], industry_name: str) -> dict[str, str] | None:
        target = self._normalize(industry_name)
        if not target:
            return None
        for row in rows:
            if row["normalized"] == target:
                return row
        for row in rows:
            if len(target) >= 3 and (target in row["normalized"] or row["normalized"] in target):
                return row
        return None

    def _load_peer_rows(self, ak_module: Any, board_symbol: str, target_ticker: str) -> list[dict[str, str]]:
        df = ak_module.stock_board_industry_cons_em(symbol=board_symbol)
        if df is None or getattr(df, "empty", True):
            return []
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        code_column = self._first_existing_column(normalized, ["代码", "SECURITY_CODE", "stock_code", "code"])
        name_column = self._first_existing_column(normalized, ["名称", "SECURITY_NAME_ABBR", "stock_name", "name"])
        if not code_column:
            return []
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for _, record in normalized.iterrows():
            code = self._ticker_symbol(str(record.get(code_column)))
            if not code or code == target_ticker or code in seen:
                continue
            seen.add(code)
            name = str(record.get(name_column) or "").strip() if name_column else ""
            rows.append({"ticker": code, "name": name})
        return rows

    def _load_peer_codes(self, ak_module: Any, board_symbol: str, target_ticker: str) -> list[str]:
        return [row["ticker"] for row in self._load_peer_rows(ak_module, board_symbol, target_ticker)]

    def _replace_snapshots(self, db: Session, snapshots: list[IndustryBenchmarkSnapshot]) -> None:
        for snapshot in snapshots:
            db.execute(
                delete(IndustryBenchmarkSnapshot).where(
                    IndustryBenchmarkSnapshot.industry_name == snapshot.industry_name,
                    IndustryBenchmarkSnapshot.industry_level == snapshot.industry_level,
                    IndustryBenchmarkSnapshot.original_industry == snapshot.original_industry,
                    IndustryBenchmarkSnapshot.period == snapshot.period,
                    IndustryBenchmarkSnapshot.metric == snapshot.metric,
                )
            )
            db.add(snapshot)

    def _statement_records(self, df: Any) -> list[dict[str, Any]]:
        if df is None or getattr(df, "empty", True):
            return []
        normalized = df.copy()
        normalized.columns = [str(column).strip() for column in normalized.columns]
        date_column = self._first_existing_column(normalized, ["REPORT_DATE", "REPORT_DATE_NAME", "报告期"])
        if not date_column:
            return []
        records: list[dict[str, Any]] = []
        for _, record in normalized.iterrows():
            timestamp = self._to_timestamp(record.get(date_column))
            if timestamp is None:
                continue
            records.append({"period": self._label_period(timestamp), "rank": self._period_rank_from_timestamp(timestamp), "record": record})
        records.sort(key=lambda item: item["rank"])
        return records

    def _select_period_record(self, records: list[dict[str, Any]], requested_period: str) -> dict[str, Any] | None:
        requested_rank = self._period_rank(requested_period)
        exact = [record for record in records if record["period"] == requested_period]
        if exact:
            return exact[-1]
        previous = [record for record in records if record["rank"] <= requested_rank]
        return previous[-1] if previous else (records[-1] if records else None)

    def _previous_record(self, records: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
        rank = self._period_rank(period)
        previous = [record for record in records if record["rank"] < rank]
        return previous[-1] if previous else None

    def _same_period_previous_year(self, records: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
        target = self._previous_year_period(period)
        for record in records:
            if record["period"] == target:
                return record
        return None

    def _weighted_value(self, metric: str, numerator: float, denominator: float) -> float | None:
        if denominator <= 0:
            return None
        if metric == "revenue_growth":
            return ((numerator / denominator) - 1.0) * 100.0
        if metric in {"gross_margin", "net_margin", "debt_ratio", "expense_ratio"}:
            return numerator / denominator * 100.0
        return numerator / denominator

    def _winsorize(self, values: list[float]) -> list[float]:
        if not values:
            return []
        ordered = sorted(values)
        low = self._percentile(ordered, 5)
        high = self._percentile(ordered, 95)
        if low is None or high is None:
            return ordered
        return [min(max(value, low), high) for value in ordered]

    def _is_reasonable(self, metric: str, value: float) -> bool:
        if not math.isfinite(value):
            return False
        ranges = {
            "revenue": (0.0, math.inf),
            "revenue_growth": (-95.0, 1000.0),
            "gross_margin": (-100.0, 100.0),
            "net_margin": (-200.0, 200.0),
            "ar_turnover": (0.0, 1000.0),
            "inventory_turnover": (0.0, 1000.0),
            "debt_ratio": (0.0, 300.0),
            "expense_ratio": (-50.0, 200.0),
        }
        lower, upper = ranges.get(metric, (-math.inf, math.inf))
        return lower <= value <= upper

    @staticmethod
    def _confidence(sample_count: int) -> str:
        if sample_count >= 20:
            return "high"
        if sample_count >= 10:
            return "limited"
        if sample_count >= 5:
            return "cautious"
        return "unavailable"

    @staticmethod
    def _period_range(periods: list[str]) -> list[str]:
        if not periods:
            return []
        return [periods[0], periods[-1]] if periods[0] != periods[-1] else [periods[0]]

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * percentile / 100.0
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    @staticmethod
    def _average_positive(current: float | None, previous: float | None) -> float | None:
        current_value = IndustryBenchmarkRefreshService._positive(current)
        previous_value = IndustryBenchmarkRefreshService._positive(previous)
        if current_value is not None and previous_value is not None:
            return (current_value + previous_value) / 2.0
        return current_value

    @staticmethod
    def _positive(value: Any) -> float | None:
        number = IndustryBenchmarkRefreshService._finite(value)
        return number if number is not None and number > 0 else None

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
    def _first_number(record: Any, candidates: list[str]) -> float | None:
        index = set(getattr(record, "index", []))
        for candidate in candidates:
            if candidate not in index and not isinstance(record, dict):
                continue
            value = record.get(candidate) if hasattr(record, "get") else None
            number = IndustryBenchmarkRefreshService._coerce_number(value)
            if number is not None:
                return number
        return None

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            if value != value:
                return None
        except Exception:
            pass
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "none", "false", "--", "-"}:
            return None
        multiplier = 1.0
        if text.endswith("%"):
            text = text[:-1]
        if text.endswith("亿"):
            multiplier = 100000000.0
            text = text[:-1]
        elif text.endswith("万"):
            multiplier = 10000.0
            text = text[:-1]
        try:
            return float(text) * multiplier
        except ValueError:
            return None

    @staticmethod
    def _first_existing_column(df: Any, candidates: list[str]) -> str | None:
        columns = set(getattr(df, "columns", []))
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _label_period(timestamp: Any) -> str:
        year = int(timestamp.year)
        month = int(timestamp.month)
        if month == 12:
            return f"{year}FY"
        quarter = max(1, min(4, (month - 1) // 3 + 1))
        return f"{year}Q{quarter}"

    @staticmethod
    def _period_rank(period: str) -> int:
        text = str(period or "").upper()
        year = int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else 0
        if "FY" in text:
            return year * 10 + 5
        if "Q" in text:
            try:
                return year * 10 + int(text.split("Q", 1)[1][:1])
            except ValueError:
                return year * 10
        if len(text) >= 6 and text[4:6].isdigit():
            month = int(text[4:6])
            return year * 10 + (5 if month == 12 else max(1, min(4, (month - 1) // 3 + 1)))
        return year * 10

    @staticmethod
    def _period_rank_from_timestamp(timestamp: Any) -> int:
        year = int(timestamp.year)
        month = int(timestamp.month)
        quarter = 5 if month == 12 else max(1, min(4, (month - 1) // 3 + 1))
        return year * 10 + quarter

    @staticmethod
    def _previous_year_period(period: str) -> str:
        text = str(period or "").upper()
        year = int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else 0
        return f"{year - 1}{text[4:]}" if year else text

    @staticmethod
    def _to_timestamp(value: Any) -> Any | None:
        try:
            import pandas as pd

            timestamp = pd.to_datetime(value)
        except Exception:
            return None
        if getattr(timestamp, "year", None) is None or pd.isna(timestamp):
            return None
        return timestamp

    @staticmethod
    def _ticker_symbol(value: str) -> str:
        normalized = str(value or "").strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]
        normalized = normalized.replace("SH", "").replace("SZ", "")
        digits = "".join(char for char in normalized if char.isdigit())
        return digits.zfill(6) if digits else ""

    @staticmethod
    def _exchange_symbol(code: str) -> str:
        symbol = IndustryBenchmarkRefreshService._ticker_symbol(code)
        prefix = "SH" if symbol.startswith(("5", "6", "9")) else "SZ"
        return f"{prefix}{symbol}"

    @staticmethod
    def _normalize(value: str | None) -> str:
        return "".join(str(value or "").strip().upper().replace("（", "(").replace("）", ")").split())

    def _akshare(self) -> Any:
        if self.ak_module is not None:
            return self.ak_module
        if not settings.akshare_enable:
            raise RuntimeError("AkShare is disabled by settings.akshare_enable")
        import akshare as ak

        return ak
