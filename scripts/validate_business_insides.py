#!/usr/bin/env python3
"""Validate single-truth business-insides inputs and generated snapshot freshness."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_business_insides import compute_sales_metrics
from core.cashflow.paid_capital_truth import compute_paid_capital_truth

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BANK = PROJECT_ROOT / "config" / "bank_accounts.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"


def validate_business_insides(
    *,
    db_path: Path = DEFAULT_DB,
    bank_accounts_path: Path = DEFAULT_BANK,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    as_of: str | date | None = None,
    tolerance_kzt: float = 1.0,
) -> list[str]:
    errors: list[str] = []
    as_of_date = date.fromisoformat(as_of) if isinstance(as_of, str) else (as_of or date.today())
    metrics = compute_sales_metrics(db_path=db_path, as_of=as_of_date)
    capital = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of_date,
    )

    if metrics["total_rows"] <= 0:
        errors.append("sales metrics: no DELIVERED rows in last 30d window")
    if metrics["avg_30d_net_rev_kzt"] <= 0:
        errors.append("sales metrics: avg_30d_net_rev_kzt is non-positive")

    expected_total = (
        float(capital["cash_actual_kzt"])
        + float(capital["inventory_on_hand_paid_kzt"])
        + float(capital["inventory_inbound_paid_kzt"])
        + float(capital["inventory_on_delivery_paid_kzt"])
    )
    if abs(expected_total - float(capital["total_capital_paid_kzt"])) > float(tolerance_kzt):
        errors.append(
            "capital consistency mismatch: total_capital_paid_kzt != sum(component balances)"
        )

    snapshot = output_dir / f"BUSINESS_INSIDES_{as_of_date.isoformat()}.md"
    snapshot_alt = output_dir / "snapshots" / f"BUSINESS_INSIDES_{as_of_date.isoformat()}.md"
    if not snapshot.exists() and not snapshot_alt.exists():
        errors.append(
            f"business-insides snapshot missing for {as_of_date.isoformat()} "
            f"(expected {snapshot} or {snapshot_alt})"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate business-insides truth snapshot")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--bank-accounts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--tolerance-kzt", type=float, default=1.0)
    args = parser.parse_args()

    errors = validate_business_insides(
        db_path=args.db,
        bank_accounts_path=args.bank_accounts,
        output_dir=args.output_dir,
        as_of=args.as_of,
        tolerance_kzt=args.tolerance_kzt,
    )
    if errors:
        print("BUSINESS_INSIDES FAILURES:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK: business-insides validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
