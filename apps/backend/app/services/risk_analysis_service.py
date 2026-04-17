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
from app.services.document_risk_service import DocumentRiskService
from app.services.feature_engineering_service import FeatureEngineeringService
from app.services.industry_benchmark_service import IndustryBenchmarkService
from app.services.industry_classifier_service import IndustryClassifierService
from app.services.tax_risk_service import TaxRiskService


logger = logging.getLogger(__name__)


class RiskAnalysisService:
    def __init__(self) -> None:
        self.feature_engineering_service = FeatureEngineeringService()
        self.rule_evaluator = RuleEvaluator()
        self.explainer = RiskExplanationService()
        self.document_risk_service = DocumentRiskService()
        self.tax_risk_service = TaxRiskService()
        self.industry_classifier = IndustryClassifierService()
        self.industry_benchmark_service = IndustryBenchmarkService(self.industry_classifier)

    def _with_builtin_context_rules(self, rules: list[AuditRule]) -> list[AuditRule]:
        existing = {rule.code for rule in rules}
        builtin_rules = []
        if "EXCESS_PROFIT_INDUSTRY_OUTLIER" not in existing:
            builtin_rules.append(
                AuditRule(
                    code="EXCESS_PROFIT_INDUSTRY_OUTLIER",
                    name="超额盈利与回款质量背离风险",
                    risk_category="财务风险",
                    risk_level="HIGH",
                    description="企业毛利率显著高于行业且应收周转弱于行业，同时现金流或应收质量出现异常。",
                    conditions={
                        "logic": "all",
                        "conditions": [{"metric": "excess_profit_risk_signal", "operator": ">=", "value": 1, "label": "毛利率高于行业且回款质量偏弱"}],
                    },
                    focus_accounts=["主营业务收入", "营业成本", "应收账款"],
                    focus_processes=["收入确认", "成本归集", "销售回款"],
                    recommended_procedures=["对比行业毛利率", "执行收入截止测试", "复核期后回款和坏账准备"],
                    evidence_types=["行业数据", "财务指标", "应收账款账龄"],
                    weight=3.4,
                    enabled=True,
                )
            )
        if "DEBT_PRESSURE_HIGH" not in existing:
            builtin_rules.append(
                AuditRule(
                    code="DEBT_PRESSURE_HIGH",
                    name="融资与偿债压力风险",
                    risk_category="财务风险",
                    risk_level="MEDIUM",
                    description="企业或行业杠杆水平偏高，需关注短期偿债压力和融资安排。",
                    conditions={
                        "logic": "any",
                        "conditions": [
                            {"metric": "short_term_debt_pressure", "operator": ">=", "value": 1, "label": "资产负债率达到高杠杆阈值"},
                            {"metric": "debt_ratio_industry_high", "operator": ">=", "value": 1, "label": "行业杠杆水平偏高"},
                        ],
                    },
                    focus_accounts=["短期借款", "长期借款", "应付债券"],
                    focus_processes=["资金计划", "融资管理", "偿债安排"],
                    recommended_procedures=["复核债务到期结构", "检查授信额度和续贷安排", "执行现金流压力测试"],
                    evidence_types=["财务指标", "授信合同", "银行流水"],
                    weight=2.8,
                    enabled=True,
                )
            )
        return [*rules, *builtin_rules]

    def _rule_weight_context(self, rule: AuditRule, features: dict) -> tuple[float, list[str]]:
        multiplier = 1.0
        reasons: list[str] = []
        industry_code = str((features.get("industry_comparison") or {}).get("industry_code") or "")
        if industry_code in {"software_service", "professional_service", "internet_platform"} and rule.code in {"AR_COLLECTION", "REV_AR_GAP", "EXCESS_PROFIT_INDUSTRY_OUTLIER"}:
            multiplier *= 1.15
            reasons.append("light_asset_industry")
        high_leverage = features.get("latest_debt_ratio", 0.0) >= 65.0 or features.get("debt_ratio_industry_high", 0.0) >= 1.0
        if high_leverage and (rule.code in {"DEBT_PRESSURE_HIGH", "FINANCING_PRESSURE", "SHORT_TERM_DEBT_PRESSURE"} or "debt" in str(rule.code or "").lower()):
            multiplier *= 1.20
            reasons.append("high_leverage_context")
        return min(multiplier, 1.30), reasons

    def _feature_snapshot_for_hit(self, features: dict, hit) -> dict:
        snapshot = dict(features)
        snapshot["score_details"] = {
            "base_score": hit.base_score,
            "final_score": hit.score,
            "effective_weight": hit.effective_weight,
            "weight_multiplier": hit.weight_multiplier,
            "weight_reasons": hit.weight_reasons,
        }
        return snapshot

    def _ensure_baseline_result(
        self,
        db: Session,
        enterprise_id: int,
        run_id: int,
        features: dict,
        financials: list,
        events: list,
        documents: list,
    ) -> None:
        if not (financials or events or documents):
            return
        if hasattr(db, "flush"):
            db.flush()
        if self.document_risk_service.list_risks(db, enterprise_id):
            return
        snapshot = dict(features)
        snapshot["score_details"] = {
            "base_score": 30.0,
            "final_score": 30.0,
            "effective_weight": 0.0,
            "weight_multiplier": 1.0,
            "weight_reasons": ["baseline_observation"],
        }
        db.add(
            RiskIdentificationResult(
                enterprise_id=enterprise_id,
                run_id=run_id,
                rule_id=None,
                rule_code=None,
                risk_name="综合风险观察",
                risk_category="baseline",
                risk_level="LOW",
                risk_score=30.0,
                source_type="baseline",
                reasons=["未触发高风险规则，但已完成基础风险评分。"],
                evidence_chain=[],
                feature_snapshot=snapshot,
                llm_summary="未触发高风险规则，建议保持常规审计关注。",
                llm_explanation="baseline 仅表示完成基础评分，不代表发现重大风险。",
            )
        )

    @staticmethod
    def get_analysis_readiness(enterprise, financials: list, events: list, documents: list) -> dict:
        if enterprise.sync_status == "syncing":
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "syncing",
                "risk_analysis_message": "官方数据同步中，请稍后刷新后再运行风险分析。",
            }
        if enterprise.sync_status == "failed":
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "failed",
                "risk_analysis_message": "最近一次官方数据同步失败，请先重新同步后再运行风险分析。",
            }
        if not documents and not events:
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "no_official_data",
                "risk_analysis_message": "当前企业暂无可用于分析的官方数据，请先同步官方公告或上传文档。",
            }
        if not financials and not events:
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "official_docs_only",
                "risk_analysis_message": "当前已同步官方文档，但缺少可用于规则分析的财务或事件结构化数据。",
            }
        return {
            "risk_analysis_ready": True,
            "risk_analysis_reason": "ready",
            "risk_analysis_message": "当前企业已满足风险分析运行条件。",
        }

    def _normalize_to_list(self, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            for sep in ["。", "，", ",", ";", "\n"]:
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
            raise ValueError("企业不存在。")

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
        documents = enterprise_repo.get_documents(enterprise_id, official_only=True)
        readiness = self.get_analysis_readiness(enterprise, financials, events, documents)
        benchmarks = list(db.scalars(select(IndustryBenchmark).where(IndustryBenchmark.source != "mock")).all())

        if not readiness["risk_analysis_ready"]:
            raise ValueError(readiness["risk_analysis_message"])

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
            industry_comparison = self.industry_benchmark_service.build_comparison(db, enterprise, financials, benchmarks)
            features = self.feature_engineering_service.build_features(financials, events, benchmarks, industry_comparison)

            risk_repo = RiskRepository(db)
            risk_repo.clear_enterprise_results(enterprise_id)
            db.execute(delete(RiskAlertRecord).where(RiskAlertRecord.enterprise_id == enterprise_id))

            rules = self._with_builtin_context_rules(list(db.scalars(select(AuditRule).where(AuditRule.enabled.is_(True))).all()))

            for rule in rules:
                multiplier, weight_reasons = self._rule_weight_context(rule, features)
                hit = self.rule_evaluator.evaluate(rule, features, context_weight_multiplier=multiplier, weight_reasons=weight_reasons)
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
                    rule_code=rule.code,
                    risk_name=rule.name,
                    risk_category=rule.risk_category,
                    risk_level=rule.risk_level,
                    risk_score=hit.score,
                    source_type="rule",
                    reasons=hit.reasons,
                    evidence_chain=hit.evidence_chain,
                    feature_snapshot=self._feature_snapshot_for_hit(features, hit),
                    llm_summary=explanation.get("summary", ""),
                    llm_explanation=self._serialize_llm_explanation(explanation.get("explanation", "")),
                )
                db.add(result)
                db.flush()

                focus_accounts = sorted(set((rule.focus_accounts or []) + audit_focus))
                recommendation_sources = self._recommendation_sources(result.source_type, result.evidence_chain)
                db.add(
                    AuditRecommendation(
                        enterprise_id=enterprise_id,
                        run_id=run.id,
                        risk_result_id=result.id,
                        priority=rule.risk_level.lower(),
                        focus_accounts=focus_accounts,
                        focus_processes=rule.focus_processes,
                        recommended_procedures=sorted(set((rule.recommended_procedures or []) + procedures)),
                        evidence_types=sorted(set((rule.evidence_types or []) + recommendation_sources)),
                        recommendation_text=f"{rule.name}：优先关注{'、'.join(focus_accounts or ['相关科目'])}。",
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

            self._persist_tax_risks(db, enterprise_id, run.id)

            self._persist_tax_risks(db, enterprise_id, run.id)

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

            self._ensure_baseline_result(db, enterprise_id, run.id, features, financials, events, documents)
            run.status = "completed"
            run.metadata_json = {"last_error": None}
            results = self.get_results(db, enterprise_id)
            run.summary = f"共识别出 {len(results)} 项风险。"
            db.commit()
            logger.info(
                "risk analysis finished enterprise_id=%s run_id=%s result_count=%s",
                enterprise_id,
                run.id,
                len(results),
            )

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
        payload = self.document_risk_service.list_risks(db, enterprise_id)
        for item in payload:
            item["evidence_chain"] = self._normalize_evidence_chain(item.get("evidence_chain") or item.get("evidence") or [])
            item["evidence"] = item["evidence_chain"]
            item["llm_explanation"] = self._deserialize_llm_explanation(item.get("llm_explanation"))
        return payload

    def _normalize_evidence_chain(self, evidence_chain: list[dict]) -> list[dict]:
        normalized = []
        for index, evidence in enumerate(evidence_chain or [], start=1):
            if evidence.get("evidence_id") and evidence.get("evidence_type") and evidence.get("title"):
                normalized.append(
                    {
                        "evidence_id": evidence.get("evidence_id") or f"E{index}",
                        "evidence_type": evidence.get("evidence_type"),
                        "source": evidence.get("source"),
                        "source_label": evidence.get("source_label"),
                        "published_at": evidence.get("published_at"),
                        "title": evidence.get("title"),
                        "snippet": evidence.get("snippet") or evidence.get("content") or "",
                        "content": evidence.get("content") or evidence.get("snippet") or "",
                        "report_period": evidence.get("report_period"),
                    }
                )
                continue
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

    def _persist_tax_risks(self, db: Session, enterprise_id: int, run_id: int) -> None:
        tax_payload = self.tax_risk_service.build_tax_risks(db, enterprise_id)
        for item in tax_payload.get("tax_risks", []):
            result = RiskIdentificationResult(
                enterprise_id=enterprise_id,
                run_id=run_id,
                rule_id=None,
                rule_code=item["rule_code"],
                risk_name=item["risk_name"],
                risk_category=item["risk_category"],
                risk_level=item["risk_level"],
                risk_score=float(item["risk_score"]),
                source_type="rule",
                reasons=list(item.get("reasons") or []),
                evidence_chain=list(item.get("evidence_chain") or []),
                feature_snapshot={
                    "tax_risk": item,
                    "tax_diagnostics": tax_payload.get("diagnostics") or {},
                },
                llm_summary=item.get("summary"),
                llm_explanation=self._serialize_llm_explanation(
                    {
                        "summary": item.get("summary"),
                        "metrics": item.get("metrics") or [],
                    }
                ),
            )
            db.add(result)
            db.flush()
            db.add(
                AuditRecommendation(
                    enterprise_id=enterprise_id,
                    run_id=run_id,
                    risk_result_id=result.id,
                    priority=str(item.get("risk_level") or "medium").lower(),
                    focus_accounts=list(item.get("focus_accounts") or []),
                    focus_processes=list(item.get("focus_processes") or []),
                    recommended_procedures=list(item.get("recommended_procedures") or []),
                    evidence_types=["risk_rule", "tax_analysis", "financial_indicator"],
                    recommendation_text=f"{item['risk_name']}：优先关注 {'、'.join(item.get('focus_accounts') or ['相关税务科目'])}。",
                )
            )
            db.add(
                RiskAlertRecord(
                    enterprise_id=enterprise_id,
                    run_id=run_id,
                    alert_type=item["risk_category"],
                    severity=item["risk_level"],
                    title=item["risk_name"],
                    content=item.get("summary") or "",
                    payload={"rule_code": item["rule_code"], "reasons": item.get("reasons") or []},
                )
            )

    @staticmethod
    def get_analysis_readiness(enterprise, financials: list, events: list, documents: list) -> dict:
        if enterprise.sync_status == "syncing":
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "syncing",
                "risk_analysis_message": "官方数据同步中，请稍后刷新后再运行风险分析。",
            }
        if enterprise.sync_status == "failed":
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "failed",
                "risk_analysis_message": "最近一次官方数据同步失败，请先重新同步后再运行风险分析。",
            }
        if not documents and not events and not financials:
            return {
                "risk_analysis_ready": False,
                "risk_analysis_reason": "no_official_data",
                "risk_analysis_message": "当前企业暂无可用于分析的官方数据，请先同步官方公告或上传文档。",
            }
        if documents and not events and not financials:
            logger.info("risk_analysis documents_only_ready enterprise_id=%s", getattr(enterprise, "id", None))
            return {
                "risk_analysis_ready": True,
                "risk_analysis_reason": "documents_only_ready",
                "risk_analysis_message": "当前可基于现有文档运行风险分析，结果将以文档抽取风险为主。",
            }
        return {
            "risk_analysis_ready": True,
            "risk_analysis_reason": "ready",
            "risk_analysis_message": "当前企业已满足风险分析运行条件。",
        }

    def run(self, db: Session, enterprise_id: int) -> dict:
        enterprise_repo = EnterpriseRepository(db)
        enterprise = enterprise_repo.get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在。")

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
        documents = enterprise_repo.get_documents(enterprise_id, official_only=True)
        readiness = self.get_analysis_readiness(enterprise, financials, events, documents)
        benchmarks = list(db.scalars(select(IndustryBenchmark).where(IndustryBenchmark.source != "mock")).all())

        if not readiness["risk_analysis_ready"]:
            raise ValueError(readiness["risk_analysis_message"])

        documents_only_mode = bool(documents) and not financials and not events
        if documents_only_mode:
            logger.info("risk_analysis documents_only_ready enterprise_id=%s", enterprise_id)

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
            industry_comparison = self.industry_benchmark_service.build_comparison(db, enterprise, financials, benchmarks)
            features = self.feature_engineering_service.build_features(financials, events, benchmarks, industry_comparison)

            risk_repo = RiskRepository(db)
            risk_repo.clear_enterprise_results(enterprise_id)
            db.execute(delete(RiskAlertRecord).where(RiskAlertRecord.enterprise_id == enterprise_id))

            rules = self._with_builtin_context_rules(list(db.scalars(select(AuditRule).where(AuditRule.enabled.is_(True))).all()))

            for rule in rules:
                multiplier, weight_reasons = self._rule_weight_context(rule, features)
                hit = self.rule_evaluator.evaluate(rule, features, context_weight_multiplier=multiplier, weight_reasons=weight_reasons)
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
                    rule_code=rule.code,
                    risk_name=rule.name,
                    risk_category=rule.risk_category,
                    risk_level=rule.risk_level,
                    risk_score=hit.score,
                    source_type="rule",
                    reasons=hit.reasons,
                    evidence_chain=hit.evidence_chain,
                    feature_snapshot=self._feature_snapshot_for_hit(features, hit),
                    llm_summary=explanation.get("summary", ""),
                    llm_explanation=self._serialize_llm_explanation(explanation.get("explanation", "")),
                )
                db.add(result)
                db.flush()

                focus_accounts = sorted(set((rule.focus_accounts or []) + audit_focus))
                recommendation_sources = self._recommendation_sources(result.source_type, result.evidence_chain)
                db.add(
                    AuditRecommendation(
                        enterprise_id=enterprise_id,
                        run_id=run.id,
                        risk_result_id=result.id,
                        priority=rule.risk_level.lower(),
                        focus_accounts=focus_accounts,
                        focus_processes=rule.focus_processes,
                        recommended_procedures=sorted(set((rule.recommended_procedures or []) + procedures)),
                        evidence_types=sorted(set((rule.evidence_types or []) + recommendation_sources)),
                        recommendation_text=f"{rule.name}：优先关注 {'、'.join(focus_accounts or ['相关科目'])}。",
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

            self._persist_tax_risks(db, enterprise_id, run.id)

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

            self._ensure_baseline_result(db, enterprise_id, run.id, features, financials, events, documents)
            run.status = "completed"
            run.metadata_json = {"last_error": None}
            results = self.get_results(db, enterprise_id)
            if documents_only_mode:
                run.summary = f"本次基于现有文档结果完成风险分析，共汇总 {len(results)} 项风险，未使用财务指标规则。"
            else:
                run.summary = f"共识别出 {len(results)} 项风险。"
            db.commit()
            logger.info(
                "risk analysis finished enterprise_id=%s run_id=%s result_count=%s",
                enterprise_id,
                run.id,
                len(results),
            )

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
