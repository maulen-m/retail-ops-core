#!/usr/bin/env python3
"""Persist redaction-safe Kaspi Pay cash anchor records.

Default: dry run. Apply requires ENABLE_CASHFLOW_ANCHOR_WRITE=1 and --apply.
This script writes only the dedicated cash anchor table; it never creates
order-level CASH_IN events from balance anchors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.kaspi_pay_cash_anchor import (  # noqa: E402
    DEFAULT_EXPECTED_STORES,
    CashAnchorError,
    apply_cash_anchor,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _parse_expected_stores(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_EXPECTED_STORES
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Kaspi Pay cash anchor records")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cutoff", required=True, help="Decision-grade cutoff date, e.g. 2026-05-03")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-stores", default=None, help="Comma-separated override; default is the five current stores")
    parser.add_argument("--redact", action="store_true", help="Assert generated artifacts are redaction-safe")
    parser.add_argument("--strict", action="store_true", help="Fail non-zero on package/reconciliation/privacy issues")
    parser.add_argument("--apply", action="store_true", help="Write anchor rows; requires ENABLE_CASHFLOW_ANCHOR_WRITE=1")
    args = parser.parse_args()

    try:
        summary = apply_cash_anchor(
            db_path=args.db,
            source_root=args.source_root,
            cutoff=args.cutoff,
            run_id=args.run_id,
            output_root=args.output_root,
            strict=args.strict,
            redact=args.redact,
            apply=args.apply,
            expected_stores=_parse_expected_stores(args.expected_stores),
        )
    except (CashAnchorError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    apply_summary = summary["apply"]
    print(f"status={summary['status']}")
    print(f"applied={apply_summary['applied']}")
    print(f"candidate_anchor_records={apply_summary['candidate_anchor_records']}")
    print(f"existing_anchor_records={apply_summary['existing_anchor_records']}")
    print(f"would_insert_anchor_records={apply_summary['would_insert_anchor_records']}")
    print(f"inserted_anchor_records={apply_summary['inserted_anchor_records']}")
    print(f"cashflow_events_created={apply_summary['cashflow_events_created']}")
    print(f"output_root={args.output_root}")
    if not args.apply:
        print("DRY RUN: no DB writes.")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
