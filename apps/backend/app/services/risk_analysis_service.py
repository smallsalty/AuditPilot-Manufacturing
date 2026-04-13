import json
import logging
from collections import defaultdict
from datetime import datetime

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.risk_explanation_service import RiskExplanationService
from app.models import (
    AnalysisRun,
    AuditRecommendation,
    AuditRule,
    IndustryBenchmark,
    RiskAlertRecord,
    RiskIdentificationResult,
)
from app.repositories.enterprise_repository import EnterpriseRepository
from app.repositories.risk_repository import RiskRepository
from app.rule_engine.evaluator import RuleEvaluator
from app.services.feature_engineering_service import FeatureEngineeringService


logger = logging.getLogger(__name__)


class RiskAnalysisService:
    def __init__(self) -> None:
        self.feature_engineering_service = FeatureEngineeringService()
        self.rule_evaluator = RuleEvaluator()
        self.explainer = RiskExplanationService()

    def _normalize_to_list(self, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            for sep in ["、", "，", ",", ";", "；", "\n"]:
                if sep in value:
                    return [item.strip() for item in value.split(sep) if item.strip()]
            return [value]
        text = str(value).strip()
        return [text] if text else []

    def _serialize_llm_explanation(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    def _deserialize_llm_explanation(self, value):
        if value is None or not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except Exception:
            return value

    def get_analysis_state(self, db: Session, enterprise_id: int) -> dict:
        run = EnterpriseRepository(db).get_latest_analysis_run(enterprise_id)
        if run is None:
            return {
                "analysis_status": "not_started",
                "last_run_at": None,
                "last_error": None,
            }
        metadata = run.metadata_json or {}
        last_run_at = run.updated_at or run.created_at
        return {
            "analysis_status": run.status,
            "last_run_at": last_run_at.isoformat() if isinstance(last_run_at, datetime) else None,
            "last_error": metadata.get("last_error"),
        }

    def run(self, db: Session, enterprise_id: int) -> dict:
        enterprise_repo = EnterpriseRepository(db)
        enterprise = enterprise_repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在")

        latest_run = enterprise_repo.get_latest_analysis_run(enterprise_id)
        if latest_run and latest_run.status == "running":
            return {
                "run_id": latest_run.id,
                "status": "running",
                "summary": latest_run.summary or "风险分析任务仍在执行中，请稍后刷新。",
                "results": self.get_results(db, enterprise_id),
            }

        financials = enterprise_repo.get_financials(enterprise_id, official_only=True)
        events = enterprise_repo.get_external_events(enterprise_id, official_only=True)
        benchmarks = list(
            db.scalars(
                select(IndustryBenchmark).where(
                    IndustryBenchmark.industry_tag == enterprise.industry_tag,
                    IndustryBenchmark.source != "mock",
                )
            ).all()
        )

        if not financials and not events:
            raise ValueError("当前企业尚无可用于分析的官方数据，请先同步源数据或上传文档。")

        run = AnalysisRun(
            enterprise_id=enterprise_id,
            status="running",
            trigger_source="manual",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        logger.info("risk analysis started enterprise_id=%s run_id=%s", enterprise_id, run.id)

        try:
            features = self.feature_engineering_service.build_features(financials, events, benchmarks)

            risk_repo = RiskRepository(db)
            risk_repo.clear_enterprise_results(enterprise_id)
            db.execute(delete(RiskAlertRecord).where(RiskAlertRecord.enterprise_id == enterprise_id))

            rules = list(db.scalars(select(AuditRule).where(AuditRule.enabled.is_(True))).all())

            for rule in rules:
                hit = self.rule_evaluator.evaluate(rule, features)
                if hit is None:
                    continue

                payload = {
                    "risk_name": rule.name,
                    "risk_category": rule.risk_category,
                    "reasons": hit.reasons,
                    "evidence_chain": hit.evidence_chain,
                }
                explanation = self.explainer.explain_risk(enterprise.name, payload)

                audit_focus = self._normalize_to_list(explanation.get("audit_focus"))
                procedures = self._normalize_to_list(explanation.get("procedures"))

                result = RiskIdentificationResult(
                    enterprise_id=enterprise_id,
                    run_id=run.id,
                    rule_id=rule.id,
                    risk_name=rule.name,
                    risk_category=rule.risk_category,
                    risk_level=rule.risk_level,
                    risk_score=hit.score,
                    source_type="rule",
                    reasons=hit.reasons,
                    evidence_chain=hit.evidence_chain,
                    feature_snapshot=features,
                    llm_summary=explanation.get("summary", ""),
                    llm_explanation=self._serialize_llm_explanation(explanation.get("explanation", "")),
                )
                db.add(result)
                db.flush()

                recommendation_sources = self._recommendation_sources(result.source_type, result.evidence_chain)
                db.add(
                    AuditRecommendation(
                        enterprise_id=enterprise_id,
                        run_id=run.id,
                        risk_result_id=result.id,
                        priority=rule.risk_level.lower(),
                        focus_accounts=sorted(set((rule.focus_accounts or []) + audit_focus)),
                        focus_processes=rule.focus_processes,
                        recommended_procedures=sorted(set((rule.recommended_procedures or []) + procedures)),
                        evidence_types=sorted(set((rule.evidence_types or []) + recommendation_sources)),
                        recommendation_text=f"{rule.name}：优先关注 {'、'.join(rule.focus_accounts or []) or '相关科目'}。",
                    )
                )

                db.add(
                    RiskAlertRecord(
                        enterprise_id=enterprise_id,
                        run_id=run.id,
                        alert_type=rule.risk_category,
                        severity=rule.risk_level,
                        title=rule.name,
                        content=explanation.get("summary", ""),
                        payload={"reasons": hit.reasons},
                    )
                )

            anomaly = self._run_anomaly_detection(enterprise_id, run.id, features, financials)
            if anomaly:
                db.add(anomaly)
                db.flush()
                db.add(
                    AuditRecommendation(
                        enterprise_id=enterprise_id,
                        run_id=run.id,
                        risk_result_id=anomaly.id,
                        priority="medium",
                        focus_accounts=["主营业务收入", "应收账款", "存货"],
                        focus_processes=["经营分析", "期末结账"],
                        recommended_procedures=[
                            "实施趋势分析",
                            "复核异常波动原因",
                            "结合行业数据执行敏感性分析",
                        ],
                        evidence_types=["financial_anomaly", "industry_signal", "management_interview"],
                        recommendation_text="模型识别到关键指标与历史轨迹明显偏离，建议优先执行趋势复核与管理层访谈。",
                    )
                )

            run.status = "completed"
            run.metadata_json = {"last_error": None}
            results = self.get_results(db, enterprise_id)
            run.summary = f"共识别 {len(results)} 项风险。"
            db.commit()
            logger.info("risk analysis finished enterprise_id=%s run_id=%s result_count=%s", enterprise_id, run.id, len(results))

            return {
                "run_id": run.id,
                "status": run.status,
                "summary": run.summary,
                "results": results,
            }
        except Exception as exc:
            db.rollback()
            run = db.get(AnalysisRun, run.id)
            if run is None:
                raise
            run.status = "failed"
            run.summary = "风险分析执行失败。"
            run.metadata_json = {"last_error": str(exc)}
            db.commit()
            logger.warning("risk analysis failed enterprise_id=%s run_id=%s error=%s", enterprise_id, run.id, exc)
            raise

    def get_results(self, db: Session, enterprise_id: int) -> list[dict]:
        results = RiskRepository(db).list_results(enterprise_id)
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)

        rec_map = defaultdict(list)
        for recommendation in recommendations:
            if recommendation.risk_result_id:
                rec_map[recommendation.risk_result_id].append(recommendation)

        payload = []
        for result in results:
            recs = rec_map.get(result.id, [])
            payload.append(
                {
                    "id": result.id,
                    "risk_name": result.risk_name,
                    "risk_category": result.risk_category,
                    "risk_level": result.risk_level,
                    "risk_score": result.risk_score,
                    "source_type": result.source_type,
                    "reasons": result.reasons,
                    "evidence_chain": self._normalize_evidence_chain(result.evidence_chain),
                    "llm_summary": result.llm_summary,
                    "llm_explanation": self._deserialize_llm_explanation(result.llm_explanation),
                    "focus_accounts": sorted({item for rec in recs for item in (rec.focus_accounts or [])}),
                    "focus_processes": sorted({item for rec in recs for item in (rec.focus_processes or [])}),
                    "recommended_procedures": sorted(
                        {item for rec in recs for item in (rec.recommended_procedures or [])}
                    ),
                    "evidence_types": sorted({item for rec in recs for item in (rec.evidence_types or [])}),
                }
            )
        return payload

    def _normalize_evidence_chain(self, evidence_chain: list[dict]) -> list[dict]:
        normalized = []
        for index, evidence in enumerate(evidence_chain or [], start=1):
            source = str(evidence.get("source") or "")
            evidence_type = self._map_evidence_type(evidence.get("type"), source)
            normalized.append(
                {
                    "evidence_id": f"E{index}",
                    "evidence_type": evidence_type,
                    "source": source or None,
                    "source_label": self._source_label(source, evidence_type),
                    "published_at": evidence.get("report_period"),
                    "title": evidence.get("title") or f"证据 {index}",
                    "snippet": evidence.get("content") or "",
                    "content": evidence.get("content") or "",
                    "report_period": evidence.get("report_period"),
                }
            )
        return normalized

    def _recommendation_sources(self, source_type: str, evidence_chain: list[dict]) -> list[str]:
        sources = set()
        if source_type == "rule":
            sources.add("risk_rule")
        if source_type == "model":
            sources.add("financial_anomaly")
        for evidence in evidence_chain or []:
            mapped = self._map_evidence_type(evidence.get("type"), str(evidence.get("source") or ""))
            if mapped == "announcement":
                sources.add("announcement_event")
            elif mapped == "penalty":
                sources.add("penalty_event")
            elif mapped == "uploaded_document":
                sources.add("uploaded_document")
        return sorted(sources)

    def _map_evidence_type(self, raw_type: str | None, source: str) -> str:
        if source == "cninfo":
            return "announcement"
        if source == "upload":
            return "uploaded_document"
        if raw_type == "model":
            return "derived_risk_result"
        if raw_type == "industry":
            return "industry_signal"
        return "financial_indicator"

    def _source_label(self, source: str, evidence_type: str) -> str:
        if source == "cninfo":
            return "巨潮资讯"
        if source == "upload":
            return "上传文档"
        if evidence_type == "industry_signal":
            return "行业信号"
        if evidence_type == "derived_risk_result":
            return "模型结果"
        return "财务指标"

    def _run_anomaly_detection(
        self,
        enterprise_id: int,
        run_id: int,
        features: dict,
        financials: list,
    ) -> RiskIdentificationResult | None:
        rows = defaultdict(dict)
        for item in financials:
            if item.period_type != "annual":
                continue
            rows[item.report_year][item.indicator_code] = item.value

        if len(rows) < 3:
            return None

        years = sorted(rows.keys())
        matrix = []
        for year in years:
            row = rows[year]
            matrix.append(
                [
                    row.get("revenue", 0.0),
                    row.get("net_profit", 0.0),
                    row.get("operating_cash_flow", 0.0),
                    row.get("accounts_receivable", 0.0),
                    row.get("inventory", 0.0),
                ]
            )

        model = IsolationForest(random_state=42, contamination=0.34)
        predictions = model.fit_predict(np.array(matrix))
        if predictions[-1] != -1:
            return None

        return RiskIdentificationResult(
            enterprise_id=enterprise_id,
            run_id=run_id,
            rule_id=None,
            risk_name="数值异常波动风险",
            risk_category="经营风险",
            risk_level="MEDIUM",
            risk_score=68.0,
            source_type="model",
            reasons=["IsolationForest 识别出最新年度财务结构与历史样本差异较大。"],
            evidence_chain=[
                {
                    "type": "model",
                    "title": "IsolationForest 异常检测",
                    "content": "模型识别到最新年度关键财务指标存在异常波动。",
                    "source": "isolation_forest",
                    "report_period": str(int(features.get("latest_year", 0))),
                    "metadata": {"features": matrix[-1]},
                }
            ],
            feature_snapshot=features,
            llm_summary="模型检测到最新年度关键指标与历史轨迹偏离，建议结合经营背景复核。",
            llm_explanation="该异常并不直接等同于错报，但提示需要对收入、存货和现金流的组合变化执行进一步分析。",
        )
