#!/usr/bin/env python3
"""Validate delivered sales identity coverage in a date window."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_coverage"


class IdentityCoverageError(RuntimeError):
    pass


def validate_no_missing_identity_in_delivered_window(
    *,
    db_path: Path,
    as_of: str,
    lookback_days: int,
    output_root: Path,
    strict: bool,
) -> dict[str, str]:
    if lookback_days <= 0:
        raise IdentityCoverageError("lookback_days must be > 0")
    as_of_day = date.fromisoformat(as_of)
    start_day = as_of_day - timedelta(days=lookback_days - 1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales_fact_v2'"
        ).fetchone()
        if not has_table:
            raise IdentityCoverageError("sales_fact_v2 missing")

        rows = conn.execute(
            """
            SELECT order_id, order_date, store_code, sku_key, my_size, status, return_flag
            FROM sales_fact_v2
            WHERE date(order_date) BETWEEN ? AND ?
              AND UPPER(COALESCE(status, ''))='DELIVERED'
              AND COALESCE(return_flag, 0)=0
            """,
            (start_day.isoformat(), as_of_day.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    missing_sku = []
    missing_size = []
    for row in rows:
        order_id = str(row["order_id"] or "").strip()
        sku_key = str(row["sku_key"] or "").strip()
        my_size = str(row["my_size"] or "").strip()
        if not sku_key:
            missing_sku.append(order_id)
        if not my_size:
            missing_size.append(order_id)

    payload = {
        "as_of": as_of_day.isoformat(),
        "start_date": start_day.isoformat(),
        "lookback_days": lookback_days,
        "delivered_rows": len(rows),
        "missing_sku_count": len(missing_sku),
        "missing_size_count": len(missing_size),
        "missing_sku_sample": missing_sku[:50],
        "missing_size_sample": missing_size[:50],
        "status": "PASS" if not missing_sku and not missing_size else "FAIL",
    }

    out_dir = output_root.resolve() / as_of_day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "identity_coverage_report.json"
    out_md = out_dir / "identity_coverage_report.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(
        "\n".join(
            [
                "# Identity Coverage Report",
                "",
                f"- as_of: `{payload['as_of']}`",
                f"- start_date: `{payload['start_date']}`",
                f"- delivered_rows: `{payload['delivered_rows']}`",
                f"- missing_sku_count: `{payload['missing_sku_count']}`",
                f"- missing_size_count: `{payload['missing_size_count']}`",
                f"- status: `{payload['status']}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and payload["status"] != "PASS":
        raise IdentityCoverageError("identity coverage regression detected")

    return {
        "json_path": str(out_json),
        "md_path": str(out_md),
        "status": payload["status"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate missing identity in delivered sales window")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_no_missing_identity_in_delivered_window(
        db_path=args.db,
        as_of=str(args.as_of),
        lookback_days=int(args.lookback_days),
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"identity_coverage_report_json={report['json_path']}")
    print(f"identity_coverage_report_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if (report["status"] == "PASS" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
