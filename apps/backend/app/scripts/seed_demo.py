import csv
import json
from datetime import date

from sqlalchemy import delete

from app.core.config import settings
from app.core.db import SessionLocal, create_all
from app.models import (
    AnalysisRun,
    AuditChatRecord,
    AuditRecommendation,
    AuditRule,
    BusinessTransaction,
    DocumentExtractResult,
    DocumentMeta,
    EnterpriseProfile,
    ExternalEvent,
    FinancialIndicator,
    IndustryBenchmark,
    KnowledgeChunk,
    MacroIndicator,
    RiskAlertRecord,
    RiskIdentificationResult,
)
from app.utils.embeddings import HashingEmbeddingService


def seed() -> None:
    create_all()
    embedding_service = HashingEmbeddingService()
    with SessionLocal() as db:
        db.execute(delete(AuditChatRecord))
        db.execute(delete(AuditRecommendation))
        db.execute(delete(RiskAlertRecord))
        db.execute(delete(RiskIdentificationResult))
        db.execute(delete(AnalysisRun))
        db.execute(delete(BusinessTransaction))
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(DocumentExtractResult))
        db.execute(delete(DocumentMeta))
        db.execute(delete(ExternalEvent))
        db.execute(delete(FinancialIndicator))
        db.execute(delete(AuditRule))
        db.execute(delete(IndustryBenchmark))
        db.execute(delete(MacroIndicator))
        db.execute(delete(EnterpriseProfile))
        db.commit()

        enterprise_data = json.loads(
            (settings.data_root / "seeds" / "backend" / "enterprise_profile.json").read_text(encoding="utf-8")
        )
        enterprise = EnterpriseProfile(
            name=enterprise_data["name"],
            ticker=enterprise_data["ticker"],
            report_year=enterprise_data["report_year"],
            industry_tag=enterprise_data["industry_tag"],
            sub_industry=enterprise_data.get("sub_industry"),
            exchange=enterprise_data.get("exchange", "SSE"),
            province=enterprise_data.get("province"),
            city=enterprise_data.get("city"),
            listed_date=date.fromisoformat(enterprise_data["listed_date"]),
            employee_count=enterprise_data.get("employee_count"),
            description=enterprise_data.get("description"),
            portrait=enterprise_data.get("portrait"),
        )
        db.add(enterprise)
        db.commit()
        db.refresh(enterprise)

        with (settings.data_root / "seeds" / "backend" / "financial_indicators.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row["ticker"] != enterprise.ticker:
                    continue
                db.add(
                    FinancialIndicator(
                        enterprise_id=enterprise.id,
                        period_type=row["period_type"],
                        report_period=row["report_period"],
                        report_year=int(row["report_year"]),
                        report_quarter=int(row["report_quarter"]) if row["report_quarter"] else None,
                        indicator_code=row["indicator_code"],
                        indicator_name=row["indicator_name"],
                        value=float(row["value"]),
                        unit=row.get("unit"),
                        source=row.get("source", "seed"),
                    )
                )

        event_rows = json.loads((settings.data_root / "mock" / "corporate" / "risk_events.json").read_text(encoding="utf-8"))
        for row in event_rows:
            if row["ticker"] != enterprise.ticker:
                continue
            db.add(
                ExternalEvent(
                    enterprise_id=enterprise.id,
                    event_type=row["event_type"],
                    severity=row["severity"],
                    title=row["title"],
                    event_date=date.fromisoformat(row["event_date"]) if row.get("event_date") else None,
                    source=row.get("source", "mock"),
                    summary=row["summary"],
                    payload=row.get("payload"),
                )
            )

        rules = json.loads((settings.data_root / "seeds" / "backend" / "audit_rules.json").read_text(encoding="utf-8"))
        for rule in rules:
            db.add(AuditRule(**rule))

        with (settings.data_root / "mock" / "macro" / "macro_indicators.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
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

        with (settings.data_root / "mock" / "macro" / "industry_benchmark.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
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

        doc_text = (settings.data_root / "mock" / "documents" / "sany_annual_report_excerpt.txt").read_text(
            encoding="utf-8"
        )
        document = DocumentMeta(
            enterprise_id=enterprise.id,
            document_name="三一重工年报节选.txt",
            document_type="annual_report",
            source="seed",
            parse_status="parsed",
            content_text=doc_text,
        )
        db.add(document)
        db.flush()

        knowledge_rows = json.loads(
            (settings.data_root / "seeds" / "backend" / "knowledge_chunks.json").read_text(encoding="utf-8")
        )
        for row in knowledge_rows:
            db.add(
                KnowledgeChunk(
                    enterprise_id=enterprise.id if row.get("enterprise_scoped", True) else None,
                    source_type=row["source_type"],
                    source_id=document.id if row["source_type"] == "document" else None,
                    title=row["title"],
                    content=row["content"],
                    tags=row.get("tags"),
                    embedding=embedding_service.encode([row["content"]])[0],
                )
            )
        db.commit()
    print("Seed completed.")


if __name__ == "__main__":
    seed()
