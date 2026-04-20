from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from app.core.db import SessionLocal
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.audit_sync_service import AuditSyncService
from app.services.document_service import DocumentService
from app.services.risk_analysis_service import RiskAnalysisService


logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _int_value(payload: dict[str, Any] | None, key: str) -> int:
    if not payload:
        return 0
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _should_refresh_risk(sync_result: dict[str, Any], parse_result: dict[str, Any]) -> bool:
    return any(
        [
            _int_value(sync_result, "documents_inserted") > 0,
            _int_value(sync_result, "events_inserted") > 0,
            _int_value(parse_result, "documents") > 0,
            _int_value(parse_result, "events") > 0,
        ]
    )


def _enterprise_label(enterprise: Any) -> dict[str, Any]:
    return {
        "enterprise_id": getattr(enterprise, "id", None),
        "enterprise_name": getattr(enterprise, "name", None),
        "ticker": getattr(enterprise, "ticker", None),
    }


def _risk_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "result_count": len(result.get("results") or []),
        "matched_event_count": result.get("matched_event_count", 0),
        "audit_focus_items": len(((result.get("audit_focus") or {}).get("items") or [])),
    }


def run_daily_monitor(
    *,
    enterprise_ids: list[int] | None = None,
    limit: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    db = SessionLocal()
    sync_service = AuditSyncService()
    document_service = DocumentService()
    risk_service = RiskAnalysisService()
    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "source": "cninfo",
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "enterprise_total": 0,
        "success_enterprises": 0,
        "skipped_enterprises": 0,
        "failed_enterprises": 0,
        "announcements_fetched": 0,
        "documents_inserted": 0,
        "events_inserted": 0,
        "parse_queued": 0,
        "parsed_documents": 0,
        "parsed_events": 0,
        "risk_analysis_runs": 0,
        "failures": [],
        "enterprises": [],
    }

    try:
        repo = EnterpriseRepository(db)
        enterprises = repo.list_enterprises(official_only=False)
        if enterprise_ids:
            requested_ids = set(enterprise_ids)
            enterprises = [item for item in enterprises if item.id in requested_ids]
            found_ids = {item.id for item in enterprises}
            for missing_id in sorted(requested_ids - found_ids):
                summary["failed_enterprises"] += 1
                summary["failures"].append(
                    {
                        "enterprise_id": missing_id,
                        "stage": "load_enterprise",
                        "error": "enterprise_not_found",
                    }
                )
        if limit is not None and limit > 0:
            enterprises = enterprises[:limit]

        summary["enterprise_total"] = len(enterprises)

        for enterprise in enterprises:
            item_summary: dict[str, Any] = {**_enterprise_label(enterprise), "status": "pending"}
            stage = "sync"
            if not getattr(enterprise, "ticker", None):
                item_summary.update({"status": "skipped", "reason": "missing_ticker"})
                summary["skipped_enterprises"] += 1
                summary["enterprises"].append(item_summary)
                continue

            try:
                logger.info("daily cninfo monitor sync started enterprise_id=%s", enterprise.id)
                sync_result = sync_service.sync_company(
                    db,
                    enterprise.id,
                    sources=["cninfo"],
                    date_from=date_from,
                    date_to=date_to,
                )

                stage = "parse_queue"
                parse_result = document_service.process_parse_queue(db, enterprise_id=enterprise.id)

                stage = "risk_analysis"
                risk_result = None
                risk_ran = False
                if _should_refresh_risk(sync_result, parse_result):
                    risk_result = risk_service.run(db, enterprise.id)
                    risk_ran = True

                summary["announcements_fetched"] += _int_value(sync_result, "announcements_fetched")
                summary["documents_inserted"] += _int_value(sync_result, "documents_inserted")
                summary["events_inserted"] += _int_value(sync_result, "events_inserted")
                summary["parse_queued"] += _int_value(sync_result, "parse_queued")
                summary["parsed_documents"] += _int_value(parse_result, "documents")
                summary["parsed_events"] += _int_value(parse_result, "events")
                if risk_ran:
                    summary["risk_analysis_runs"] += 1

                item_summary.update(
                    {
                        "status": "success",
                        "sync": sync_result,
                        "parsed": parse_result,
                        "risk_analysis_ran": risk_ran,
                        "risk_analysis": _risk_summary(risk_result),
                    }
                )
                summary["success_enterprises"] += 1
                logger.info(
                    "daily cninfo monitor enterprise finished enterprise_id=%s documents_inserted=%s events_inserted=%s parsed_documents=%s parsed_events=%s risk_ran=%s",
                    enterprise.id,
                    _int_value(sync_result, "documents_inserted"),
                    _int_value(sync_result, "events_inserted"),
                    _int_value(parse_result, "documents"),
                    _int_value(parse_result, "events"),
                    risk_ran,
                )
            except Exception as exc:
                db.rollback()
                summary["failed_enterprises"] += 1
                failure = {
                    **_enterprise_label(enterprise),
                    "stage": stage,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
                summary["failures"].append(failure)
                item_summary.update({"status": "failed", **failure})
                logger.exception(
                    "daily cninfo monitor enterprise failed enterprise_id=%s stage=%s",
                    getattr(enterprise, "id", None),
                    stage,
                )
            finally:
                summary["enterprises"].append(item_summary)
    finally:
        db.close()
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run daily CNInfo announcement monitoring.")
    parser.add_argument("--enterprise-id", action="append", type=int, dest="enterprise_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--date-from", type=str)
    parser.add_argument("--date-to", type=str)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run_daily_monitor(
        enterprise_ids=args.enterprise_ids,
        limit=args.limit,
        date_from=_parse_date(args.date_from),
        date_to=_parse_date(args.date_to),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("failed_enterprises") else 0


if __name__ == "__main__":
    raise SystemExit(main())
