#!/usr/bin/env python3
"""Validate that orders for the cutoff date have sizes before shipping."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import get_cutoff_date_almaty
from core.validation.day_complete import evaluate_day_complete


def _resolve_cutoff_date(value: str | None) -> date:
    if not value:
        return get_cutoff_date_almaty()
    token = value.strip().lower()
    if token == "today":
        return date.today()
    if token == "yesterday":
        return date.today() - timedelta(days=1)
    if token == "tomorrow":
        return date.today() + timedelta(days=1)
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate day-complete sizing gate")
    parser.add_argument(
        "--cutoff-date",
        type=str,
        default=None,
        help="Cutoff date (YYYY-MM-DD). Default: yesterday in Asia/Almaty",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=PROJECT_ROOT / "db" / "app.db",
        help="SQLite DB path (default: db/app.db)",
    )
    args = parser.parse_args()

    cutoff_date = _resolve_cutoff_date(args.cutoff_date)
    report = evaluate_day_complete(args.db_path, cutoff_date)

    print("Day complete validation")
    print(f"Cutoff date: {report.details.get('cutoff_date')}")

    if report.errors:
        print("\nERRORS:")
        for err in report.errors:
            print(f"  - {err}")
        return 1

    print(f"Eligible orders: {report.details.get('eligible_orders', 0)}")
    print(f"Violations: {report.details.get('violations', 0)}")
    print(f"Skipped missing line items: {report.details.get('skipped_missing_line_items', 0)}")
    print(
        "Skipped cancelled/returned archive: "
        f"{report.details.get('skipped_cancelled_returned_archive', 0)}"
    )
    print(
        "Manual offer text classifications: "
        f"{report.details.get('manual_offer_text_classifications', 0)}"
    )

    if report.ok:
        print("\nDAY COMPLETE: OK")
        return 0

    print("\nDAY COMPLETE: FAIL")
    for violation in report.violations:
        print(
            "  - order_id={order_id} sku_id={sku_id} store={store} planned={planned} "
            "internal_status={internal} kaspi_status={kaspi}".format(
                order_id=violation.order_id,
                sku_id=violation.sku_id,
                store=violation.store_code,
                planned=violation.planned_ship_date,
                internal=violation.internal_status,
                kaspi=violation.kaspi_status,
            )
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
