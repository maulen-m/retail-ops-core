#!/usr/bin/env python3
"""Validate production readiness based on dashboard output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.validation.production_readiness import (
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    evaluate_production_readiness,
)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"ERROR: Dashboard output not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: Invalid JSON in {path}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate production readiness using dashboard output."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DASHBOARD_PATH,
        help="Dashboard JSON path (default: exports/po_dashboard_data.json)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite DB path for recent-sales checks (default: db/app.db)",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip DB-based recent-sales checks",
    )
    args = parser.parse_args()

    output = _load_json(args.input)
    db_path = None if args.no_db else args.db
    report = evaluate_production_readiness(output, db_path=db_path)

    print("Production readiness summary:")
    for key, value in report.details.items():
        print(f"  {key}: {value}")

    if report.blockers:
        print("\nBLOCKERS:")
        for blocker in report.blockers:
            print(f"  - {blocker}")
        return 1

    if report.warnings:
        print("\nWARNINGS:")
        for warning in report.warnings:
            print(f"  - {warning}")

    print("\nREADY: Production readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
