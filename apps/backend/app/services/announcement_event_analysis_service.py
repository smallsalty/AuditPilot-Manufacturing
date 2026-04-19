from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.ai.announcement_event_prompt_registry import AnnouncementEventPromptRegistry
from app.ai.llm_client import LLMClient, LLMRequestError
from app.core.config import settings
from app.models import ExternalEvent
from app.utils.documents import parse_document_text


logger = logging.getLogger(__name__)


class AnnouncementEventAnalysisService:
    ANALYSIS_VERSION = "announcement-event-analysis:v1"
    MAX_BODY_CHARS = 12000
    MAX_LIST_ITEMS = 6

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def analyze_event(self, event: ExternalEvent) -> dict[str, Any]:
        payload = dict(event.payload) if isinstance(event.payload, dict) else {}
        primary_match = payload.get("primary_title_match") if isinstance(payload.get("primary_title_match"), dict) else None
        title_matches = payload.get("title_matches") if isinstance(payload.get("title_matches"), list) else []
        category_code = AnnouncementEventPromptRegistry.resolve_category(
            event_type=event.event_type,
            primary_match=primary_match,
        )
        matched_keywords = self._matched_keywords(primary_match, title_matches)
        body_text, body_source_kind, body_error = self._load_body_text(event)
        analysis_meta = {
            "analysis_version": self.ANALYSIS_VERSION,
            "analyzed_at": self._now_iso(),
            "body_source_kind": body_source_kind,
            "prompt_category": category_code,
            "llm_provider": self.llm_client.provider,
            "llm_model": self.llm_client.model,
            "body_error": body_error,
        }
        if self.llm_client.config_error:
            analysis = self._fallback_analysis(event, body_text, body_source_kind)
            analysis["category_code"] = category_code
            analysis["analysis_status"] = "fallback"
            analysis_meta["status"] = "fallback"
            analysis_meta["error"] = {"error_type": "config_error", "message": self.llm_client.config_error}
            return {"analysis": analysis, "meta": analysis_meta}

        prompt_bundle = AnnouncementEventPromptRegistry.build_prompts(
            title=event.title,
            event_type=event.event_type,
            category_code=category_code,
            matched_keywords=matched_keywords,
            body_text=self._trim_body(body_text),
            fallback_summary=event.summary or event.title,
        )
        try:
            result = self.llm_client.chat_completion(
                prompt_bundle["system_prompt"],
                prompt_bundle["user_prompt"],
                json_mode=True,
                request_kind="announcement_event_analysis",
                metadata={
                    "enterprise_id": event.enterprise_id,
                    "document_id": -event.id,
                    "classified_type": "announcement_event",
                    "prompt_template": prompt_bundle["prompt_template"],
                    "schema_name": "announcement_event_analysis_v1",
                    "candidate_count": 1,
                    "context_variant": category_code,
                    "llm_input_chars": len(prompt_bundle["user_prompt"]),
                },
                max_tokens=1600,
                max_attempts=2,
                timeout=45.0,
                strict_json_instruction=True,
            )
            parsed_ok = not (isinstance(result, dict) and result.get("parsed_ok") is False)
            analysis = self._normalize_result(result, event, body_text, body_source_kind)
            analysis["category_code"] = category_code
            analysis["prompt_template"] = prompt_bundle["prompt_template"]
            analysis["analysis_status"] = "succeeded" if parsed_ok else "fallback"
            analysis_meta.update(
                {
                    "status": "succeeded" if parsed_ok else "fallback",
                    "prompt_template": prompt_bundle["prompt_template"],
                    "response_chars": result.get("response_chars") if isinstance(result, dict) else None,
                    "payload_mode": result.get("payload_mode") if isinstance(result, dict) else None,
                    "retry_attempts": result.get("retry_attempts") if isinstance(result, dict) else None,
                }
            )
            if not parsed_ok:
                analysis_meta["error"] = {
                    "error_type": "json_decode_error",
                    "message": "MiniMax returned invalid JSON; fallback analysis was used.",
                }
            return {"analysis": analysis, "meta": analysis_meta}
        except Exception as exc:
            logger.warning("announcement event analysis failed event_id=%s error=%s", event.id, exc)
            analysis = self._fallback_analysis(event, body_text, body_source_kind)
            analysis["category_code"] = category_code
            analysis["analysis_status"] = "fallback"
            analysis_meta["status"] = "fallback"
            analysis_meta["error"] = self._error_payload(exc)
            return {"analysis": analysis, "meta": analysis_meta}

    def _load_body_text(self, event: ExternalEvent) -> tuple[str, str, dict[str, Any] | None]:
        source_url = str(event.source_url or "").strip()
        if not source_url.startswith(("http://", "https://")):
            return self._title_body(event), "title_only", {"message": "source_url unavailable"}
        target_dir = settings.uploads_dir / "event_analysis" / str(event.enterprise_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".pdf" if ".pdf" in source_url.lower() else ".txt"
        target_path = target_dir / f"event-{event.id}-{hashlib.sha1(source_url.encode('utf-8')).hexdigest()[:10]}{suffix}"
        try:
            if not target_path.exists():
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(source_url)
                    response.raise_for_status()
                    target_path.write_bytes(response.content)
            text = parse_document_text(str(target_path))
            if text.strip():
                return text, "source_url_file", None
            return self._title_body(event), "title_only", {"message": "parsed body empty"}
        except Exception as exc:
            return self._title_body(event), "title_only", self._error_payload(exc)

    def _normalize_result(
        self,
        result: Any,
        event: ExternalEvent,
        body_text: str,
        body_source_kind: str,
    ) -> dict[str, Any]:
        payload = result if isinstance(result, dict) else {}
        if isinstance(payload.get("items"), list) and payload["items"] and isinstance(payload["items"][0], dict):
            payload = payload["items"][0]
        if payload.get("parsed_ok") is False:
            return self._fallback_analysis(event, body_text, body_source_kind)
        summary = self._clean_text(payload.get("summary")) or event.summary or event.title
        return {
            "summary": summary,
            "key_facts": self._clean_list(payload.get("key_facts")),
            "risk_points": self._clean_list(payload.get("risk_points")),
            "audit_focus": self._clean_list(payload.get("audit_focus")),
            "involved_parties": self._clean_list(payload.get("involved_parties")),
            "amounts": self._clean_list(payload.get("amounts")),
            "dates": self._clean_list(payload.get("dates")),
            "evidence_excerpt": self._clean_text(payload.get("evidence_excerpt")) or self._evidence_excerpt(body_text),
            "severity": self._severity(payload.get("severity"), event.severity),
            "confidence": self._confidence(payload.get("confidence")),
            "body_source_kind": body_source_kind,
        }

    def _fallback_analysis(self, event: ExternalEvent, body_text: str, body_source_kind: str) -> dict[str, Any]:
        return {
            "summary": event.summary or event.title,
            "key_facts": [event.title],
            "risk_points": [],
            "audit_focus": [],
            "involved_parties": [],
            "amounts": [],
            "dates": [event.event_date.isoformat()] if event.event_date else [],
            "evidence_excerpt": self._evidence_excerpt(body_text) or event.summary or event.title,
            "severity": event.severity or "medium",
            "confidence": 0.35 if body_source_kind == "title_only" else 0.5,
            "body_source_kind": body_source_kind,
        }

    def _title_body(self, event: ExternalEvent) -> str:
        return "\n".join(part for part in [event.title, event.summary] if part)

    def _trim_body(self, text: str) -> str:
        text = str(text or "").strip()
        return text[: self.MAX_BODY_CHARS]

    def _evidence_excerpt(self, text: str) -> str:
        for raw in str(text or "").splitlines():
            item = " ".join(raw.split()).strip()
            if len(item) >= 12:
                return item[:300]
        return str(text or "").strip()[:300]

    def _matched_keywords(self, primary_match: dict[str, Any] | None, title_matches: list[Any]) -> list[str]:
        values: list[str] = []
        if primary_match:
            values.extend(str(item) for item in primary_match.get("matched_keywords") or [])
        for match in title_matches:
            if isinstance(match, dict):
                values.extend(str(item) for item in match.get("matched_keywords") or [])
        return self._dedupe(values)[: self.MAX_LIST_ITEMS]

    def _clean_list(self, value: Any) -> list[str]:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = [str(item) for item in value if item not in (None, "", [])]
        else:
            items = []
        return self._dedupe([self._clean_text(item) or "" for item in items])[: self.MAX_LIST_ITEMS]

    def _clean_text(self, value: Any) -> str | None:
        text = " ".join(str(value or "").replace("\r", "\n").split()).strip()
        if not text:
            return None
        return text[:1200]

    def _severity(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"low", "medium", "high"} else fallback

    def _confidence(self, value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(number, 1.0))

    def _dedupe(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _error_payload(self, error: Exception) -> dict[str, Any]:
        if isinstance(error, LLMRequestError):
            return error.to_dict()
        return {"error_type": error.__class__.__name__, "message": str(error)}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
