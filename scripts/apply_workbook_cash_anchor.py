#!/usr/bin/env python3
"""Persist governed workbook cash anchor records.

Default: dry run. Apply requires ENABLE_CASHFLOW_ANCHOR_WRITE=1 and --apply.
This script writes only cashflow_cash_anchor rows; it never creates order-level
CASH_IN events and never treats reserve cash as operating cash.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.workbook_cash_anchor import (  # noqa: E402
    DEFAULT_EXPECTED_GRAND_TOTAL_WITH_RESERVE_KZT,
    DEFAULT_EXPECTED_OPERATING_TOTAL_KZT,
    DEFAULT_EXPECTED_RESERVE_KZT,
    DEFAULT_EXPECTED_STORES,
    DEFAULT_FX_BASIS,
    SHEET_NAME,
    WorkbookCashAnchorError,
    apply_workbook_cash_anchor,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _parse_expected_stores(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_EXPECTED_STORES
    return tuple(part.strip().upper() for part in value.split(",") if part.strip())


def _fx_basis_from_args(args: argparse.Namespace) -> dict[str, Decimal]:
    fx = dict(DEFAULT_FX_BASIS)
    fx["USD"] = Decimal(str(args.usd_kzt))
    fx["USDT"] = Decimal(str(args.usdt_kzt))
    fx["RUB"] = Decimal(str(args.rub_kzt))
    fx["CNY"] = Decimal(str(args.cny_kzt))
    return fx


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply workbook Cash_Balances anchor records")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--sheet", default=SHEET_NAME)
    parser.add_argument("--snapshot-ts", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-stores", default=None)
    parser.add_argument("--expected-operating-total-kzt", default=str(DEFAULT_EXPECTED_OPERATING_TOTAL_KZT))
    parser.add_argument("--expected-reserve-kzt", default=str(DEFAULT_EXPECTED_RESERVE_KZT))
    parser.add_argument(
        "--expected-grand-total-with-reserve-kzt",
        default=str(DEFAULT_EXPECTED_GRAND_TOTAL_WITH_RESERVE_KZT),
    )
    parser.add_argument("--usd-kzt", default="485")
    parser.add_argument("--usdt-kzt", default="485")
    parser.add_argument("--rub-kzt", default="6")
    parser.add_argument("--cny-kzt", default="72")
    parser.add_argument("--backup-path", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Write anchor rows; requires ENABLE_CASHFLOW_ANCHOR_WRITE=1")
    args = parser.parse_args()

    try:
        summary = apply_workbook_cash_anchor(
            db_path=args.db,
            workbook_path=args.workbook,
            sheet_name=args.sheet,
            snapshot_label=args.snapshot_ts,
            output_root=args.output_root,
            run_id=args.run_id,
            apply=bool(args.apply),
            expected_stores=_parse_expected_stores(args.expected_stores),
            fx_basis=_fx_basis_from_args(args),
            expected_operating_total_kzt=Decimal(str(args.expected_operating_total_kzt)),
            expected_reserve_kzt=Decimal(str(args.expected_reserve_kzt)),
            expected_grand_total_with_reserve_kzt=Decimal(
                str(args.expected_grand_total_with_reserve_kzt)
            ),
            backup_path=args.backup_path,
        )
    except (WorkbookCashAnchorError, FileNotFoundError, RuntimeError, ValueError) as exc:
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
    print(f"operating_total_kzt={summary['snapshot']['operating_total_kzt']}")
    print(f"reserve_kzt={summary['snapshot']['reserve_context']['reserve_kzt']}")
    print(f"grand_total_with_reserve_kzt={summary['snapshot']['grand_total_with_reserve_kzt']}")
    print(f"balance_check_csv={summary['balance_check_csv']}")
    print(f"output_root={args.output_root}")
    if not args.apply:
        print("DRY RUN: no DB writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
