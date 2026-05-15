#!/usr/bin/env python3
"""Preview a redaction-safe Kaspi Pay cash anchor package.

Default: read source files and write redacted validation artifacts only.
No database writes are performed by this preview.
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
    build_cash_anchor_preview,
)


def _parse_expected_stores(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_EXPECTED_STORES
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Kaspi Pay cash anchor records")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cutoff", required=True, help="Decision-grade cutoff date, e.g. 2026-05-03")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--expected-stores", default=None, help="Comma-separated override; default is the five current stores")
    parser.add_argument("--redact", action="store_true", help="Assert generated artifacts are redaction-safe")
    parser.add_argument("--strict", action="store_true", help="Fail non-zero on package/reconciliation/privacy issues")
    args = parser.parse_args()

    run_id = args.run_id or f"cash-anchor-preview-{args.cutoff}"
    try:
        summary = build_cash_anchor_preview(
            source_root=args.source_root,
            cutoff=args.cutoff,
            output_root=args.output_root,
            strict=args.strict,
            redact=args.redact,
            run_id=run_id,
            expected_stores=_parse_expected_stores(args.expected_stores),
        )
    except (CashAnchorError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"status={summary['status']}")
    print(f"stores={summary['store_count']}")
    print(f"output_root={args.output_root}")
    for record in summary["records"]:
        print(
            "store={store_code} anchor={anchor_closing_balance_kzt:.2f} "
            "excluded_txns={post_cutoff_txn_count} report_after_cutoff={sales_report_rows_after_cutoff} "
            "bridge={statement_bridge_error_kzt:.2f}".format(**record)
        )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
