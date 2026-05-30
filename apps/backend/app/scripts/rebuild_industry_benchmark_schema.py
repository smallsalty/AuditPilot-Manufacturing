from __future__ import annotations

import argparse

from app.core.db import rebuild_industry_benchmark_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drop legacy industry tables and create the official EastMoney benchmark schema.")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive industry-only schema rebuild.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.yes:
        raise SystemExit("Refusing to rebuild industry tables without --yes.")
    rebuild_industry_benchmark_schema(confirm=True)
    print("Industry benchmark schema rebuilt.")


if __name__ == "__main__":
    main()
