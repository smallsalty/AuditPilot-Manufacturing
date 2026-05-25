from __future__ import annotations

import logging

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import CompanyIndustryMapping, EnterpriseProfile, FinancialIndicator, IndustryBenchmarkSnapshot, IndustrySamplePool
from app.models.base import Base
from app.services.financial_report_service import FinancialReportService
from app.services.industry_benchmark_refresh_service import IndustryBenchmarkRefreshService, PeerFinancialRecord
from app.services.industry_taxonomy_service import IndustryReference


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _reference() -> IndustryReference:
    return IndustryReference(
        industry_name="专用设备",
        industry_level="secondary",
        fallback_used=True,
        industry_code="secondary:专用设备",
        original_industry="半导体设备",
        rank=1,
    )


def test_refresh_stats_use_weighted_ratio_not_simple_average():
    records = [
        PeerFinancialRecord("000001", "2025FY", revenue=100.0, previous_revenue=80.0, gross_profit=20.0, net_profit=10.0, operating_cost=70.0, expenses=8.0, average_ar=25.0, average_inventory=35.0, total_assets=200.0, total_liabilities=80.0),
        PeerFinancialRecord("000002", "2025FY", revenue=200.0, previous_revenue=200.0, gross_profit=60.0, net_profit=20.0, operating_cost=120.0, expenses=20.0, average_ar=50.0, average_inventory=40.0, total_assets=300.0, total_liabilities=180.0),
        PeerFinancialRecord("000003", "2025FY", revenue=300.0, previous_revenue=250.0, gross_profit=90.0, net_profit=45.0, operating_cost=180.0, expenses=36.0, average_ar=100.0, average_inventory=60.0, total_assets=500.0, total_liabilities=200.0),
        PeerFinancialRecord("000004", "2025FY", revenue=400.0, previous_revenue=300.0, gross_profit=160.0, net_profit=80.0, operating_cost=220.0, expenses=40.0, average_ar=80.0, average_inventory=110.0, total_assets=600.0, total_liabilities=300.0),
        PeerFinancialRecord("000005", "2025FY", revenue=500.0, previous_revenue=400.0, gross_profit=100.0, net_profit=50.0, operating_cost=350.0, expenses=70.0, average_ar=125.0, average_inventory=175.0, total_assets=900.0, total_liabilities=450.0),
    ]

    snapshots = {
        snapshot.metric: snapshot
        for snapshot in IndustryBenchmarkRefreshService().build_snapshots(
            reference=_reference(),
            requested_period="2025FY",
            records=records,
        )
    }

    assert snapshots["gross_margin"].mean == pytest.approx((20 + 60 + 90 + 160 + 100) / 1500 * 100)
    assert snapshots["ar_turnover"].mean == pytest.approx(1500 / (25 + 50 + 100 + 80 + 125))
    assert snapshots["inventory_turnover"].mean == pytest.approx((70 + 120 + 180 + 220 + 350) / (35 + 40 + 60 + 110 + 175))
    assert snapshots["debt_ratio"].mean == pytest.approx((80 + 180 + 200 + 300 + 450) / (200 + 300 + 500 + 600 + 900) * 100)
    assert snapshots["expense_ratio"].mean == pytest.approx((8 + 20 + 36 + 40 + 70) / 1500 * 100)
    assert snapshots["revenue_growth"].mean == pytest.approx((1500 / (80 + 200 + 250 + 300 + 400) - 1) * 100)
    assert snapshots["gross_margin"].confidence == "cautious"


def test_refresh_samples_are_independent_by_metric_and_small_metric_is_hidden():
    records = [
        PeerFinancialRecord("000001", "2025FY", revenue=100.0, gross_profit=20.0, expenses=8.0),
        PeerFinancialRecord("000002", "2025FY", revenue=200.0, gross_profit=60.0, expenses=20.0),
        PeerFinancialRecord("000003", "2025FY", revenue=300.0, gross_profit=90.0, expenses=36.0),
        PeerFinancialRecord("000004", "2025FY", revenue=400.0, gross_profit=160.0, expenses=None),
        PeerFinancialRecord("000005", "2025FY", revenue=500.0, gross_profit=100.0, expenses=None),
    ]

    snapshots = {
        snapshot.metric: snapshot
        for snapshot in IndustryBenchmarkRefreshService().build_snapshots(
            reference=_reference(),
            requested_period="2025FY",
            records=records,
        )
    }

    assert snapshots["gross_margin"].sample_count == 5
    assert snapshots["gross_margin"].median is not None
    assert snapshots["expense_ratio"].sample_count == 3
    assert snapshots["expense_ratio"].mean is None
    assert snapshots["expense_ratio"].confidence == "unavailable"


def test_refresh_marks_period_mismatch_and_limited_confidence():
    records = [
        PeerFinancialRecord(str(index).zfill(6), "2024FY" if index == 0 else "2025FY", revenue=100.0 + index, gross_profit=20.0 + index)
        for index in range(10)
    ]

    gross_margin = next(
        snapshot
        for snapshot in IndustryBenchmarkRefreshService().build_snapshots(
            reference=_reference(),
            requested_period="2025FY",
            records=records,
        )
        if snapshot.metric == "gross_margin"
    )

    assert gross_margin.sample_count == 10
    assert gross_margin.confidence == "limited"
    assert gross_margin.period_aligned is False
    assert gross_margin.actual_peer_period_range == ["2024FY", "2025FY"]
    assert gross_margin.p25 is not None
    assert gross_margin.p75 is not None


def test_refresh_uses_industry_name_for_constituents_and_writes_snapshots():
    pd = pytest.importorskip("pandas")

    class FakeAkShare:
        def __init__(self) -> None:
            self.constituent_symbols: list[str] = []

        def stock_board_industry_name_em(self):
            return pd.DataFrame([{"板块名称": "专用设备", "板块代码": "BK0427"}])

        def stock_board_industry_cons_em(self, symbol: str):
            self.constituent_symbols.append(symbol)
            return pd.DataFrame({"代码": ["000001", "000002", "000003", "000004", "000005"]})

        def stock_profit_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            current_revenue = 1000.0 + seed * 100
            previous_revenue = 900.0 + seed * 80
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "TOTAL_OPERATE_INCOME": previous_revenue,
                        "OPERATE_COST": previous_revenue * 0.62,
                        "PARENT_NETPROFIT": previous_revenue * 0.08,
                        "SALE_EXPENSE": previous_revenue * 0.03,
                        "MANAGE_EXPENSE": previous_revenue * 0.04,
                        "RESEARCH_EXPENSE": previous_revenue * 0.02,
                        "FINANCE_EXPENSE": previous_revenue * 0.01,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "TOTAL_OPERATE_INCOME": current_revenue,
                        "OPERATE_COST": current_revenue * 0.6,
                        "PARENT_NETPROFIT": current_revenue * 0.1,
                        "SALE_EXPENSE": current_revenue * 0.03,
                        "MANAGE_EXPENSE": current_revenue * 0.04,
                        "RESEARCH_EXPENSE": current_revenue * 0.02,
                        "FINANCE_EXPENSE": current_revenue * 0.01,
                    },
                ]
            )

        def stock_balance_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "ACCOUNTS_RECE": 90.0 + seed,
                        "INVENTORY": 140.0 + seed,
                        "TOTAL_ASSETS": 1000.0 + seed * 20,
                        "TOTAL_LIABILITIES": 420.0 + seed * 10,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "ACCOUNTS_RECE": 110.0 + seed,
                        "INVENTORY": 160.0 + seed,
                        "TOTAL_ASSETS": 1100.0 + seed * 20,
                        "TOTAL_LIABILITIES": 460.0 + seed * 10,
                    },
                ]
            )

    db = _session()
    try:
        enterprise = EnterpriseProfile(
            name="测试专用设备企业",
            ticker="688001",
            report_year=2025,
            industry_tag="制造业",
            sub_industry="专用设备",
            exchange="SSE",
        )
        db.add(enterprise)
        db.commit()
        db.refresh(enterprise)
        fake_akshare = FakeAkShare()

        summary = IndustryBenchmarkRefreshService(ak_module=fake_akshare).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2025FY",
        )

        gross_margin = db.scalar(
            select(IndustryBenchmarkSnapshot).where(
                IndustryBenchmarkSnapshot.industry_name == "专用设备",
                IndustryBenchmarkSnapshot.metric == "gross_margin",
            )
        )
        assert fake_akshare.constituent_symbols[0] == "专用设备"
        assert summary["snapshot_count"] > 0
        assert gross_margin is not None
        assert gross_margin.industry_code == "BK0427"
        assert gross_margin.sample_count == 5
    finally:
        db.close()


def test_refresh_writes_company_mappings_sample_pool_and_snapshots_from_pool():
    pd = pytest.importorskip("pandas")

    class FakeAkShare:
        def __init__(self) -> None:
            self.constituent_symbols: list[str] = []

        def stock_profile_cninfo(self, symbol: str):
            return pd.DataFrame(
                [
                    {
                        "公司名称": "宁德时代新能源科技股份有限公司",
                        "A股代码": symbol,
                        "A股简称": "宁德时代",
                        "所属行业": "电气机械和器材制造业",
                    }
                ]
            )

        def stock_industry_change_cninfo(self, symbol: str, start_date: str, end_date: str):
            return pd.DataFrame(
                [
                    {
                        "新证券简称": "宁德时代",
                        "机构名称": "宁德时代新能源科技股份有限公司",
                        "证券代码": symbol,
                        "分类标准编码": "008001",
                        "分类标准": "中国上市公司协会上市公司行业分类标准",
                        "行业编码": "C38",
                        "行业门类": "制造业",
                        "行业大类": "电气机械和器材制造业",
                        "行业次类": None,
                        "行业中类": None,
                        "变更日期": "2024-02-08",
                    },
                    {
                        "新证券简称": "宁德时代",
                        "机构名称": "宁德时代新能源科技股份有限公司",
                        "证券代码": symbol,
                        "分类标准编码": "008003",
                        "分类标准": "申银万国行业分类标准",
                        "行业编码": "S630701",
                        "行业门类": "电力设备",
                        "行业大类": "锂电池",
                        "行业次类": "电池",
                        "行业中类": "锂电池",
                        "变更日期": "2021-07-30",
                    },
                ]
            )

        def stock_individual_info_em(self, symbol: str):
            return pd.DataFrame(
                [
                    {"item": "股票简称", "value": "宁德时代"},
                    {"item": "行业", "value": "电池"},
                ]
            )

        def stock_board_industry_name_em(self):
            return pd.DataFrame([{"板块名称": "电池", "板块代码": "BK1033"}])

        def stock_board_industry_cons_em(self, symbol: str):
            self.constituent_symbols.append(symbol)
            return pd.DataFrame(
                {
                    "代码": ["300750", "000001", "000002", "000003", "000004", "000005"],
                    "名称": ["宁德时代", "样本一", "样本二", "样本三", "样本四", "样本五"],
                }
            )

        def stock_profit_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            current_revenue = 1000.0 + seed * 100
            previous_revenue = 850.0 + seed * 50
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "TOTAL_OPERATE_INCOME": previous_revenue,
                        "OPERATE_COST": previous_revenue * 0.62,
                        "PARENT_NETPROFIT": previous_revenue * 0.08,
                        "SALE_EXPENSE": previous_revenue * 0.03,
                        "MANAGE_EXPENSE": previous_revenue * 0.04,
                        "RESEARCH_EXPENSE": previous_revenue * 0.02,
                        "FINANCE_EXPENSE": previous_revenue * 0.01,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "TOTAL_OPERATE_INCOME": current_revenue,
                        "OPERATE_COST": current_revenue * 0.6,
                        "PARENT_NETPROFIT": current_revenue * 0.1,
                        "SALE_EXPENSE": current_revenue * 0.03,
                        "MANAGE_EXPENSE": current_revenue * 0.04,
                        "RESEARCH_EXPENSE": current_revenue * 0.02,
                        "FINANCE_EXPENSE": current_revenue * 0.01,
                    },
                ]
            )

        def stock_balance_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "ACCOUNTS_RECE": 90.0 + seed,
                        "INVENTORY": 140.0 + seed,
                        "TOTAL_ASSETS": 1000.0 + seed * 20,
                        "TOTAL_LIABILITIES": 420.0 + seed * 10,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "ACCOUNTS_RECE": 110.0 + seed,
                        "INVENTORY": 160.0 + seed,
                        "TOTAL_ASSETS": 1100.0 + seed * 20,
                        "TOTAL_LIABILITIES": 460.0 + seed * 10,
                    },
                ]
            )

    db = _session()
    try:
        enterprise = EnterpriseProfile(
            name="宁德时代",
            ticker="300750.SZ",
            report_year=2025,
            industry_tag="制造业",
            sub_industry=None,
            exchange="SZSE",
        )
        db.add(enterprise)
        db.commit()
        db.refresh(enterprise)
        fake_akshare = FakeAkShare()

        summary = IndustryBenchmarkRefreshService(ak_module=fake_akshare).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2025FY",
        )

        mappings = list(
            db.scalars(
                select(CompanyIndustryMapping).where(CompanyIndustryMapping.ticker == "300750")
            ).all()
        )
        industries = {mapping.industry_name for mapping in mappings}
        sources = {mapping.source for mapping in mappings}
        sample_rows = list(
            db.scalars(
                select(IndustrySamplePool).where(
                    IndustrySamplePool.industry_name == "电池",
                    IndustrySamplePool.period == "2025FY",
                )
            ).all()
        )
        gross_margin = db.scalar(
            select(IndustryBenchmarkSnapshot).where(
                IndustryBenchmarkSnapshot.industry_name == "电池",
                IndustryBenchmarkSnapshot.metric == "gross_margin",
            )
        )

        assert sources == {"cninfo_profile", "cninfo_industry_change", "eastmoney_board"}
        assert "电气机械和器材制造业" in industries
        assert "电池" in industries
        assert "锂电池" not in industries
        assert fake_akshare.constituent_symbols[0] == "电池"
        assert summary["mapping_count"] == 3
        assert summary["sample_count"] == len(sample_rows)
        assert sample_rows
        assert gross_margin is not None
        assert gross_margin.industry_code == "BK1033"
        assert gross_margin.sample_count == 5
        assert gross_margin.source == "akshare_sample_pool"
    finally:
        db.close()


def test_refresh_uses_real_akshare_a_share_pool_when_eastmoney_board_fails(caplog):
    pd = pytest.importorskip("pandas")

    class FakeAkShare:
        def __init__(self) -> None:
            self.stock_info_called = False
            self.industry_queries: list[str] = []

        def stock_profile_cninfo(self, symbol: str):
            if symbol == "300750":
                return pd.DataFrame(
                    [
                        {
                            "公司名称": "宁德时代新能源科技股份有限公司",
                            "A股代码": symbol,
                            "A股简称": "宁德时代",
                            "所属行业": "电气机械和器材制造业",
                        }
                    ]
                )
            return pd.DataFrame()

        def stock_industry_change_cninfo(self, symbol: str, start_date: str, end_date: str):
            self.industry_queries.append(symbol)
            rows = {
                "300750": ("宁德时代", "宁德时代新能源科技股份有限公司", "C38", "电气机械和器材制造业"),
                "000001": ("同行一", "同行一股份有限公司", "C38", "电气机械和器材制造业"),
                "000002": ("同行二", "同行二股份有限公司", "C38", "电气机械和器材制造业"),
                "000003": ("同行三", "同行三股份有限公司", "C38", "电气机械和器材制造业"),
                "000004": ("同行四", "同行四股份有限公司", "C38", "电气机械和器材制造业"),
                "000005": ("同行五", "同行五股份有限公司", "C38", "电气机械和器材制造业"),
                "000006": ("非同行", "非同行股份有限公司", "C36", "汽车制造业"),
            }
            row = rows.get(symbol)
            if row is None:
                return pd.DataFrame()
            short_name, org_name, industry_code, industry_name = row
            return pd.DataFrame(
                [
                    {
                        "新证券简称": short_name,
                        "机构名称": org_name,
                        "证券代码": symbol,
                        "分类标准编码": "008001",
                        "分类标准": "中国上市公司协会上市公司行业分类标准",
                        "行业编码": industry_code,
                        "行业门类": "制造业",
                        "行业大类": industry_name,
                        "行业次类": None,
                        "行业中类": None,
                        "变更日期": "2024-02-08",
                    }
                ]
            )

        def stock_individual_info_em(self, symbol: str):
            return pd.DataFrame(
                [
                    {"item": "股票简称", "value": "宁德时代"},
                    {"item": "行业", "value": "电池"},
                ]
            )

        def stock_board_industry_name_em(self):
            raise RuntimeError("eastmoney_board_down")

        def stock_info_a_code_name(self):
            self.stock_info_called = True
            base_codes = ["300750", "000001", "000002", "000003", "000004", "000005", "000006"]
            base_names = ["CATL", "peer1", "peer2", "peer3", "peer4", "peer5", "nonpeer"]
            extra_codes = [f"{index:06d}" for index in range(7, 1000)]
            return pd.DataFrame(
                {
                    "code": base_codes + extra_codes,
                    "name": base_names + [f"candidate{index}" for index in range(7, 1000)],
                }
            )

        def stock_profit_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            current_revenue = 1000.0 + seed * 100
            previous_revenue = 850.0 + seed * 50
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "TOTAL_OPERATE_INCOME": previous_revenue,
                        "OPERATE_COST": previous_revenue * 0.62,
                        "PARENT_NETPROFIT": previous_revenue * 0.08,
                        "SALE_EXPENSE": previous_revenue * 0.03,
                        "MANAGE_EXPENSE": previous_revenue * 0.04,
                        "RESEARCH_EXPENSE": previous_revenue * 0.02,
                        "FINANCE_EXPENSE": previous_revenue * 0.01,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "TOTAL_OPERATE_INCOME": current_revenue,
                        "OPERATE_COST": current_revenue * 0.6,
                        "PARENT_NETPROFIT": current_revenue * 0.1,
                        "SALE_EXPENSE": current_revenue * 0.03,
                        "MANAGE_EXPENSE": current_revenue * 0.04,
                        "RESEARCH_EXPENSE": current_revenue * 0.02,
                        "FINANCE_EXPENSE": current_revenue * 0.01,
                    },
                ]
            )

        def stock_balance_sheet_by_report_em(self, symbol: str):
            seed = int(symbol[-1])
            return pd.DataFrame(
                [
                    {
                        "REPORT_DATE": "2024-12-31",
                        "ACCOUNTS_RECE": 90.0 + seed,
                        "INVENTORY": 140.0 + seed,
                        "TOTAL_ASSETS": 1000.0 + seed * 20,
                        "TOTAL_LIABILITIES": 420.0 + seed * 10,
                    },
                    {
                        "REPORT_DATE": "2025-12-31",
                        "ACCOUNTS_RECE": 110.0 + seed,
                        "INVENTORY": 160.0 + seed,
                        "TOTAL_ASSETS": 1100.0 + seed * 20,
                        "TOTAL_LIABILITIES": 460.0 + seed * 10,
                    },
                ]
            )

    db = _session()
    try:
        enterprise = EnterpriseProfile(
            name="宁德时代",
            ticker="300750.SZ",
            report_year=2025,
            industry_tag="制造业",
            sub_industry=None,
            exchange="SZSE",
        )
        db.add(enterprise)
        db.flush()
        db.add(
            FinancialIndicator(
                enterprise_id=enterprise.id,
                period_type="annual",
                report_period="20251231",
                report_year=2025,
                report_quarter=None,
                indicator_code="gross_margin",
                indicator_name="毛利率",
                value=32.0,
                unit="pct",
                source="akshare",
            )
        )
        db.commit()
        db.refresh(enterprise)
        fake_akshare = FakeAkShare()
        caplog.set_level(logging.INFO, logger="app.services.industry_benchmark_refresh_service")

        summary = IndustryBenchmarkRefreshService(ak_module=fake_akshare).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2025FY",
        )

        sample_rows = list(
            db.scalars(
                select(IndustrySamplePool).where(
                    IndustrySamplePool.industry_source == IndustryBenchmarkRefreshService.CNINFO_PEER_SOURCE,
                    IndustrySamplePool.industry_name == "电气机械和器材制造业",
                    IndustrySamplePool.period == "2025FY",
                )
            ).all()
        )
        sample_tickers = {row.sample_ticker for row in sample_rows}
        gross_margin = db.scalar(
            select(IndustryBenchmarkSnapshot).where(
                IndustryBenchmarkSnapshot.industry_code == "C38",
                IndustryBenchmarkSnapshot.industry_name == "电气机械和器材制造业",
                IndustryBenchmarkSnapshot.metric == "gross_margin",
            )
        )
        report = FinancialReportService().build_report(db, enterprise.id, refresh=False, include_quarterly=True)
        comparison = report["industry_comparison"]

        assert fake_akshare.stock_info_called is True
        assert {"000001", "000002", "000003", "000004", "000005"}.issubset(sample_tickers)
        assert "300750" not in sample_tickers
        assert "000006" not in sample_tickers
        assert all(row.metadata_json["industry_source"] == IndustryBenchmarkRefreshService.CNINFO_PEER_SOURCE for row in sample_rows)
        assert any(item["error"] == "industry_board_load_failed" for item in summary["failures"])
        collection_entry = next(
            item
            for item in summary["collection_log"]
            if item["peer_source"] == IndustryBenchmarkRefreshService.CNINFO_PEER_SOURCE
            and item["industry_code"] == "C38"
            and item["status"] == "success"
        )
        assert collection_entry["candidate_count"] == 1000
        assert collection_entry["scanned_count"] == 999
        assert collection_entry["matched_peer_count"] == 5
        assert collection_entry["financial_attempted_count"] == 5
        assert collection_entry["financial_success_count"] == 5
        assert collection_entry["sample_row_count"] == len(sample_rows)
        status_messages = [
            record.getMessage()
            for record in caplog.records
            if "industry_benchmark_collection_status" in record.getMessage()
        ]
        assert any(
            "matched_peer_count=5" in message and "financial_success_count=5" in message
            for message in status_messages
        )
        assert gross_margin is not None
        assert gross_margin.sample_count == 5
        assert comparison["cache_state"] == "partial_hit"
        assert comparison["gross_margin"]["available"] is True
        assert comparison["gross_margin"]["industry_name"] == "电气机械和器材制造业"
    finally:
        db.close()


def test_refresh_failure_keeps_existing_sample_pool_and_snapshot():
    pd = pytest.importorskip("pandas")

    class FailingAkShare:
        def stock_individual_info_em(self, symbol: str):
            return pd.DataFrame(
                [
                    {"item": "股票简称", "value": "宁德时代"},
                    {"item": "行业", "value": "电池"},
                ]
            )

        def stock_board_industry_name_em(self):
            return pd.DataFrame([{"板块名称": "电池", "板块代码": "BK1033"}])

        def stock_board_industry_cons_em(self, symbol: str):
            return pd.DataFrame({"代码": ["000001", "000002", "000003"], "名称": ["样本一", "样本二", "样本三"]})

        def stock_profit_sheet_by_report_em(self, symbol: str):
            raise RuntimeError("network_down")

        def stock_balance_sheet_by_report_em(self, symbol: str):
            raise RuntimeError("network_down")

    db = _session()
    try:
        enterprise = EnterpriseProfile(
            name="宁德时代",
            ticker="300750.SZ",
            report_year=2025,
            industry_tag="制造业",
            sub_industry=None,
            exchange="SZSE",
        )
        db.add_all(
            [
                enterprise,
                IndustrySamplePool(
                    industry_source="eastmoney_board",
                    industry_code="BK1033",
                    industry_name="电池",
                    period="2025FY",
                    sample_ticker="000001",
                    sample_name="旧样本",
                    metric="gross_margin",
                    value=30.0,
                    numerator=30.0,
                    denominator=100.0,
                    actual_period="2025FY",
                    source="akshare",
                ),
                IndustryBenchmarkSnapshot(
                    industry_code="BK1033",
                    industry_name="电池",
                    industry_level="board",
                    original_industry="制造业",
                    fallback_used=True,
                    period="2025FY",
                    metric="gross_margin",
                    mean=30.0,
                    median=30.0,
                    p25=30.0,
                    p75=30.0,
                    sample_count=1,
                    confidence="unavailable",
                    period_aligned=True,
                    actual_peer_period_range=["2025FY"],
                    aggregation_method="weighted_ratio",
                    source="akshare_sample_pool",
                ),
            ]
        )
        db.commit()
        db.refresh(enterprise)

        summary = IndustryBenchmarkRefreshService(ak_module=FailingAkShare()).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2025FY",
        )

        sample = db.scalar(
            select(IndustrySamplePool).where(
                IndustrySamplePool.industry_name == "电池",
                IndustrySamplePool.metric == "gross_margin",
            )
        )
        snapshot = db.scalar(
            select(IndustryBenchmarkSnapshot).where(
                IndustryBenchmarkSnapshot.industry_name == "电池",
                IndustryBenchmarkSnapshot.metric == "gross_margin",
            )
        )

        assert any(item["error"] == "industry_peer_financial_empty" for item in summary["failures"])
        assert sample is not None
        assert sample.sample_name == "旧样本"
        assert snapshot is not None
        assert snapshot.mean == pytest.approx(30.0)
    finally:
        db.close()
