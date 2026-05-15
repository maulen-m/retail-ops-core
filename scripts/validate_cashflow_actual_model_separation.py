#!/usr/bin/env python3
"""Validate actual/modelled cashflow separation for paid-truth D1 mode."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.order_cashflow_validation import (  # noqa: E402
    evaluate_actual_model_separation,
    to_json,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cashflow actual/model separation")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--anchor-date", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate_actual_model_separation(args.db, anchor_date=args.anchor_date)
    if args.json:
        print(to_json(report))
    else:
        print(f"status={report['status']}")
        print(f"modeled_receivables_count={report['modeled_receivables_count']}")
        print(
            "legacy_modeled_receivables_diagnostic_count="
            f"{report['legacy_modeled_receivables_diagnostic_count']}"
        )
        print(f"paid_truth_receivables_daily_count={report['paid_truth_receivables_daily_count']}")
        print(f"balance_anchor_fake_cash_in_count={report['balance_anchor_fake_cash_in_count']}")
        print(f"actual_model_cash_overlap_count={report['actual_model_cash_overlap_count']}")
    return 1 if args.strict and report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
