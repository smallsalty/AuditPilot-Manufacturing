from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

from app.ai.audit_qa_server import AuditQAServer
from app.ai.llm_client import LLMClient
from app.core.db import SessionLocal
from app.models import DocumentMeta
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.document_service import DocumentService


@dataclass
class ProbeResult:
    ok: bool
    probe: str
    item: str
    variant: str
    json_mode: bool
    strict_json_instruction: bool
    max_tokens: int
    max_attempts: int
    elapsed_ms: int
    result_type: str
    error_type: str | None = None
    error: str | None = None
    response_preview: str | None = None
    payload_chars: int | None = None
    candidate_count: int | None = None


def _truncate(value: Any, limit: int = 300) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _run_minimal_once(
    *,
    json_mode: bool,
    strict_json_instruction: bool,
    max_tokens: int,
    max_attempts: int,
) -> ProbeResult:
    client = LLMClient()
    start = time.time()
    try:
        result = client.chat_completion(
            "You are a helpful assistant.",
            "Reply with OK.",
            json_mode=json_mode,
            request_kind="probe_minimal",
            metadata={"context_variant": "minimal"},
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            strict_json_instruction=strict_json_instruction,
        )
        return ProbeResult(
            ok=True,
            probe="minimal",
            item="minimal",
            variant="minimal",
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type=type(result).__name__,
            response_preview=_truncate(result),
            payload_chars=len(str(result or "")),
        )
    except Exception as exc:
        return ProbeResult(
            ok=False,
            probe="minimal",
            item="minimal",
            variant="minimal",
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type="error",
            error_type=exc.__class__.__name__,
            error=str(exc),
        )


def _build_document_extract_payload(doc_id: int) -> tuple[DocumentMeta, str, list[dict[str, Any]], str, str]:
    db = SessionLocal()
    try:
        service = DocumentService()
        document = db.get(DocumentMeta, doc_id)
        if document is None:
            raise ValueError(f"document {doc_id} not found")
        text = document.content_text or ""
        classified_type = document.classified_type or document.document_type or "general"
        entries = service._clean_document(text, classified_type)
        candidates = []
        for idx, entry in enumerate(entries, start=1):
            candidate = service._build_candidate(document, entry, classified_type, idx)
            if candidate is not None:
                candidates.append(candidate)
        trimmed = service._trim_candidates(candidates, classified_type)
        system_prompt, user_prompt = service._build_llm_extract_prompts(document, trimmed, classified_type)
        return document, classified_type, trimmed, system_prompt, user_prompt
    finally:
        db.close()


def _run_document_extract_once(
    *,
    doc_id: int,
    json_mode: bool,
    strict_json_instruction: bool,
    max_tokens: int,
    max_attempts: int,
) -> ProbeResult:
    document, classified_type, trimmed, system_prompt, user_prompt = _build_document_extract_payload(doc_id)
    client = LLMClient()
    start = time.time()
    try:
        result = client.chat_completion(
            system_prompt,
            user_prompt,
            json_mode=json_mode,
            request_kind="probe_document_extract",
            metadata={
                "enterprise_id": document.enterprise_id,
                "document_id": document.id,
                "classified_type": classified_type,
                "candidate_count": len(trimmed),
                "llm_input_chars": sum(len(str(item.get("evidence_excerpt") or "")) for item in trimmed[: client.client is not None and 10 or 10]),
                "context_variant": "trimmed_candidates",
            },
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            strict_json_instruction=strict_json_instruction,
        )
        return ProbeResult(
            ok=True,
            probe="document_extract",
            item=str(doc_id),
            variant=classified_type,
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type=type(result).__name__,
            response_preview=_truncate(result),
            payload_chars=len(user_prompt),
            candidate_count=len(trimmed),
        )
    except Exception as exc:
        return ProbeResult(
            ok=False,
            probe="document_extract",
            item=str(doc_id),
            variant=classified_type,
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type="error",
            error_type=exc.__class__.__name__,
            error=str(exc),
            payload_chars=len(user_prompt),
            candidate_count=len(trimmed),
        )


def _build_chat_payload(enterprise_id: int, question: str, context_variant: str) -> tuple[int, str, str, str]:
    db = SessionLocal()
    try:
        enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError(f"enterprise {enterprise_id} not found")
        server = AuditQAServer()
        risk_rows, document_risks, chunks = server._collect_context(db, enterprise, question)
        _basis_level, system_prompt, user_prompt, variant = server.build_prompt_payload(
            enterprise=enterprise,
            question=question,
            risk_rows=risk_rows,
            document_risks=document_risks,
            chunks=chunks,
            context_variant=context_variant,
        )
        candidate_count = len(risk_rows) + len(document_risks) + len(chunks)
        return candidate_count, variant, system_prompt, user_prompt
    finally:
        db.close()


def _run_chat_once(
    *,
    enterprise_id: int,
    question: str,
    context_variant: str,
    json_mode: bool,
    strict_json_instruction: bool,
    max_tokens: int,
    max_attempts: int,
) -> ProbeResult:
    candidate_count, variant, system_prompt, user_prompt = _build_chat_payload(enterprise_id, question, context_variant)
    client = LLMClient()
    start = time.time()
    try:
        result = client.chat_completion(
            system_prompt,
            user_prompt,
            json_mode=json_mode,
            request_kind="probe_chat",
            metadata={
                "enterprise_id": enterprise_id,
                "candidate_count": candidate_count,
                "llm_input_chars": len(user_prompt),
                "context_variant": variant,
            },
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            strict_json_instruction=strict_json_instruction,
        )
        return ProbeResult(
            ok=True,
            probe="chat",
            item=str(enterprise_id),
            variant=variant,
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type=type(result).__name__,
            response_preview=_truncate(result),
            payload_chars=len(user_prompt),
            candidate_count=candidate_count,
        )
    except Exception as exc:
        return ProbeResult(
            ok=False,
            probe="chat",
            item=str(enterprise_id),
            variant=variant,
            json_mode=json_mode,
            strict_json_instruction=strict_json_instruction,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            result_type="error",
            error_type=exc.__class__.__name__,
            error=str(exc),
            payload_chars=len(user_prompt),
            candidate_count=candidate_count,
        )


def _run_parallel(factory, iterations: int, concurrency: int) -> list[ProbeResult]:
    if concurrency <= 1:
        return [factory() for _ in range(iterations)]
    results: list[ProbeResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(factory) for _ in range(iterations)]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _summarize(results: list[ProbeResult]) -> dict[str, Any]:
    success = [item for item in results if item.ok]
    failures = [item for item in results if not item.ok]
    by_error: dict[str, int] = {}
    for item in failures:
        key = item.error_type or item.error or "unknown"
        by_error[key] = by_error.get(key, 0) + 1
    return {
        "total": len(results),
        "success": len(success),
        "failure": len(failures),
        "success_rate": round((len(success) / len(results)) * 100, 2) if results else 0.0,
        "avg_elapsed_ms": int(sum(item.elapsed_ms for item in results) / len(results)) if results else 0,
        "errors": by_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe MiniMax Anthropic compatibility stability.")
    subparsers = parser.add_subparsers(dest="probe", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--iterations", type=int, default=10)
    common.add_argument("--concurrency", type=int, default=1)
    common.add_argument("--json-mode", action="store_true")
    common.add_argument("--strict-json-instruction", action="store_true")
    common.add_argument("--max-tokens", type=int, default=2048)
    common.add_argument("--max-attempts", type=int, default=1)

    subparsers.add_parser("minimal", parents=[common])

    document_parser = subparsers.add_parser("document_extract", parents=[common])
    document_parser.add_argument("--doc-ids", nargs="+", type=int, required=True)

    chat_parser = subparsers.add_parser("chat", parents=[common])
    chat_parser.add_argument("--enterprise-id", type=int, required=True)
    chat_parser.add_argument("--question", type=str, required=True)
    chat_parser.add_argument(
        "--context-variant",
        choices=["full", "document_risks", "chunks", "risk_rows"],
        default="full",
    )

    args = parser.parse_args()

    all_results: list[ProbeResult] = []
    if args.probe == "minimal":
        all_results = _run_parallel(
            lambda: _run_minimal_once(
                json_mode=args.json_mode,
                strict_json_instruction=args.strict_json_instruction,
                max_tokens=args.max_tokens,
                max_attempts=args.max_attempts,
            ),
            iterations=args.iterations,
            concurrency=args.concurrency,
        )
    elif args.probe == "document_extract":
        for doc_id in args.doc_ids:
            results = _run_parallel(
                lambda doc_id=doc_id: _run_document_extract_once(
                    doc_id=doc_id,
                    json_mode=args.json_mode,
                    strict_json_instruction=args.strict_json_instruction,
                    max_tokens=args.max_tokens,
                    max_attempts=args.max_attempts,
                ),
                iterations=args.iterations,
                concurrency=args.concurrency,
            )
            all_results.extend(results)
    elif args.probe == "chat":
        all_results = _run_parallel(
            lambda: _run_chat_once(
                enterprise_id=args.enterprise_id,
                question=args.question,
                context_variant=args.context_variant,
                json_mode=args.json_mode,
                strict_json_instruction=args.strict_json_instruction,
                max_tokens=args.max_tokens,
                max_attempts=args.max_attempts,
            ),
            iterations=args.iterations,
            concurrency=args.concurrency,
        )

    output = {
        "probe": args.probe,
        "summary": _summarize(all_results),
        "results": [asdict(item) for item in all_results],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
