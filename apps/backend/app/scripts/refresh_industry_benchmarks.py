from __future__ import annotations

import argparse
import json

from app.core.db import SessionLocal, create_all
from app.services.industry_benchmark_refresh_service import IndustryBenchmarkRefreshService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh cached AkShare industry benchmark snapshots.")
    parser.add_argument("--enterprise-id", dest="enterprise_ids", action="append", type=int, help="Enterprise id to refresh. Can be repeated.")
    parser.add_argument("--period", help="Requested report period, for example 2024FY or 2024Q3.")
    parser.add_argument("--limit", type=int, help="Limit enterprises when enterprise id is not specified.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_all()
    with SessionLocal() as db:
        summary = IndustryBenchmarkRefreshService().refresh(
            db,
            enterprise_ids=args.enterprise_ids,
            period=args.period,
            limit=args.limit,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

