#!/usr/bin/env python3
"""Validate D1 order-line cash-in coverage without mutating the DB."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.order_cashflow_validation import (  # noqa: E402
    evaluate_order_cashflow_coverage,
    to_json,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate D1 order cashflow coverage")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate_order_cashflow_coverage(args.db, as_of=args.as_of)
    if args.json:
        print(to_json(report))
    else:
        print(f"status={report['status']}")
        print(f"candidate_line_count={report['candidate_line_count']}")
        print(f"cash_in_missing_count={report['cash_in_missing_count']}")
        print(f"modeled_receivables_count={report['modeled_receivables_count']}")
        print(f"balance_anchor_fake_cash_in_count={report['balance_anchor_fake_cash_in_count']}")
        print(f"duplicate_cash_in_count={report['duplicate_cash_in_count']}")
        print(f"missing_line_evidence_count={report['missing_line_evidence_count']}")
    return 1 if args.strict and report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
