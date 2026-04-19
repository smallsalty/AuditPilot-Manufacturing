from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.providers.audit.announcement_event_matcher import AnnouncementEventMatcher
from app.repositories.enterprise_repository import EnterpriseRepository


class AnnouncementRiskService:
    LOOKBACK_DAYS = 365
    REPEAT_WINDOW_DAYS = 90
    SCORE_BY_LEVEL = {
        "low": 42.0,
        "medium": 58.0,
        "high": 74.0,
    }
    CATEGORY_SCORE_CAPS = {
        "regulatory_litigation": 92.0,
        "accounting_audit": 90.0,
        "fund_occupation_related_party_guarantee": 90.0,
        "debt_liquidity_default": 88.0,
        "equity_control_pledge": 80.0,
        "performance_revision_impairment": 78.0,
        "governance_personnel_internal_control": 76.0,
    }

    def __init__(self) -> None:
        self.matcher = AnnouncementEventMatcher()

    def build_announcement_risks(self, db: Session, enterprise_id: int) -> dict[str, Any]:
        repo = EnterpriseRepository(db)
        events = repo.get_external_events(enterprise_id, official_only=True)
        documents = repo.get_documents(enterprise_id, official_only=True)
        source_rows = self._collect_source_rows(events=events, documents=documents)
        if not source_rows:
            return self._empty_payload(enterprise_id)

        matched_rows = [
            self._materialize_row(row)
            for row in source_rows
        ]
        matched_rows = [row for row in matched_rows if row is not None]
        if not matched_rows:
            return self._empty_payload(enterprise_id)

        matched_rows.sort(key=lambda item: (item["source_date"] or date.min, item["source_title"]), reverse=True)
        category_history = defaultdict(list)
        today = date.today()
        for item in matched_rows:
            category_history[item["category_code"]].append(item)

        announcement_risks: list[dict[str, Any]] = []
        category_breakdown_map: dict[str, dict[str, Any]] = {}

        for item in matched_rows:
            definition = self.matcher.category_definition(item["category_code"])
            if definition is None:
                continue
            if item["source_date"] and (today - item["source_date"]).days > self.LOOKBACK_DAYS:
                continue
            prior_same_category = [
                other for other in category_history[item["category_code"]]
                if other["dedupe_key"] != item["dedupe_key"]
                and other["source_date"]
                and item["source_date"]
                and 0 <= (item["source_date"] - other["source_date"]).days <= self.REPEAT_WINDOW_DAYS
            ]
            score = self._score_event(
                category_code=item["category_code"],
                risk_level=item["risk_level"],
                source_date=item["source_date"],
                repeat_count=len(prior_same_category),
                base_weight=definition.base_weight,
            )
            explanation = self._build_explanation(
                definition=definition,
                matched_keywords=item["matched_keywords"],
                source_title=item["source_title"],
                secondary_categories=item["secondary_categories"],
                repeat_count=len(prior_same_category),
            )
            summary = f"{definition.category_name}信号，标题命中“{'、'.join(item['matched_keywords'])}”。"
            event_analysis = item.get("event_analysis")
            analysis_summary = self._analysis_summary(event_analysis)
            analysis_detail = self._analysis_detail_text(event_analysis)
            analysis_audit_focus = self._analysis_list(event_analysis, "audit_focus")
            if analysis_summary:
                summary = analysis_summary
            if analysis_detail:
                explanation = analysis_detail
            risk_item = {
                "event_code": definition.event_code,
                "event_category": definition.category_name,
                "event_name": definition.event_name,
                "source_event_id": item.get("source_event_id"),
                "matched_keywords": item["matched_keywords"],
                "risk_level": item["risk_level"],
                "risk_score": round(score, 1),
                "summary": summary,
                "explanation": explanation,
                "source_title": item["source_title"],
                "source_date": item["source_date"].isoformat() if item["source_date"] else None,
                "source_url": item["source_url"],
                "canonical_risk_key": definition.canonical_risk_key,
                "risk_category": definition.risk_category,
                "focus_accounts": list(definition.focus_accounts),
                "focus_processes": list(definition.focus_processes),
                "recommended_procedures": self._dedupe_strings(list(definition.recommended_procedures) + analysis_audit_focus),
                "evidence_types": list(definition.evidence_types),
                "rationale": definition.rationale,
                "repeat_count_90d": len(prior_same_category),
                "event_analysis": event_analysis if isinstance(event_analysis, dict) else None,
                "body_analysis_summary": analysis_summary,
                "audit_focus": analysis_audit_focus,
            }
            announcement_risks.append(risk_item)

            breakdown = category_breakdown_map.setdefault(
                definition.category_code,
                {
                    "event_category": definition.category_name,
                    "count": 0,
                    "high_risk_count": 0,
                    "score": 0.0,
                },
            )
            breakdown["count"] += 1
            breakdown["high_risk_count"] += 1 if item["risk_level"] == "high" else 0
            breakdown["score"] = max(float(breakdown["score"]), round(score, 1))

        if not announcement_risks:
            return self._empty_payload(enterprise_id)

        announcement_risks.sort(key=lambda item: (-float(item["risk_score"]), item["event_category"], item["source_title"]))
        category_breakdown = sorted(
            category_breakdown_map.values(),
            key=lambda item: (-int(item["count"]), -float(item["score"]), item["event_category"]),
        )
        aggregate_score = self._aggregate_score(announcement_risks)
        high_risk_count = sum(1 for item in announcement_risks if item["risk_level"] == "high")
        matched_event_count = len(announcement_risks)

        return {
            "enterprise_id": enterprise_id,
            "announcement_risks": announcement_risks,
            "announcement_risk_score": aggregate_score,
            "announcement_risk_level": self._aggregate_level(aggregate_score),
            "matched_event_count": matched_event_count,
            "high_risk_event_count": high_risk_count,
            "category_breakdown": category_breakdown,
            "announcement_summary": self._build_summary(announcement_risks, category_breakdown),
        }

    def _collect_source_rows(self, *, events: list[Any], documents: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        for event in events:
            if getattr(event, "source", "") != "cninfo":
                continue
            payload = getattr(event, "payload", None) or {}
            primary_match = payload.get("primary_title_match") if isinstance(payload, dict) else None
            title_matches = payload.get("title_matches") if isinstance(payload, dict) else None
            row = self._build_source_row(
                source_event_id=getattr(event, "id", None),
                title=getattr(event, "title", None),
                source_date=getattr(event, "announcement_date", None) or getattr(event, "event_date", None),
                source_url=getattr(event, "source_url", None),
                source_object_id=getattr(event, "source_object_id", None),
                primary_match=primary_match,
                title_matches=title_matches,
                event_analysis=payload.get("event_analysis") if isinstance(payload, dict) else None,
            )
            if row and row["dedupe_key"] not in seen:
                seen.add(row["dedupe_key"])
                rows.append(row)

        for document in documents:
            if getattr(document, "source", "") != "cninfo":
                continue
            metadata_json = getattr(document, "metadata_json", None) or {}
            diagnostics = metadata_json.get("sync_diagnostics") if isinstance(metadata_json, dict) else {}
            row = self._build_source_row(
                source_event_id=None,
                title=getattr(document, "document_name", None),
                source_date=getattr(document, "announcement_date", None),
                source_url=getattr(document, "source_url", None),
                source_object_id=getattr(document, "source_object_id", None),
                primary_match=(diagnostics or {}).get("primary_title_match"),
                title_matches=(diagnostics or {}).get("title_matches"),
                event_analysis=None,
            )
            if row and row["dedupe_key"] not in seen:
                seen.add(row["dedupe_key"])
                rows.append(row)
        return rows

    def _build_source_row(
        self,
        *,
        source_event_id: Any,
        title: Any,
        source_date: Any,
        source_url: Any,
        source_object_id: Any,
        primary_match: Any,
        title_matches: Any,
        event_analysis: Any,
    ) -> dict[str, Any] | None:
        title_text = str(title or "").strip()
        if not title_text:
            return None
        matches = title_matches if isinstance(title_matches, list) else self.matcher.match_title_categories(title_text)
        selected = primary_match if isinstance(primary_match, dict) else self.matcher.select_primary_match(title_text, matches)
        if not selected:
            return None
        if selected["category_code"] not in self.matcher.SUPPORTED_RISK_CATEGORY_CODES:
            return None
        parsed_date = self._coerce_date(source_date)
        return {
            "source_event_id": int(source_event_id) if source_event_id is not None else None,
            "category_code": selected["category_code"],
            "matched_keywords": list(selected.get("matched_keywords") or []),
            "risk_level": str(selected.get("risk_level") or "medium").lower(),
            "source_title": title_text,
            "source_date": parsed_date,
            "source_url": str(source_url or "").strip() or None,
            "secondary_categories": list(selected.get("secondary_categories") or []),
            "event_analysis": event_analysis if isinstance(event_analysis, dict) else None,
            "dedupe_key": str(source_object_id or "").strip()
            or "|".join([title_text, parsed_date.isoformat() if parsed_date else "", str(source_url or "").strip()]),
        }

    def _materialize_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        return row

    def _score_event(
        self,
        *,
        category_code: str,
        risk_level: str,
        source_date: date | None,
        repeat_count: int,
        base_weight: float,
    ) -> float:
        score = self.SCORE_BY_LEVEL.get(risk_level, self.SCORE_BY_LEVEL["medium"]) * base_weight
        score *= self._recency_multiplier(source_date)
        score += min(repeat_count * 5.0, 12.0)
        return min(score, self.CATEGORY_SCORE_CAPS.get(category_code, 85.0))

    def _recency_multiplier(self, source_date: date | None) -> float:
        if source_date is None:
            return 0.78
        days = max((date.today() - source_date).days, 0)
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.93
        if days <= 180:
            return 0.86
        return 0.74

    def _aggregate_score(self, announcement_risks: list[dict[str, Any]]) -> float:
        if not announcement_risks:
            return 0.0
        weights = [0.46, 0.27, 0.17, 0.1]
        total = 0.0
        for index, risk in enumerate(announcement_risks[:4]):
            total += float(risk["risk_score"]) * weights[index]
        return round(min(total, 88.0), 1)

    def _aggregate_level(self, aggregate_score: float) -> str:
        if aggregate_score >= 70:
            return "high"
        if aggregate_score >= 45:
            return "medium"
        return "low"

    def _build_summary(self, announcement_risks: list[dict[str, Any]], category_breakdown: list[dict[str, Any]]) -> str:
        high_risk_count = sum(1 for item in announcement_risks if item["risk_level"] == "high")
        leading = "、".join(item["event_category"] for item in category_breakdown[:3]) or "未形成集中类别"
        return f"近一年命中高风险公告 {high_risk_count} 条，累计命中公告事件 {len(announcement_risks)} 条，主要集中在{leading}。"

    def _analysis_summary(self, event_analysis: Any) -> str | None:
        if not isinstance(event_analysis, dict):
            return None
        summary = str(event_analysis.get("summary") or "").strip()
        return summary or None

    def _analysis_detail_text(self, event_analysis: Any) -> str | None:
        if not isinstance(event_analysis, dict):
            return None
        parts: list[str] = []
        summary = str(event_analysis.get("summary") or "").strip()
        if summary:
            parts.append(f"正文分析总结：{summary}")
        risk_points = self._analysis_list(event_analysis, "risk_points")
        if risk_points:
            parts.append("风险点：" + "；".join(risk_points[:3]))
        audit_focus = self._analysis_list(event_analysis, "audit_focus")
        if audit_focus:
            parts.append("审计关注：" + "；".join(audit_focus[:3]))
        evidence = str(event_analysis.get("evidence_excerpt") or "").strip()
        if evidence:
            parts.append("证据摘录：" + evidence)
        if not parts:
            return None
        return " ".join(parts[:4])

    def _analysis_list(self, event_analysis: Any, key: str) -> list[str]:
        if not isinstance(event_analysis, dict):
            return []
        value = event_analysis.get(key)
        if not isinstance(value, list):
            return []
        return self._dedupe_strings([str(item).strip() for item in value if str(item).strip()])[:5]

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        items: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in items:
                items.append(text)
        return items

    def _build_explanation(
        self,
        *,
        definition,
        matched_keywords: list[str],
        source_title: str,
        secondary_categories: list[str],
        repeat_count: int,
    ) -> str:
        parts = [
            f"公告标题“{source_title}”命中关键词“{'、'.join(matched_keywords)}”，归入{definition.category_name}。",
            definition.rationale,
        ]
        if secondary_categories:
            parts.append(f"同一标题还同时触及{ '、'.join(secondary_categories[:2]) }等其他风险信号，但本次仅按主事件类别计分。")
        if repeat_count > 0:
            parts.append(f"近90天同类公告已重复发生 {repeat_count + 1} 次，说明该风险并非单点事件，应提高审计关注强度。")
        return " ".join(parts)

    def _empty_payload(self, enterprise_id: int) -> dict[str, Any]:
        return {
            "enterprise_id": enterprise_id,
            "announcement_risks": [],
            "announcement_risk_score": 0.0,
            "announcement_risk_level": "low",
            "matched_event_count": 0,
            "high_risk_event_count": 0,
            "category_breakdown": [],
            "announcement_summary": "近一年未命中可计分的巨潮公告标题风险事件。",
        }

    @staticmethod
    def _coerce_date(value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None
