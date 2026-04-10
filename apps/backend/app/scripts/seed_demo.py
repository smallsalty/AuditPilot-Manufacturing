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
from app.services.risk_analysis_service import RiskAnalysisService
from app.utils.embeddings import HashingEmbeddingService


DOCUMENT_SEEDS = {
    "600031.SH": [
        "管理层讨论与分析：2024 年四季度海外订单集中确认，部分大型设备项目在年末集中验收，导致收入与应收账款同步上升。",
        "风险提示：若海外渠道回款节奏不及预期，公司可能面临经营现金流承压和信用减值压力。",
        "重大事项：公司持续推进关联供应链协同，部分设备租赁与零部件采购存在较多关联主体。",  # noqa: E501
    ],
    "601689.SH": [
        "管理层讨论与分析：客户平台切换和新品导入节奏放缓，导致部分产成品库存和在制品周转天数上升。",
        "风险提示：若终端需求恢复不及预期，公司可能需要加快去库存并重新评估跌价准备。",
        "重大事项：年内新增多条产线，产能爬坡与订单兑现之间存在时间差。",  # noqa: E501
    ],
    "600309.SH": [
        "管理层讨论与分析：化工价格波动和环保投入增加，对成本控制与合规管理提出更高要求。",
        "风险提示：环保执法趋严，若安全与环保整改执行不到位，可能影响产线稳定运行并带来处罚风险。",
        "重大事项：公司与供应商就原料结算条款存在争议，已启动法律程序。",  # noqa: E501
    ],
    "002475.SZ": [
        "管理层讨论与分析：公司持续推进大客户项目切换与全球产能协同，供应链管理复杂度明显提升。",
        "风险提示：若关联供应链管理和关键岗位交接控制不足，可能影响采购、结算和内控执行。",
        "重大事项：年内财务和采购负责人均发生调整，相关审批流程已启动优化。",  # noqa: E501
    ],
    "300124.SZ": [
        "管理层讨论与分析：工业自动化业务保持稳健增长，项目交付节奏总体正常，库存管理和回款表现稳定。",
        "风险提示：原材料波动和项目型交付周期变化仍需跟踪，但整体经营韧性较强。",
        "重大事项：公司继续推进工业机器人与新能源业务协同，并未披露重大诉讼处罚事项。",  # noqa: E501
    ],
}

PREBUILT_ANALYSIS_TICKERS = {"600031.SH", "601689.SH", "600309.SH", "002475.SZ"}


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

        profile_path = settings.data_root / "seeds" / "backend" / "enterprise_profiles.json"
        if profile_path.exists():
            enterprise_rows = json.loads(profile_path.read_text(encoding="utf-8"))
        else:
            enterprise_rows = [
                json.loads(
                    (settings.data_root / "seeds" / "backend" / "enterprise_profile.json").read_text(encoding="utf-8")
                )
            ]

        enterprise_map: dict[str, EnterpriseProfile] = {}
        for enterprise_data in enterprise_rows:
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
            db.flush()
            enterprise_map[enterprise.ticker] = enterprise
        db.commit()

        with (settings.data_root / "seeds" / "backend" / "financial_indicators.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                enterprise = enterprise_map.get(row["ticker"])
                if enterprise is None:
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
            enterprise = enterprise_map.get(row["ticker"])
            if enterprise is None:
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

        knowledge_rows = json.loads(
            (settings.data_root / "seeds" / "backend" / "knowledge_chunks.json").read_text(encoding="utf-8")
        )
        for row in knowledge_rows:
            target_enterprise_ids = (
                [enterprise.id for enterprise in enterprise_map.values()] if row.get("enterprise_scoped", True) else [None]
            )
            for enterprise_id in target_enterprise_ids:
                db.add(
                    KnowledgeChunk(
                        enterprise_id=enterprise_id,
                        source_type=row["source_type"],
                        source_id=None,
                        title=row["title"],
                        content=row["content"],
                        tags=row.get("tags"),
                        embedding=embedding_service.encode([row["content"]])[0],
                    )
                )

        for ticker, enterprise in enterprise_map.items():
            paragraphs = DOCUMENT_SEEDS.get(ticker, [])
            if not paragraphs:
                continue
            doc_text = "\n".join(paragraphs)
            document = DocumentMeta(
                enterprise_id=enterprise.id,
                document_name=f"{enterprise.name}年报节选.txt",
                document_type="annual_report",
                source="seed",
                parse_status="parsed",
                content_text=doc_text,
            )
            db.add(document)
            db.flush()
            for index, paragraph in enumerate(paragraphs, start=1):
                embedding = embedding_service.encode([paragraph])[0]
                db.add(
                    DocumentExtractResult(
                        document_id=document.id,
                        extract_type="risk_warning" if index == 2 else ("major_events" if index == 3 else "mda"),
                        title=f"{enterprise.name}-extract-{index}",
                        content=paragraph,
                        page_number=index,
                        keywords=["年报", "制造业", "风险提示"],
                        embedding=embedding,
                    )
                )
                db.add(
                    KnowledgeChunk(
                        enterprise_id=enterprise.id,
                        source_type="document",
                        source_id=document.id,
                        title=f"{enterprise.name}-文档片段-{index}",
                        content=paragraph,
                        tags=["年报", "风险提示"],
                        embedding=embedding,
                    )
                )
        db.commit()

        risk_service = RiskAnalysisService()
        for ticker in PREBUILT_ANALYSIS_TICKERS:
            enterprise = enterprise_map.get(ticker)
            if enterprise is None:
                continue
            risk_service.run(db, enterprise.id)
    print("Seed completed.")


if __name__ == "__main__":
    seed()
