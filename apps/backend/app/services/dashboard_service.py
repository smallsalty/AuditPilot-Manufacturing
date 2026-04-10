from collections import defaultdict

from sqlalchemy.orm import Session

from app.repositories.enterprise_repository import EnterpriseRepository
from app.repositories.risk_repository import RiskRepository
from app.services.risk_analysis_service import RiskAnalysisService


class DashboardService:
    CATEGORY_MAP = {
        "财务风险": "financial",
        "经营风险": "operational",
        "合规风险": "compliance",
        "内控风险": "compliance",
    }

    def build_dashboard(self, db: Session, enterprise_id: int) -> dict:
        enterprise_repo = EnterpriseRepository(db)
        enterprise = enterprise_repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在")
        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        results = RiskRepository(db).list_results(enterprise_id)
        score_buckets = defaultdict(list)
        for result in results:
            bucket = self.CATEGORY_MAP.get(result.risk_category, "operational")
            score_buckets[bucket].append(result.risk_score)
        financial = round(sum(score_buckets["financial"]) / max(1, len(score_buckets["financial"])), 1)
        operational = round(sum(score_buckets["operational"]) / max(1, len(score_buckets["operational"])), 1)
        compliance = round(sum(score_buckets["compliance"]) / max(1, len(score_buckets["compliance"])), 1)
        total = round((financial + operational + compliance) / 3 if results else 0, 1)
        trend = [{"report_period": f"T{idx}", "risk_score": result.risk_score} for idx, result in enumerate(results[:6], 1)]
        return {
            "enterprise": {
                "id": enterprise.id,
                "name": enterprise.name,
                "ticker": enterprise.ticker,
                "industry_tag": enterprise.industry_tag,
                "report_year": enterprise.report_year,
            },
            "score": {
                "total": total,
                "financial": financial,
                "operational": operational,
                "compliance": compliance,
            },
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "radar": [
                {"name": "财务风险", "value": financial},
                {"name": "经营风险", "value": operational},
                {"name": "合规风险", "value": compliance},
                {"name": "文本预警", "value": min(100, total + 8)},
                {"name": "规则命中", "value": min(100, len(results) * 12)},
            ],
            "trend": trend or [{"report_period": "未分析", "risk_score": 0}],
            "top_risks": [
                {
                    "id": result.id,
                    "risk_name": result.risk_name,
                    "risk_level": result.risk_level,
                    "risk_score": result.risk_score,
                    "source_type": result.source_type,
                }
                for result in results[:5]
            ],
        }
