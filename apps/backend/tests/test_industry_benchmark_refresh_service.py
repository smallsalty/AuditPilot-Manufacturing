from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.core.db import rebuild_industry_benchmark_schema
from app.models import EnterpriseProfile, IndustryBenchmarkRefreshState, IndustryLeaderBenchmark, IndustryLeaderCompany
from app.models.base import Base
from app.services.industry_benchmark_refresh_service import (
    BoardValidation,
    EastmoneyBoardValidationClient,
    IndustryBenchmarkRefreshService,
)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _enterprise(db):
    enterprise = EnterpriseProfile(
        name="宁德时代",
        ticker="300750.SZ",
        report_year=2026,
        industry_tag="制造业",
        exchange="SZSE",
    )
    db.add(enterprise)
    db.commit()
    db.refresh(enterprise)
    return enterprise


class FakeBoardClient:
    def __init__(self, status: str = "verified") -> None:
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def validate(self, industry_name: str, ticker: str) -> BoardValidation:
        self.calls.append((industry_name, ticker))
        return BoardValidation(status=self.status, board_code="BK1033" if self.status == "verified" else None)


class FakeAkShare:
    def __init__(self, *, peer_count: int = 7, exact_period: bool = True, fail_yjbb: bool = False) -> None:
        self.peer_count = peer_count
        self.exact_period = exact_period
        self.fail_yjbb = fail_yjbb
        self.yjbb_dates: list[str] = []

    def stock_yjbb_em(self, date: str):
        pd = pytest.importorskip("pandas")
        self.yjbb_dates.append(date)
        if self.fail_yjbb:
            raise RuntimeError("yjbb_down")
        rows = [
            {"股票代码": "300750", "股票简称": "宁德时代", "所处行业": "电池", "营业总收入-营业总收入": 9999.0, "净利润-净利润": 999.0},
            {"股票代码": "200001", "股票简称": "B股排除", "所处行业": "电池", "营业总收入-营业总收入": 99999.0, "净利润-净利润": 9999.0},
            {"股票代码": "000001", "股票简称": "重复旧值", "所处行业": "电池", "营业总收入-营业总收入": 100.0, "净利润-净利润": 10.0},
            {"股票代码": "000001", "股票简称": "重复忽略", "所处行业": "电池", "营业总收入-营业总收入": 99999.0, "净利润-净利润": 9999.0},
        ]
        rows.extend(
            {
                "股票代码": f"00000{index}",
                "股票简称": f"同行{index}",
                "所处行业": "电池",
                "营业总收入-营业总收入": float(index * 100),
                "净利润-净利润": float(index * 10),
            }
            for index in range(2, self.peer_count + 1)
        )
        rows.append({"股票代码": "600001", "股票简称": "其他行业", "所处行业": "汽车", "营业总收入-营业总收入": 99999.0, "净利润-净利润": 9999.0})
        return pd.DataFrame(rows)

    def stock_profit_sheet_by_report_em(self, symbol: str):
        pd = pytest.importorskip("pandas")
        seed = int(symbol[-1])
        current_date = "2026-03-31" if self.exact_period else "2025-12-31"
        current_revenue = float(seed * 100)
        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2025-03-31",
                    "TOTAL_OPERATE_INCOME": current_revenue * 0.8,
                    "OPERATE_COST": current_revenue * 0.5,
                    "PARENT_NETPROFIT": current_revenue * 0.08,
                },
                {
                    "REPORT_DATE": current_date,
                    "TOTAL_OPERATE_INCOME": current_revenue,
                    "OPERATE_COST": current_revenue * (0.8 - seed * 0.05),
                    "PARENT_NETPROFIT": current_revenue * (0.05 + seed * 0.01),
                    "SALE_EXPENSE": current_revenue * 0.03,
                    "MANAGE_EXPENSE": current_revenue * 0.02,
                    "RESEARCH_EXPENSE": current_revenue * 0.04,
                    "FINANCE_EXPENSE": current_revenue * 0.01,
                },
            ]
        )

    def stock_balance_sheet_by_report_em(self, symbol: str):
        pd = pytest.importorskip("pandas")
        seed = int(symbol[-1])
        current_date = "2026-03-31" if self.exact_period else "2025-12-31"
        return pd.DataFrame(
            [
                {"REPORT_DATE": "2025-12-31", "ACCOUNTS_RECE": 80.0 + seed, "INVENTORY": 100.0 + seed, "TOTAL_ASSETS": 900.0, "TOTAL_LIABILITIES": 360.0},
                {"REPORT_DATE": current_date, "ACCOUNTS_RECE": 100.0 + seed, "INVENTORY": 120.0 + seed, "TOTAL_ASSETS": 1000.0, "TOTAL_LIABILITIES": 400.0},
            ]
        )


def test_refresh_uses_yjbb_industry_filters_a_shares_and_writes_top_five_arithmetic_mean():
    db = _session()
    try:
        enterprise = _enterprise(db)
        board_client = FakeBoardClient()
        summary = IndustryBenchmarkRefreshService(ak_module=FakeAkShare(), board_client=board_client).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2026Q1",
        )

        state = db.scalar(select(IndustryBenchmarkRefreshState))
        leaders = list(db.scalars(select(IndustryLeaderCompany).order_by(IndustryLeaderCompany.rank)).all())
        gross_margin = db.scalar(select(IndustryLeaderBenchmark).where(IndustryLeaderBenchmark.metric_code == "gross_margin"))

        assert summary["ready_count"] == 1
        assert state is not None
        assert state.industry_name == "电池"
        assert state.source == "eastmoney_yjbb"
        assert state.board_code == "BK1033"
        assert state.board_validation_status == "verified"
        assert board_client.calls == [("电池", "300750")]
        assert [leader.ticker for leader in leaders] == ["000007", "000006", "000005", "000004", "000003"]
        assert "300750" not in {leader.ticker for leader in leaders}
        assert gross_margin is not None
        assert gross_margin.sample_count == 5
        assert gross_margin.leader_benchmark == pytest.approx(sum(20.0 + seed * 5.0 for seed in (7, 6, 5, 4, 3)) / 5)
    finally:
        db.close()


def test_refresh_accepts_three_leaders_and_hides_two_leaders():
    for peer_count, expected_status in ((3, "ready"), (2, "failed")):
        db = _session()
        try:
            enterprise = _enterprise(db)
            IndustryBenchmarkRefreshService(ak_module=FakeAkShare(peer_count=peer_count), board_client=FakeBoardClient("unavailable")).refresh(
                db,
                enterprise_ids=[enterprise.id],
                period="2026Q1",
            )
            state = db.scalar(select(IndustryBenchmarkRefreshState))
            assert state is not None
            assert state.status == expected_status
            if expected_status == "failed":
                assert state.error_reason == "insufficient_leader_sample"
        finally:
            db.close()


def test_refresh_requires_exact_peer_period():
    db = _session()
    try:
        enterprise = _enterprise(db)
        IndustryBenchmarkRefreshService(ak_module=FakeAkShare(exact_period=False), board_client=FakeBoardClient()).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2026Q1",
        )
        state = db.scalar(select(IndustryBenchmarkRefreshState))
        assert state is not None
        assert state.status == "failed"
        assert state.error_reason == "insufficient_leader_sample"
    finally:
        db.close()


def test_refresh_records_yjbb_failure_without_mock_fallback():
    db = _session()
    try:
        enterprise = _enterprise(db)
        summary = IndustryBenchmarkRefreshService(ak_module=FakeAkShare(fail_yjbb=True), board_client=FakeBoardClient()).refresh(
            db,
            enterprise_ids=[enterprise.id],
            period="2026Q1",
        )
        state = db.scalar(select(IndustryBenchmarkRefreshState))
        assert summary["failed_count"] == 1
        assert state is not None
        assert state.status == "failed"
        assert state.error_reason == "eastmoney_yjbb_unavailable"
    finally:
        db.close()


def test_board_validation_rotates_hosts_and_verifies_target_member():
    class RotatingClient(EastmoneyBoardValidationClient):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def _request_json(self, host: str, params: dict[str, str]):
            self.calls.append(host)
            if host == self.HOSTS[0]:
                raise RuntimeError("first_host_down")
            if params["fs"].startswith("m:90"):
                return [{"f12": "BK1033", "f14": "电池"}]
            return [{"f12": "300750", "f14": "宁德时代"}]

    client = RotatingClient()
    validation = client.validate("电池", "300750")

    assert validation == BoardValidation(status="verified", board_code="BK1033")
    assert client.calls == [client.HOSTS[0], client.HOSTS[1], client.HOSTS[1]]


def test_schema_rebuild_drops_only_industry_tables():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE industry_benchmark (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE keep_me (id INTEGER PRIMARY KEY)"))

    rebuild_industry_benchmark_schema(confirm=True, bind=engine)
    names = set(inspect(engine).get_table_names())

    assert "industry_benchmark" not in names
    assert "company_industry_mapping" not in names
    assert "industry_benchmark_refresh_state" in names
    assert "industry_leader_company" in names
    assert "industry_leader_benchmark" in names
    assert "keep_me" in names
