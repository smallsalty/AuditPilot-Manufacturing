import csv
from datetime import date

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EnterpriseProfile, ExternalEvent, FinancialIndicator, IndustryBenchmark, MacroIndicator
from app.providers import AkshareFinancialProvider, MockCorporateRiskProvider, MockFinancialProvider


class IngestionService:
    def __init__(self) -> None:
        self.financial_providers = {
            "akshare": AkshareFinancialProvider(),
            "mock": MockFinancialProvider(),
        }
        self.risk_providers = {"mock": MockCorporateRiskProvider()}

    def ingest_financials(
        self,
        db: Session,
        enterprise: EnterpriseProfile,
        provider_name: str,
        include_quarterly: bool,
        force_seed_fallback: bool = False,
    ) -> tuple[int, str]:
        provider = self.financial_providers["mock"] if force_seed_fallback else self.financial_providers.get(provider_name)
        if provider is None:
            raise ValueError(f"未知财务 provider: {provider_name}")

        rows = provider.fetch_financials(enterprise.ticker, include_quarterly=include_quarterly)
        if not rows:
            raise ValueError("当前企业尚未获取到可用的官方财务数据，请先同步或检查 AkShare 数据源。")

        db.execute(delete(FinancialIndicator).where(FinancialIndicator.enterprise_id == enterprise.id))
        for row in rows:
            db.add(
                FinancialIndicator(
                    enterprise_id=enterprise.id,
                    period_type=row["period_type"],
                    report_period=str(row["report_period"]),
                    report_year=int(row["report_year"]),
                    report_quarter=int(row["report_quarter"]) if row.get("report_quarter") not in ("", None) else None,
                    indicator_code=row["indicator_code"],
                    indicator_name=row["indicator_name"],
                    value=float(row["value"]),
                    unit=row.get("unit"),
                    source=row.get("source", provider.provider_name),
                )
            )
        db.commit()
        return len(rows), provider.provider_name

    def ingest_risk_events(self, db: Session, enterprise: EnterpriseProfile, provider_name: str) -> tuple[int, str]:
        provider = self.risk_providers.get(provider_name)
        if provider is None:
            raise ValueError(f"未知风险 provider: {provider_name}")
        rows = provider.fetch_risk_events(enterprise.ticker)
        db.execute(delete(ExternalEvent).where(ExternalEvent.enterprise_id == enterprise.id))
        for row in rows:
            event_date = date.fromisoformat(row["event_date"]) if row.get("event_date") else None
            db.add(
                ExternalEvent(
                    enterprise_id=enterprise.id,
                    event_type=row["event_type"],
                    severity=row["severity"],
                    title=row["title"],
                    event_date=event_date,
                    source=row.get("source", provider.provider_name),
                    summary=row["summary"],
                    payload=row.get("payload"),
                )
            )
        db.commit()
        return len(rows), provider.provider_name

    def ingest_macro(self, db: Session, industry_tag: str) -> int:
        macro_file = settings.data_root / "mock" / "macro" / "macro_indicators.csv"
        benchmark_file = settings.data_root / "mock" / "macro" / "industry_benchmark.csv"
        db.execute(delete(MacroIndicator))
        db.execute(delete(IndustryBenchmark).where(IndustryBenchmark.industry_tag == industry_tag))
        inserted = 0
        with open(macro_file, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                db.add(
                    MacroIndicator(
                        indicator_name=row["indicator_name"],
                        indicator_code=row["indicator_code"],
                        report_period=row["report_period"],
                        value=float(row["value"]),
                        unit=row.get("unit"),
                        source=row.get("source", "mock"),
                    )
                )
                inserted += 1
        with open(benchmark_file, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row["industry_tag"] != industry_tag:
                    continue
                db.add(
                    IndustryBenchmark(
                        industry_tag=row["industry_tag"],
                        report_period=row["report_period"],
                        metric_code=row["metric_code"],
                        metric_name=row["metric_name"],
                        value=float(row["value"]),
                        source=row.get("source", "mock"),
                    )
                )
                inserted += 1
        db.commit()
        return inserted
