from __future__ import annotations

import json
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditRule, DocumentMeta
from app.repositories.document_repository import DocumentRepository
from app.repositories.enterprise_repository import EnterpriseRepository
from app.repositories.risk_repository import RiskRepository


class DocumentRiskService:
    def list_risks(self, db: Session, enterprise_id: int) -> list[dict[str, Any]]:
        documents = EnterpriseRepository(db).get_documents(enterprise_id, official_only=True)
        extracts_by_document = {
            document.id: DocumentRepository(db).list_extracts(document.id)
            for document in documents
            if document.id is not None
        }
        persisted_results = RiskRepository(db).list_results(enterprise_id)
        recommendations = RiskRepository(db).list_recommendations(enterprise_id)
        rec_map: dict[int, list[Any]] = defaultdict(list)
        for recommendation in recommendations:
            if recommendation.risk_result_id:
                rec_map[recommendation.risk_result_id].append(recommendation)

        document_rows = self._build_document_risks(documents, extracts_by_document)
        merged: list[dict[str, Any]] = []
        used_document_keys: set[str] = set()

        for result in persisted_results:
            matching_document = self._find_matching_document_risk(result.risk_name, document_rows)
            source_rules = matching_document["source_rules"] if matching_document else []
            source_documents = matching_document["source_documents"] if matching_document else []
            summary = matching_document["summary"] if matching_document else (result.llm_summary or "；".join(result.reasons))
            evidence_chain = list(result.evidence_chain or [])
            if matching_document:
                evidence_chain.extend(matching_document["evidence"])
                used_document_keys.add(matching_document["merge_key"])
            merged.append(
                {
                    "id": result.id,
                    "risk_name": result.risk_name,
                    "risk_category": result.risk_category,
                    "risk_level": result.risk_level,
                    "risk_score": result.risk_score,
                    "source_type": result.source_type,
                    "source_mode": "hybrid" if matching_document else "risk_analysis",
                    "reasons": result.reasons,
                    "summary": summary,
                    "evidence_chain": evidence_chain,
                    "evidence": evidence_chain,
                    "source_rules": source_rules,
                    "source_documents": source_documents,
                    "llm_summary": result.llm_summary,
                    "llm_explanation": result.llm_explanation,
                    "focus_accounts": sorted({item for rec in rec_map.get(result.id, []) for item in (rec.focus_accounts or [])}),
                    "focus_processes": sorted({item for rec in rec_map.get(result.id, []) for item in (rec.focus_processes or [])}),
                    "recommended_procedures": sorted(
                        {item for rec in rec_map.get(result.id, []) for item in (rec.recommended_procedures or [])}
                    ),
                    "evidence_types": sorted({item for rec in rec_map.get(result.id, []) for item in (rec.evidence_types or [])}),
                }
            )

        next_id = max([item["id"] for item in merged], default=0) + 1
        for row in document_rows:
            if row["merge_key"] in used_document_keys:
                continue
            merged.append(
                {
                    "id": next_id,
                    "risk_name": row["risk_name"],
                    "risk_category": row["risk_category"],
                    "risk_level": row["risk_level"],
                    "risk_score": row["risk_score"],
                    "source_type": "document_rule",
                    "source_mode": "document_rule",
                    "reasons": row["reasons"],
                    "summary": row["summary"],
                    "evidence_chain": row["evidence"],
                    "evidence": row["evidence"],
                    "source_rules": row["source_rules"],
                    "source_documents": row["source_documents"],
                    "llm_summary": row["summary"],
                    "llm_explanation": None,
                    "focus_accounts": row["focus_accounts"],
                    "focus_processes": row["focus_processes"],
                    "recommended_procedures": row["recommended_procedures"],
                    "evidence_types": row["evidence_types"],
                }
            )
            next_id += 1

        merged.sort(key=lambda item: (-float(item.get("risk_score") or 0), str(item.get("risk_name") or "")))
        return merged

    def build_focus_items(self, db: Session, enterprise_id: int) -> list[dict[str, Any]]:
        risks = self.list_risks(db, enterprise_id)
        items: list[dict[str, Any]] = []
        seen: list[str] = []

        for index, risk in enumerate(risks, start=1):
            summary = str(risk.get("summary") or "").strip()
            if not summary:
                summary = "；".join(risk.get("reasons") or []) or str(risk.get("risk_name") or "")
            if any(SequenceMatcher(None, summary, other).ratio() >= 0.84 for other in seen):
                continue
            seen.append(summary)
            evidence_preview = [item.get("snippet") or item.get("content") or "" for item in (risk.get("evidence") or [])]
            evidence_preview = [item[:140] for item in evidence_preview if item][:2]
            items.append(
                {
                    "id": f"focus-{index}",
                    "title": str(risk.get("risk_name") or f"重点 {index}"),
                    "summary": summary,
                    "sources": self._dedupe_strings(
                        list(risk.get("source_rules") or [])
                        + [item.get("document_name") for item in (risk.get("source_documents") or [])]
                    ),
                    "evidence_preview": evidence_preview,
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

    def _build_document_risks(
        self,
        documents: list[DocumentMeta],
        extracts_by_document: dict[int, list[Any]],
    ) -> list[dict[str, Any]]:
        rules_by_name = self._load_rule_lookup(documents, extracts_by_document)
        grouped: dict[str, dict[str, Any]] = {}

        for document in documents:
            for extract in extracts_by_document.get(document.id, []):
                payload = self._decode_extract_payload(extract.content)
                summary = str(payload.get("problem_summary") or payload.get("content") or extract.content or "").strip()
                if not summary:
                    continue
                title = str(payload.get("title") or extract.title or document.document_name).strip()
                key = self._canonical_key(title, summary)
                grouped.setdefault(
                    key,
                    {
                        "merge_key": key,
                        "risk_name": title,
                        "risk_category": "文档发现",
                        "risk_level": self._guess_risk_level(payload),
                        "risk_score": self._score_payload(payload),
                        "summary": summary,
                        "reasons": [],
                        "evidence": [],
                        "source_rules": [],
                        "source_documents": [],
                        "focus_accounts": [],
                        "focus_processes": [],
                        "recommended_procedures": [],
                        "evidence_types": ["uploaded_document" if document.source == "upload" else "announcement"],
                    },
                )
                row = grouped[key]
                row["risk_score"] = max(row["risk_score"], self._score_payload(payload))
                row["risk_level"] = self._max_risk_level(row["risk_level"], self._guess_risk_level(payload))
                row["reasons"] = self._dedupe_strings(row["reasons"] + list(payload.get("risk_points") or []) + [summary])
                row["source_rules"] = self._dedupe_strings(row["source_rules"] + list(payload.get("applied_rules") or []))
                row["source_documents"].append({"document_id": document.id, "document_name": document.document_name})
                row["evidence"].append(
                    {
                        "evidence_id": f"D{extract.id}",
                        "evidence_type": "uploaded_document" if document.source == "upload" else "announcement",
                        "source": document.source,
                        "source_label": document.document_name,
                        "published_at": document.announcement_date.isoformat() if document.announcement_date else None,
                        "title": title,
                        "snippet": str(payload.get("evidence_excerpt") or summary)[:200],
                        "content": str(payload.get("evidence_excerpt") or extract.content or "")[:500],
                        "report_period": document.report_period_label,
                    }
                )

                matched_rules = [rules_by_name[item] for item in row["source_rules"] if item in rules_by_name]
                for rule in matched_rules:
                    row["focus_accounts"] = self._dedupe_strings(row["focus_accounts"] + list(rule.focus_accounts or []))
                    row["focus_processes"] = self._dedupe_strings(row["focus_processes"] + list(rule.focus_processes or []))
                    row["recommended_procedures"] = self._dedupe_strings(
                        row["recommended_procedures"] + list(rule.recommended_procedures or [])
                    )

                if not row["recommended_procedures"]:
                    row["recommended_procedures"] = self._dedupe_strings(
                        row["recommended_procedures"] + list(payload.get("financial_topics") or []) + ["核对相关披露与原始依据"]
                    )

        for value in grouped.values():
            value["source_documents"] = self._dedupe_documents(value["source_documents"])
            value["evidence"] = value["evidence"][:4]
        return list(grouped.values())

    def _load_rule_lookup(
        self,
        documents: list[DocumentMeta],
        extracts_by_document: dict[int, list[Any]],
    ) -> dict[str, AuditRule]:
        names: set[str] = set()
        for document in documents:
            for extract in extracts_by_document.get(document.id, []):
                payload = self._decode_extract_payload(extract.content)
                names.update(str(item).strip() for item in (payload.get("applied_rules") or []) if str(item).strip())
        return {}

    def _find_matching_document_risk(self, risk_name: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        best_match = None
        best_score = 0.0
        for row in rows:
            score = SequenceMatcher(None, risk_name, row["risk_name"]).ratio()
            if score > best_score:
                best_score = score
                best_match = row
        if best_score >= 0.55:
            return best_match
        return None

    def _decode_extract_payload(self, content: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {
            "title": "",
            "problem_summary": content,
            "evidence_excerpt": content,
            "applied_rules": [],
            "risk_points": [],
            "financial_topics": [],
            "detail_level": "general",
        }

    def _score_payload(self, payload: dict[str, Any]) -> float:
        base = 62.0
        if payload.get("detail_level") == "financial_deep_dive":
            base += 8.0
        base += min(len(payload.get("applied_rules") or []) * 4.0, 12.0)
        base += min(len(payload.get("risk_points") or []) * 2.0, 8.0)
        return min(base, 95.0)

    def _guess_risk_level(self, payload: dict[str, Any]) -> str:
        text = " ".join([str(payload.get("problem_summary") or "")] + [str(item) for item in (payload.get("risk_points") or [])])
        if any(keyword in text for keyword in ["重大", "异常", "处罚", "失真", "舞弊"]):
            return "HIGH"
        if payload.get("detail_level") == "financial_deep_dive":
            return "HIGH"
        return "MEDIUM"

    def _max_risk_level(self, left: str, right: str) -> str:
        order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    def _canonical_key(self, title: str, summary: str) -> str:
        seed = f"{title}|{summary[:80]}".strip().lower().replace(" ", "")
        return seed

    def _dedupe_strings(self, values: list[str | None]) -> list[str]:
        seen: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            if text not in seen:
                seen.append(text)
        return seen

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
