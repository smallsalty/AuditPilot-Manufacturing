from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import DocumentEventFeature, DocumentExtractResult, DocumentMeta
from app.utils.display_text import clean_document_title, clean_file_name_like


def backfill_clean_display_fields(*, enterprise_id: int | None = None) -> dict[str, int]:
    stats = {
        "documents_updated": 0,
        "extracts_updated": 0,
        "features_updated": 0,
    }
    with SessionLocal() as db:
        document_stmt = select(DocumentMeta)
        if enterprise_id is not None:
            document_stmt = document_stmt.where(DocumentMeta.enterprise_id == enterprise_id)
        for document in db.scalars(document_stmt).all():
            updated = False
            clean_name = clean_document_title(document.document_name)
            if clean_name and clean_name != document.document_name:
                document.document_name = clean_name
                updated = True
            if document.file_name:
                suffix = ""
                if "." in document.file_name:
                    suffix = f".{document.file_name.rsplit('.', 1)[-1]}"
                clean_file_name = clean_file_name_like(document.file_name, fallback_suffix=suffix or ".pdf")
                if clean_file_name != document.file_name:
                    document.file_name = clean_file_name
                    updated = True
            if updated:
                stats["documents_updated"] += 1

        extract_stmt = select(DocumentExtractResult)
        if enterprise_id is not None:
            extract_stmt = extract_stmt.join(DocumentMeta, DocumentMeta.id == DocumentExtractResult.document_id).where(
                DocumentMeta.enterprise_id == enterprise_id
            )
        for extract in db.scalars(extract_stmt).all():
            updated = False
            clean_title = clean_document_title(extract.title)
            if clean_title and clean_title != extract.title:
                extract.title = clean_title
                updated = True
            if extract.subject:
                clean_subject = clean_document_title(extract.subject)
                if clean_subject != extract.subject:
                    extract.subject = clean_subject
                    updated = True
            try:
                payload = json.loads(extract.content)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                payload_updated = False
                if payload.get("title"):
                    clean_payload_title = clean_document_title(payload["title"])
                    if clean_payload_title != payload["title"]:
                        payload["title"] = clean_payload_title
                        payload_updated = True
                if payload.get("subject"):
                    clean_payload_subject = clean_document_title(payload["subject"])
                    if clean_payload_subject != payload["subject"]:
                        payload["subject"] = clean_payload_subject
                        payload_updated = True
                if payload_updated:
                    extract.content = json.dumps(payload, ensure_ascii=False)
                    updated = True
            if updated:
                stats["extracts_updated"] += 1

        feature_stmt = select(DocumentEventFeature)
        if enterprise_id is not None:
            feature_stmt = feature_stmt.where(DocumentEventFeature.enterprise_id == enterprise_id)
        for feature in db.scalars(feature_stmt).all():
            updated = False
            if feature.subject:
                clean_subject = clean_document_title(feature.subject)
                if clean_subject != feature.subject:
                    feature.subject = clean_subject
                    updated = True
            payload = feature.payload if isinstance(feature.payload, dict) else None
            if payload and payload.get("subject"):
                clean_payload_subject = clean_document_title(payload["subject"])
                if clean_payload_subject != payload["subject"]:
                    feature.payload = {**payload, "subject": clean_payload_subject}
                    updated = True
            if updated:
                stats["features_updated"] += 1

        db.commit()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill cleaned display fields for synced documents.")
    parser.add_argument("--enterprise-id", type=int, default=None)
    args = parser.parse_args()
    result = backfill_clean_display_fields(enterprise_id=args.enterprise_id)
    print(json.dumps(result, ensure_ascii=False))
