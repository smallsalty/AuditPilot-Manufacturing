from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.models import DocumentEventFeature, DocumentExtractResult, ReviewOverride
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository
from app.repositories.risk_repository import RiskRepository
from app.utils.display_text import clean_document_title


class DocumentRiskService:
    RULE_CODE_TO_RISK_KEY = {
        "REV_Q4_SPIKE": "revenue_recognition",
        "REV_Q4_RATIO": "revenue_recognition",
        "REV_AR_GAP": "revenue_recognition",
        "CF_PROFIT_LOW": "cashflow_quality",
        "OCF_PROFIT_DIVERGENCE": "cashflow_quality",
        "INV_BACKLOG": "inventory_impairment",
        "INV_GROWTH_TURNOVER": "inventory_impairment",
        "INV_INDUSTRY_DOWN": "inventory_impairment",
        "INV_INDUSTRY_CONFLICT": "inventory_impairment",
        "AR_COLLECTION": "receivable_recoverability",
        "AR_TURNOVER_PRESSURE": "receivable_recoverability",
        "COMPLIANCE_EVENTS": "litigation_compliance",
        "OTHER_AR_ASSET_RATIO": "related_party_transaction",
        "RELATED_PARTY_CONTROL": "related_party_transaction",
        "Q4_PROFIT_DEVIATION": "revenue_recognition",
        "GM_EXPENSE_ANOMALY": "cashflow_quality",
    }
    RISK_TITLES = {
        "revenue_recognition": "收入确认与收入真实性风险",
        "receivable_recoverability": "应收账款回收与收入真实性风险",
        "inventory_impairment": "存货减值与积压风险",
        "cashflow_quality": "经营现金流与利润质量风险",
        "related_party_transaction": "关联交易与资金占用风险",
        "litigation_compliance": "诉讼处罚与合规风险",
        "internal_control_effectiveness": "内部控制有效性风险",
        "audit_opinion_issue": "审计意见异常风险",
        "going_concern": "持续经营与审计意见风险",
        "financing_pressure": "融资与资金压力风险",
        "governance_instability": "治理结构与高管稳定性风险",
        "market_signal_conflict": "市场信号背离风险",
        "uncategorized": "文档发现风险",
    }

    def list_risks(self, db: Session, enterprise_id: int) -> list[dict[str, Any]]:
        repo = EnterpriseRepository(db)
        documents = repo.get_documents(enterprise_id, official_only=True)
        document_repo = DocumentRepository(db)
        grouped: dict[str, dict[str, Any]] = {}

        for document in documents:
            extracts = document_repo.list_extracts(document.id)
            features = document_repo.list_event_features(document.id)
            for extract in extracts:
                if self._should_ignore_extract(extract):
                    continue
                self._add_extract_row(grouped, document, extract)
            for feature in features:
                self._add_feature_row(grouped, document, feature)

        persisted_results = RiskRepository(db).list_results(enterprise_id)
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)
        rec_map: dict[int, list[Any]] = defaultdict(list)
        for recommendation in recommendations:
            if recommendation.risk_result_id:
                rec_map[recommendation.risk_result_id].append(recommendation)

        for result in persisted_results:
            canonical_key = self.RULE_CODE_TO_RISK_KEY.get(result.rule_code or "", "uncategorized")
            row = grouped.setdefault(canonical_key, self._new_group(canonical_key))
            row["risk_score"] = max(row["risk_score"], float(result.risk_score or 0))
            row["summary"] = row["summary"] or (result.llm_summary or "；".join(result.reasons or []))
            row["source_mode"] = "document_plus_rule" if row["source_documents"] else "rule_only"
            row["evidence_status"] = "document_plus_rule" if row["source_documents"] else "rule_inferred"
            row["confidence_level"] = "high" if row["source_documents"] else "medium"
            row["source_rules"] = self._dedupe_strings(row["source_rules"] + ([result.rule_code] if result.rule_code else []))
            row["feature_support"].extend(
                [
                    evidence.get("metadata") or {"metric": evidence.get("title"), "value": evidence.get("content")}
                    for evidence in (result.evidence_chain or [])
                ]
            )
            row["evidence"].extend(self._normalize_rule_evidence(result.evidence_chain or []))
            for recommendation in rec_map.get(result.id, []):
                row["focus_accounts"] = self._dedupe_strings(row["focus_accounts"] + list(recommendation.focus_accounts or []))
                row["focus_processes"] = self._dedupe_strings(row["focus_processes"] + list(recommendation.focus_processes or []))
                row["recommended_procedures"] = self._dedupe_strings(row["recommended_procedures"] + list(recommendation.recommended_procedures or []))
                row["evidence_types"] = self._dedupe_strings(row["evidence_types"] + list(recommendation.evidence_types or []))

        self._apply_risk_overrides(db, enterprise_id, grouped)
        rows = [self._finalize_row(row) for row in grouped.values() if not row.get("ignored")]
        rows.sort(key=lambda item: (self._mode_rank(item["source_mode"]), -float(item.get("risk_score") or 0), item["risk_name"]))
        return rows

    def build_focus_items(self, db: Session, enterprise_id: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: list[str] = []
        for index, risk in enumerate(self.list_risks(db, enterprise_id), start=1):
            summary = str(risk.get("summary") or "").strip()
            if any(SequenceMatcher(None, summary, other).ratio() >= 0.88 for other in seen):
                continue
            seen.append(summary)
            evidence_preview = [item.get("snippet") or item.get("content") or "" for item in (risk.get("evidence") or []) if item.get("snippet") or item.get("content")]
            items.append(
                {
                    "id": f"focus-{index}",
                    "title": risk["risk_name"],
                    "summary": summary,
                    "sources": self._dedupe_strings(
                        [risk.get("evidence_status")]
                        + list(risk.get("source_rules") or [])
                        + [item.get("document_name") for item in (risk.get("source_documents") or [])]
                    ),
                    "evidence_preview": [item[:140] for item in evidence_preview[:2]],
                    "expanded_sections": [
                        {
                            "title": "建议关注",
                            "items": self._dedupe_strings(
                                list(risk.get("recommended_procedures") or [])
                                + list(risk.get("focus_accounts") or [])
                                + list(risk.get("focus_processes") or [])
                            )[:4],
                        }
                    ],
                }
            )
        return items[:8]

    def _new_group(self, canonical_key: str) -> dict[str, Any]:
        return {
            "canonical_risk_key": canonical_key,
            "risk_name": self.RISK_TITLES.get(canonical_key, self.RISK_TITLES["uncategorized"]),
            "risk_category": "document_risk",
            "risk_level": "MEDIUM",
            "risk_score": 0.0,
            "source_type": "document_rule",
            "source_mode": "document_primary",
            "evidence_status": "document_supported",
            "confidence_level": "medium",
            "summary": "",
            "reasons": [],
            "evidence": [],
            "source_rules": [],
            "source_documents": [],
            "source_events": [],
            "feature_support": [],
            "focus_accounts": [],
            "focus_processes": [],
            "recommended_procedures": [],
            "evidence_types": [],
            "ignored": False,
        }

    def _add_extract_row(self, grouped: dict[str, dict[str, Any]], document: Any, extract: DocumentExtractResult) -> None:
        canonical_key = extract.canonical_risk_key or "uncategorized"
        row = grouped.setdefault(canonical_key, self._new_group(canonical_key))
        row["risk_score"] = max(row["risk_score"], self._score_extract(extract))
        row["risk_level"] = self._max_level(row["risk_level"], self._extract_level(extract))
        row["summary"] = row["summary"] or (extract.problem_summary or extract.evidence_excerpt or extract.title)
        row["reasons"] = self._dedupe_strings(row["reasons"] + self._extract_risk_points(extract))
        row["source_rules"] = self._dedupe_strings(row["source_rules"] + list(extract.applied_rules or []))
        row["source_documents"] = self._dedupe_documents(
            row["source_documents"] + [{"document_id": document.id, "document_name": clean_document_title(document.document_name)}]
        )
        row["feature_support"] = self._dedupe_feature_support(
            row["feature_support"]
            + [
                {
                    "metric": extract.metric_name,
                    "value": extract.metric_value,
                    "unit": extract.metric_unit,
                    "period": extract.period,
                }
            ]
        )
        row["evidence"].append(
            {
                "evidence_id": extract.evidence_span_id or f"D{extract.id}",
                "evidence_type": "announcement" if document.source == "cninfo" else "uploaded_document",
                "source": document.source,
                "source_label": clean_document_title(document.document_name),
                "published_at": document.announcement_date.isoformat() if document.announcement_date else None,
                "title": extract.title,
                "snippet": extract.evidence_excerpt or extract.problem_summary or extract.title,
                "content": extract.evidence_excerpt or extract.problem_summary or extract.title,
                "report_period": extract.period or document.report_period_label,
                "section_title": extract.section_title,
                "page_start": extract.page_start,
                "page_end": extract.page_end,
            }
        )

    def _add_feature_row(self, grouped: dict[str, dict[str, Any]], document: Any, feature: DocumentEventFeature) -> None:
        canonical_key = feature.canonical_risk_key or "uncategorized"
        row = grouped.setdefault(canonical_key, self._new_group(canonical_key))
        row["risk_score"] = max(row["risk_score"], 78.0 if feature.feature_type == "event" else 74.0)
        row["risk_level"] = self._max_level(row["risk_level"], "HIGH" if feature.severity == "high" else "MEDIUM")
        row["summary"] = row["summary"] or (feature.conclusion or feature.conditions or feature.subject or row["risk_name"])
        row["source_documents"] = self._dedupe_documents(
            row["source_documents"] + [{"document_id": document.id, "document_name": clean_document_title(document.document_name)}]
        )
        row["source_events"] = self._dedupe_events(
            row["source_events"]
            + [
                {
                    "event_type": feature.event_type or feature.opinion_type,
                    "event_date": feature.event_date.isoformat() if feature.event_date else None,
                    "severity": feature.severity,
                    "subject": clean_document_title(feature.subject),
                }
            ]
        )
        row["evidence"].append(
            {
                "evidence_id": f"F{feature.id}",
                "evidence_type": "announcement",
                "source": document.source,
                "source_label": clean_document_title(document.document_name),
                "published_at": feature.event_date.isoformat() if feature.event_date else None,
                "title": feature.event_type or feature.opinion_type or row["risk_name"],
                "snippet": feature.conditions or feature.conclusion or clean_document_title(feature.subject) or "",
                "content": feature.conditions or feature.conclusion or clean_document_title(feature.subject) or "",
                "report_period": feature.period,
            }
        )
        row["feature_support"] = self._dedupe_feature_support(
            row["feature_support"]
            + [
                {
                    "metric": feature.metric_name,
                    "value": feature.metric_value,
                    "unit": feature.metric_unit,
                    "period": feature.period,
                }
            ]
        )

    def _apply_risk_overrides(self, db: Session, enterprise_id: int, grouped: dict[str, dict[str, Any]]) -> None:
        overrides = DocumentRepository(db).list_overrides(enterprise_id=enterprise_id, scope="risk")
        for override in overrides:
            row = grouped.get(override.target_key)
            if row is None:
                continue
            if override.override_value.get("ignored") is True:
                row["ignored"] = True
            merge_to = override.override_value.get("merge_to_key")
            if merge_to and merge_to != override.target_key:
                target = grouped.setdefault(str(merge_to), self._new_group(str(merge_to)))
                target["summary"] = target["summary"] or row["summary"]
                target["risk_score"] = max(target["risk_score"], row["risk_score"])
                if "rule_only" in {target["source_mode"], row["source_mode"]}:
                    target["source_mode"] = "document_plus_rule" if target["source_documents"] or row["source_documents"] else "rule_only"
                target["evidence_status"] = "document_plus_rule" if row["source_mode"] != "document_primary" else target["evidence_status"]
                target["source_rules"] = self._dedupe_strings(target["source_rules"] + row["source_rules"])
                target["source_documents"] = self._dedupe_documents(target["source_documents"] + row["source_documents"])
                target["source_events"] = self._dedupe_events(target["source_events"] + row["source_events"])
                target["feature_support"] = self._dedupe_feature_support(target["feature_support"] + row["feature_support"])
                target["evidence"].extend(row["evidence"])
                row["ignored"] = True

    def _normalize_rule_evidence(self, evidence_chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for index, evidence in enumerate(evidence_chain, start=1):
            normalized.append(
                {
                    "evidence_id": evidence.get("evidence_id") or f"R{index}",
                    "evidence_type": "financial_indicator",
                    "source": evidence.get("source"),
                    "source_label": evidence.get("source_label") or "财务指标",
                    "published_at": evidence.get("published_at") or evidence.get("report_period"),
                    "title": evidence.get("title") or f"规则证据 {index}",
                    "snippet": evidence.get("snippet") or evidence.get("content") or "",
                    "content": evidence.get("content") or evidence.get("snippet") or "",
                    "report_period": evidence.get("report_period"),
                }
            )
        return normalized

    def _score_extract(self, extract: DocumentExtractResult) -> float:
        score = 70.0
        if extract.detail_level == "financial_deep_dive":
            score += 8.0
        score += min(len(extract.applied_rules or []) * 4.0, 12.0)
        score += min(len(self._extract_risk_points(extract)) * 2.0, 8.0)
        return min(score, 95.0)

    def _extract_level(self, extract: DocumentExtractResult) -> str:
        text = " ".join([extract.problem_summary or "", *self._extract_risk_points(extract)])
        if extract.detail_level == "financial_deep_dive" or any(token in text for token in ("重大", "处罚", "诉讼", "缺陷", "异常")):
            return "HIGH"
        return "MEDIUM"

    def _extract_risk_points(self, extract: DocumentExtractResult) -> list[str]:
        payload = self._extract_payload(extract)
        points = payload.get("risk_points") or []
        return [str(item).strip() for item in points if str(item).strip()]

    def _extract_payload(self, extract: DocumentExtractResult) -> dict[str, Any]:
        try:
            payload = json.loads(extract.content or "{}")
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _should_ignore_extract(self, extract: DocumentExtractResult) -> bool:
        summary = str(extract.problem_summary or extract.evidence_excerpt or extract.title or "").strip()
        if not summary:
            return True
        if self._looks_like_noise(summary):
            return True
        if (
            len(summary) <= 10
            and not extract.canonical_risk_key
            and not extract.event_type
            and not extract.opinion_type
            and not extract.metric_name
            and not list(extract.applied_rules or [])
            and not list(extract.fact_tags or [])
        ):
            return True
        if (
            not extract.canonical_risk_key
            and not extract.event_type
            and not extract.opinion_type
            and not extract.metric_name
            and not list(extract.applied_rules or [])
            and not list(extract.fact_tags or [])
            and self._looks_like_noise(str(extract.title or ""))
        ):
            return True
        return False

    def _looks_like_noise(self, text: str) -> bool:
        stripped = text.strip("：:。.;； ")
        if not stripped:
            return True
        if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", stripped):
            return True
        if re.fullmatch(r"[\u4e00-\u9fa5·]{1,8}\s+[\u4e00-\u9fa5·]{1,8}\s+\d{4}年\d{1,2}月\d{1,2}日", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,30}股份有限公司", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,30}股份有限公司全体股东", stripped):
            return True
        if re.fullmatch(r"[^，。；]{2,40}（\d{4}）[^，。；]{0,20}号", stripped):
            return True
        if stripped in {"董事会的责任", "管理层的责任", "我们的责任"}:
            return True
        return False

    def _finalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["id"] = int(hashlib.sha1(str(row["canonical_risk_key"]).encode("utf-8")).hexdigest()[:8], 16)
        row["evidence"] = row["evidence"][:6]
        row["evidence_chain"] = row["evidence"]
        row["focus_accounts"] = self._dedupe_strings(row["focus_accounts"])
        row["focus_processes"] = self._dedupe_strings(row["focus_processes"])
        row["recommended_procedures"] = self._dedupe_strings(row["recommended_procedures"])
        row["evidence_types"] = self._dedupe_strings(row["evidence_types"])
        return row

    def _mode_rank(self, mode: str) -> int:
        return {"document_primary": 0, "document_plus_rule": 1, "rule_only": 2}.get(mode, 9)

    def _max_level(self, left: str, right: str) -> str:
        order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    def _dedupe_strings(self, values: list[str | None]) -> list[str]:
        items: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in items:
                items.append(text)
        return items

    def _dedupe_documents(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, Any]] = set()
        items: list[dict[str, Any]] = []
        for value in values:
            key = (value.get("document_id"), value.get("document_name"))
            if key in seen:
                continue
            seen.add(key)
            items.append(value)
        return items

    def _dedupe_events(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, Any, Any]] = set()
        items: list[dict[str, Any]] = []
        for value in values:
            key = (value.get("event_type"), value.get("event_date"), value.get("subject"))
            if key in seen:
                continue
            seen.add(key)
            items.append(value)
        return items

    def _dedupe_feature_support(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for value in values:
            if not value.get("metric"):
                continue
            if value not in items:
                items.append(value)
        return items
