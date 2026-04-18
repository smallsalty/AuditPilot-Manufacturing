from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.ai.document_prompt_registry import DocumentPromptRegistry
from app.ai.llm_client import LLMRequestError
from app.models import DocumentMeta
from app.services.document_classify_service import DocumentClassificationResult
from app.utils.display_text import clean_document_title


class DocumentAnalysisPipeline:
    def __init__(self, service: Any) -> None:
        self.service = service

    def build_classification_meta(
        self,
        *,
        document: DocumentMeta,
        text: str,
        classification: DocumentClassificationResult,
    ) -> dict[str, Any]:
        return {
            "classification_reason": classification.classification_reason,
            "classification_signals": classification.classification_signals,
            "classification_input_snapshot": {
                "document_name": clean_document_title(document.document_name) or document.document_name,
                "sync_type": document.document_type,
                "body_head": self.safe_body_head_preview(text),
                "title_matches": self.extract_document_title_matches(document),
            },
        }

    def run(
        self,
        *,
        document: DocumentMeta,
        text: str,
        classified_type: str,
    ) -> dict[str, Any]:
        cleaned_entries, cleaning_meta = self.clean_entries(text, classified_type)
        if not cleaned_entries:
            error = self.make_error_payload(
                "cleaning_empty_content",
                "清洗后没有可分析的正文内容。",
            )
            return {
                "extracts": [],
                "analysis_status": "failed",
                "analysis_mode": "failed",
                "candidate_count_before_trim": 0,
                "candidate_count_after_trim": 0,
                "last_error": error,
                "llm_diagnostics": None,
                "cleaning_meta": cleaning_meta,
            }

        prompt_type = DocumentPromptRegistry.resolve_prompt_type(classified_type)
        stage_configs: list[tuple[str, str, list[dict[str, Any]]]] = [("core", prompt_type, cleaned_entries)]
        if classified_type == "annual_report":
            financial_entries = self.extract_financial_entries(cleaned_entries)
            cleaning_meta["financial_section_detected"] = bool(financial_entries)
            cleaning_meta["financial_section_count"] = len(financial_entries)
            if financial_entries:
                stage_configs.append(("financial_subanalysis", "annual_financial_subanalysis", financial_entries))

        all_extracts: list[dict[str, Any]] = []
        stage_diagnostics: list[dict[str, Any]] = []
        stage_mode_labels: list[str] = []
        last_error: dict[str, Any] | None = None
        had_partial_fallback = False
        candidate_count_before_trim = 0
        candidate_count_after_trim = 0

        for analysis_stage, stage_prompt_type, stage_entries in stage_configs:
            stage_result = self.run_stage(
                document=document,
                entries=stage_entries,
                classified_type=classified_type,
                prompt_type=stage_prompt_type,
                analysis_stage=analysis_stage,
            )
            all_extracts.extend(stage_result["extracts"])
            candidate_count_before_trim += int(stage_result["candidate_count_before_trim"])
            candidate_count_after_trim += int(stage_result["candidate_count_after_trim"])
            if stage_result.get("last_error"):
                last_error = stage_result["last_error"]
            if stage_result["analysis_status"] == "partial_fallback":
                had_partial_fallback = True
            if stage_result.get("llm_diagnostics"):
                stage_diagnostics.append(stage_result["llm_diagnostics"])
            if stage_result.get("analysis_mode"):
                stage_mode_labels.append(f"{stage_prompt_type}:{stage_result['analysis_mode']}")

        cleaning_meta["sub_analysis_modes"] = stage_mode_labels
        extracts = self.dedupe_extracts(all_extracts)
        llm_diagnostics = self.merge_stage_diagnostics(
            classified_type=classified_type,
            stage_diagnostics=stage_diagnostics,
            candidate_count=candidate_count_after_trim,
        )

        if extracts:
            return {
                "extracts": extracts,
                "analysis_status": "partial_fallback" if had_partial_fallback else "succeeded",
                "analysis_mode": "dual_stage_partial_fallback"
                if len(stage_configs) > 1 and had_partial_fallback
                else "dual_stage_llm"
                if len(stage_configs) > 1
                else "hybrid_fallback"
                if had_partial_fallback
                else "llm_primary",
                "candidate_count_before_trim": candidate_count_before_trim,
                "candidate_count_after_trim": candidate_count_after_trim,
                "last_error": last_error,
                "llm_diagnostics": llm_diagnostics,
                "cleaning_meta": cleaning_meta,
            }

        return {
            "extracts": [],
            "analysis_status": "failed",
            "analysis_mode": "failed",
            "candidate_count_before_trim": candidate_count_before_trim,
            "candidate_count_after_trim": candidate_count_after_trim,
            "last_error": last_error
            or self.make_error_payload(
                "classification_insufficient_signal",
                "清洗后未形成可分析的候选片段。",
            ),
            "llm_diagnostics": llm_diagnostics,
            "cleaning_meta": cleaning_meta,
        }

    def run_stage(
        self,
        *,
        document: DocumentMeta,
        entries: list[dict[str, Any]],
        classified_type: str,
        prompt_type: str,
        analysis_stage: str,
    ) -> dict[str, Any]:
        candidates = []
        for index, entry in enumerate(entries, start=1):
            candidate = self.service._build_candidate(document, entry, classified_type, index)
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return {
                "extracts": [],
                "analysis_status": "failed",
                "analysis_mode": "failed",
                "candidate_count_before_trim": 0,
                "candidate_count_after_trim": 0,
                "last_error": self.make_error_payload(
                    "classification_insufficient_signal",
                    f"{prompt_type} 阶段未形成可分析候选片段。",
                ),
                "llm_diagnostics": None,
            }

        trimmed_candidates = self.service._trim_candidates(candidates, classified_type)
        if not trimmed_candidates:
            return {
                "extracts": [],
                "analysis_status": "failed",
                "analysis_mode": "failed",
                "candidate_count_before_trim": len(candidates),
                "candidate_count_after_trim": 0,
                "last_error": self.make_error_payload(
                    "classification_insufficient_signal",
                    f"{prompt_type} 阶段候选片段经过过滤后为空。",
                ),
                "llm_diagnostics": None,
            }

        prompt_bundle = DocumentPromptRegistry.build_prompts(
            document_name=clean_document_title(document.document_name) or document.document_name,
            classified_type=classified_type,
            prompt_type=prompt_type,
            candidates=trimmed_candidates[: self.service.LLM_EXTRACT_CANDIDATE_LIMIT],
            report_period_label=document.report_period_label,
        )
        llm_input_chars = sum(
            len(str(item.get("evidence_excerpt") or ""))
            for item in trimmed_candidates[: self.service.LLM_EXTRACT_CANDIDATE_LIMIT]
        )
        stage_max_tokens = self._resolve_stage_max_tokens(
            prompt_bundle["prompt_template"],
            prompt_bundle["schema_name"],
        )

        if self.service.llm_client.config_error:
            error = self.make_error_payload(
                "llm_request_rejected",
                self.service.llm_client.config_error,
                error_type="config_error",
                prompt_template=prompt_bundle["prompt_template"],
                schema_name=prompt_bundle["schema_name"],
            )
            fallback = self.service._fallback_extracts(document, trimmed_candidates, classified_type)
            fallback = [
                self.apply_stage_defaults(item, analysis_stage, prompt_type, classified_type)
                for item in fallback
            ]
            return {
                "extracts": fallback,
                "analysis_status": "partial_fallback" if fallback else "failed",
                "analysis_mode": "hybrid_fallback" if fallback else "failed",
                "candidate_count_before_trim": len(candidates),
                "candidate_count_after_trim": len(trimmed_candidates),
                "last_error": error,
                "llm_diagnostics": self.build_llm_diagnostics(
                    classified_type=classified_type,
                    prompt_template=prompt_bundle["prompt_template"],
                    schema_name=prompt_bundle["schema_name"],
                    candidate_count=min(len(trimmed_candidates), self.service.LLM_EXTRACT_CANDIDATE_LIMIT),
                    llm_input_chars=llm_input_chars,
                    payload_mode="config_error",
                    retry_attempts=0,
                    max_tokens=stage_max_tokens,
                    raw_preview=None,
                ),
            }

        result = self.service.llm_client.chat_completion(
            prompt_bundle["system_prompt"],
            prompt_bundle["user_prompt"],
            json_mode=True,
            request_kind="document_extract",
            metadata={
                "document_id": document.id,
                "enterprise_id": document.enterprise_id,
                "classified_type": classified_type,
                "candidate_count": min(len(trimmed_candidates), self.service.LLM_EXTRACT_CANDIDATE_LIMIT),
                "llm_input_chars": llm_input_chars,
                "prompt_template": prompt_bundle["prompt_template"],
                "schema_name": prompt_bundle["schema_name"],
            },
            max_tokens=stage_max_tokens,
            max_attempts=2,
            timeout=30.0,
            strict_json_instruction=True,
        )

        items, llm_diagnostics, error = self.validate_llm_stage_result(
            result=result,
            classified_type=classified_type,
            prompt_template=prompt_bundle["prompt_template"],
            schema_name=prompt_bundle["schema_name"],
            required_item_keys=prompt_bundle["required_item_keys"],
            required_any_of=prompt_bundle["required_any_of"],
            candidate_count=min(len(trimmed_candidates), self.service.LLM_EXTRACT_CANDIDATE_LIMIT),
            llm_input_chars=llm_input_chars,
            max_tokens=stage_max_tokens,
        )

        if items:
            normalized: list[dict[str, Any]] = []
            for index, item in enumerate(items, start=1):
                payload = self.service._normalize_extract_payload(document, item, index)
                payload = self.apply_stage_defaults(payload, analysis_stage, prompt_type, classified_type)
                if self.service._is_low_quality_extract(payload):
                    continue
                normalized.append(payload)
            if normalized:
                return {
                    "extracts": normalized,
                    "analysis_status": "succeeded",
                    "analysis_mode": "llm_primary",
                    "candidate_count_before_trim": len(candidates),
                    "candidate_count_after_trim": len(trimmed_candidates),
                    "last_error": None,
                    "llm_diagnostics": llm_diagnostics,
                }
            error = self.make_error_payload(
                "llm_extract_normalization_failed",
                "模型返回了结构化结果，但规范化后没有保留有效抽取项。",
                error_type="llm_extract_normalization_failed",
                payload_mode=llm_diagnostics.get("payload_mode"),
                retry_attempts=llm_diagnostics.get("retry_attempts"),
                prompt_template=prompt_bundle["prompt_template"],
                schema_name=prompt_bundle["schema_name"],
                raw_preview=llm_diagnostics.get("raw_preview"),
            )

        fallback = self.service._fallback_extracts(document, trimmed_candidates, classified_type)
        fallback = [self.apply_stage_defaults(item, analysis_stage, prompt_type, classified_type) for item in fallback]
        if fallback:
            return {
                "extracts": fallback,
                "analysis_status": "partial_fallback",
                "analysis_mode": "hybrid_fallback",
                "candidate_count_before_trim": len(candidates),
                "candidate_count_after_trim": len(trimmed_candidates),
                "last_error": error,
                "llm_diagnostics": llm_diagnostics,
            }

        return {
            "extracts": [],
            "analysis_status": "failed",
            "analysis_mode": "failed",
            "candidate_count_before_trim": len(candidates),
            "candidate_count_after_trim": len(trimmed_candidates),
            "last_error": error,
            "llm_diagnostics": llm_diagnostics,
        }

    def clean_entries(self, text: str, classified_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        raw_entries = self.service._split_entries(text)
        entries: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        section_title = ""
        dropped_noise_count = 0

        for raw in raw_entries:
            item = self.service._normalize_entry_text(raw)
            if not item or len(item) < 4:
                dropped_noise_count += 1
                continue
            if self.service.HEADING_PATTERN.match(item):
                section_title = item[:80]
                continue
            if self.service._is_common_noise(item) or self.service._should_skip_by_type(item, classified_type, section_title):
                dropped_noise_count += 1
                continue
            paragraph_hash = hashlib.sha1(item.encode("utf-8")).hexdigest()
            if paragraph_hash in seen_hashes:
                dropped_noise_count += 1
                continue
            seen_hashes.add(paragraph_hash)
            entries.append(
                {
                    "text": item,
                    "section_title": section_title or None,
                    "paragraph_hash": paragraph_hash,
                    "page_start": None,
                    "page_end": None,
                }
            )

        filtered = [entry for entry in entries if self.service._passes_type_signal(entry, classified_type)]
        kept = (filtered or entries)[:120]
        return kept, {
            "raw_entry_count": len(raw_entries),
            "cleaned_entry_count": len(kept),
            "kept_section_titles": self.service._dedupe_strings(
                [str(entry.get("section_title") or "").strip() for entry in kept if entry.get("section_title")]
            )[:12],
            "dropped_noise_count": dropped_noise_count,
            "financial_section_detected": False,
            "financial_section_count": 0,
            "sub_analysis_modes": [],
        }

    def extract_financial_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        section_keywords = (
            "财务报表",
            "财务报表附注",
            "合并资产负债表",
            "合并利润表",
            "合并现金流量表",
            "附注",
            "主要会计数据",
            "会计政策",
        )
        topic_keywords = tuple(self.service.FINANCIAL_TOPICS) + (
            "资产负债表",
            "利润表",
            "现金流量表",
            "附注",
            "应收账款",
            "存货",
            "商誉",
            "坏账准备",
            "减值准备",
        )
        matched: list[dict[str, Any]] = []
        for entry in entries:
            text = str(entry.get("text") or "")
            section_title = str(entry.get("section_title") or "")
            if any(keyword in section_title for keyword in section_keywords) or any(keyword in text for keyword in topic_keywords):
                matched.append(entry)
        deduped: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for entry in matched:
            paragraph_hash = str(entry.get("paragraph_hash") or "")
            if not paragraph_hash or paragraph_hash in seen_hashes:
                continue
            seen_hashes.add(paragraph_hash)
            deduped.append(entry)
        return deduped[:60]

    def validate_llm_stage_result(
        self,
        *,
        result: Any,
        classified_type: str,
        prompt_template: str,
        schema_name: str,
        required_item_keys: tuple[str, ...],
        required_any_of: tuple[str, ...],
        candidate_count: int,
        llm_input_chars: int,
        max_tokens: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
        if not isinstance(result, dict):
            llm_diagnostics = self.build_llm_diagnostics(
                classified_type=classified_type,
                prompt_template=prompt_template,
                schema_name=schema_name,
                candidate_count=candidate_count,
                llm_input_chars=llm_input_chars,
                payload_mode="empty",
                retry_attempts=None,
                max_tokens=max_tokens,
                raw_preview=None,
            )
            error = self.make_error_payload(
                "llm_empty_response",
                "模型没有返回可解析的响应。",
                error_type="llm_empty_response",
                prompt_template=prompt_template,
                schema_name=schema_name,
            )
            return [], llm_diagnostics, error

        payload_mode = result.get("payload_mode")
        retry_attempts = result.get("retry_attempts")
        raw_preview = None
        if isinstance(result.get("raw"), str):
            raw_preview = self.service._trim_evidence_safe(str(result.get("raw")), limit=200)

        llm_diagnostics = self.build_llm_diagnostics(
            classified_type=classified_type,
            prompt_template=prompt_template,
            schema_name=schema_name,
            candidate_count=candidate_count,
            llm_input_chars=llm_input_chars,
            payload_mode=payload_mode,
            retry_attempts=retry_attempts,
            max_tokens=max_tokens,
            raw_preview=raw_preview,
        )

        if result.get("parsed_ok") is False:
            error = self.make_error_payload(
                "llm_json_decode_error",
                "模型返回了非 JSON 文本，无法按约定结构解析。",
                error_type="json_decode_error",
                payload_mode=payload_mode,
                retry_attempts=retry_attempts,
                prompt_template=prompt_template,
                schema_name=schema_name,
                raw_preview=raw_preview,
            )
            return [], llm_diagnostics, error

        items = result.get("items")
        if not isinstance(items, list) and isinstance(result.get("extracts"), list):
            items = result.get("extracts")
        if not isinstance(items, list):
            error = self.make_error_payload(
                "llm_schema_validation_error",
                "模型返回了 JSON，但缺少顶层 items 数组。",
                error_type="schema_validation_error",
                payload_mode=payload_mode,
                retry_attempts=retry_attempts,
                prompt_template=prompt_template,
                schema_name=schema_name,
                raw_preview=raw_preview,
            )
            return [], llm_diagnostics, error

        normalized_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if not all(self.has_value(item.get(key)) for key in required_item_keys):
                continue
            if required_any_of and not any(self.has_value(item.get(key)) for key in required_any_of):
                continue
            normalized_items.append(item)

        if not normalized_items:
            error_code = "llm_empty_response" if not items else "llm_schema_validation_error"
            error_message = "模型返回了空结果。" if not items else "模型返回的 JSON 结构不符合当前模板要求。"
            error = self.make_error_payload(
                error_code,
                error_message,
                error_type="schema_validation_error" if items else "llm_empty_response",
                payload_mode=payload_mode,
                retry_attempts=retry_attempts,
                prompt_template=prompt_template,
                schema_name=schema_name,
                raw_preview=raw_preview,
            )
            return [], llm_diagnostics, error

        return normalized_items, llm_diagnostics, None

    def has_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    def build_llm_diagnostics(
        self,
        *,
        classified_type: str,
        prompt_template: str,
        schema_name: str,
        candidate_count: int,
        llm_input_chars: int,
        payload_mode: str | None,
        retry_attempts: int | None,
        max_tokens: int,
        raw_preview: str | None,
    ) -> dict[str, Any]:
        return {
            "model": self.service.llm_client.model,
            "request_kind": "document_extract",
            "classified_type": classified_type,
            "prompt_template": prompt_template,
            "schema_name": schema_name,
            "json_mode": True,
            "strict_json_instruction": True,
            "retry_attempts": retry_attempts,
            "candidate_count": candidate_count,
            "llm_input_chars": llm_input_chars,
            "max_tokens": max_tokens,
            "payload_mode": payload_mode,
            "raw_preview": raw_preview,
        }

    def merge_stage_diagnostics(
        self,
        *,
        classified_type: str,
        stage_diagnostics: list[dict[str, Any]],
        candidate_count: int,
    ) -> dict[str, Any] | None:
        if not stage_diagnostics:
            return None
        raw_preview = next((item.get("raw_preview") for item in stage_diagnostics if item.get("raw_preview")), None)
        payload_mode = next((item.get("payload_mode") for item in reversed(stage_diagnostics) if item.get("payload_mode")), None)
        retry_attempts = max([int(item.get("retry_attempts") or 0) for item in stage_diagnostics], default=0)
        llm_input_chars = sum(int(item.get("llm_input_chars") or 0) for item in stage_diagnostics)
        max_tokens = max([int(item.get("max_tokens") or 0) for item in stage_diagnostics], default=0)
        return {
            "model": self.service.llm_client.model,
            "request_kind": "document_extract",
            "classified_type": classified_type,
            "prompt_template": stage_diagnostics[0].get("prompt_template") if len(stage_diagnostics) == 1 else "multi_stage",
            "schema_name": stage_diagnostics[0].get("schema_name") if len(stage_diagnostics) == 1 else "multi_stage",
            "json_mode": True,
            "strict_json_instruction": True,
            "retry_attempts": retry_attempts,
            "candidate_count": candidate_count,
            "llm_input_chars": llm_input_chars,
            "max_tokens": max_tokens,
            "payload_mode": payload_mode,
            "raw_preview": raw_preview,
            "stages": stage_diagnostics,
        }

    def _resolve_stage_max_tokens(self, prompt_template: str, schema_name: str) -> int:
        if (
            prompt_template == "document_extract:annual_report"
            or schema_name == "annual_report_extract_v1"
        ):
            return 2048
        if (
            prompt_template == "document_extract:annual_financial_subanalysis"
            or schema_name == "annual_financial_subanalysis_v1"
        ):
            return 2048
        return 1024

    def apply_stage_defaults(
        self,
        payload: dict[str, Any],
        analysis_stage: str,
        prompt_type: str,
        classified_type: str,
    ) -> dict[str, Any]:
        parameters = dict(payload.get("parameters") or {})
        parameters["analysis_stage"] = analysis_stage
        payload["parameters"] = parameters
        if prompt_type == "annual_financial_subanalysis":
            payload["extract_family"] = "financial_statement"
            payload["detail_level"] = "financial_deep_dive"
            payload["event_type"] = str(payload.get("event_type") or "financial_anomaly")
        elif prompt_type == "audit_report" and payload.get("opinion_type"):
            payload["extract_family"] = "opinion_conclusion"
            payload["event_type"] = payload.get("event_type") or "audit_opinion_issue"
        elif prompt_type == "internal_control_report" and (payload.get("defect_level") or payload.get("event_type")):
            payload["extract_family"] = "internal_control_conclusion"
            payload["event_type"] = payload.get("event_type") or "internal_control_issue"
        elif prompt_type == "announcement_event":
            payload["extract_family"] = "announcement_event"
        elif classified_type in self.service.FINANCIAL_DOCUMENT_TYPES and payload.get("metric_name"):
            payload["extract_family"] = "financial_statement"
        return payload

    def dedupe_extracts(self, extracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in extracts:
            key = (
                str(item.get("evidence_span_id") or ""),
                str(item.get("title") or ""),
                str(item.get("summary") or item.get("problem_summary") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def extract_document_title_matches(self, document: DocumentMeta) -> list[dict[str, Any]]:
        metadata = dict(document.metadata_json or {})
        direct = metadata.get("title_matches")
        if isinstance(direct, list):
            return [item for item in direct if isinstance(item, dict)]
        sync_diagnostics = metadata.get("sync_diagnostics") or {}
        if isinstance(sync_diagnostics, dict):
            matches = sync_diagnostics.get("title_matches")
            if isinstance(matches, list):
                return [item for item in matches if isinstance(item, dict)]
        return []

    def safe_body_head_preview(self, text: str, limit: int = 6) -> list[str]:
        lines: list[str] = []
        for raw in str(text or "").splitlines():
            item = self.service._normalize_entry_text(raw)
            if not item:
                continue
            lines.append(item[:160])
            if len(lines) >= limit:
                break
        return lines

    def make_error_payload(
        self,
        code: str,
        message: str,
        *,
        error_type: str | None = None,
        status_code: int | None = None,
        provider_response_text: str | None = None,
        payload_mode: str | None = None,
        retry_attempts: int | None = None,
        prompt_template: str | None = None,
        schema_name: str | None = None,
        raw_preview: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": code,
            "message": message,
            "status_code": status_code,
            "error_type": error_type or code,
            "provider_response_text": provider_response_text,
            "last_error_at": datetime.now(timezone.utc).isoformat(),
        }
        if payload_mode:
            payload["payload_mode"] = payload_mode
        if retry_attempts is not None:
            payload["retry_attempts"] = retry_attempts
        if prompt_template:
            payload["prompt_template"] = prompt_template
        if schema_name:
            payload["schema_name"] = schema_name
        if raw_preview:
            payload["raw_preview"] = raw_preview
        return payload

    def exception_to_error_payload(self, exc: Exception) -> dict[str, Any]:
        if isinstance(exc, LLMRequestError):
            error_type = str(exc.error_type or "llm_request_error")
            code_map = {
                "transport_error": "llm_request_rejected",
                "auth_error": "llm_request_rejected",
                "upstream_unavailable": "llm_request_rejected",
                "request_rejected": "llm_request_rejected",
                "config_error": "llm_request_rejected",
                "unexpected_error": "llm_request_rejected",
            }
            return self.make_error_payload(
                code_map.get(error_type, error_type),
                exc.message,
                error_type=error_type,
                status_code=exc.status_code,
                provider_response_text=exc.provider_response_text,
            )
        return self.make_error_payload(
            "unexpected_error",
            str(exc),
            error_type=exc.__class__.__name__,
        )
