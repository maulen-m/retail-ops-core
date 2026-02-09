#!/usr/bin/env python3
"""
Reconcile sales_fact_v2 line economics from CRM workbook anchor rows.

Default: DRY RUN.
Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ingest.sales_ingest import parse_sales_excel

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_WORKBOOK = PROJECT_ROOT.parent / "Autonomous_business 2" / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return None


def _match_sale_id(conn: sqlite3.Connection, record: dict[str, Any]) -> int | None:
    params = (
        str(record.get("order_id") or ""),
        str(record.get("store_code") or ""),
        str(record.get("kaspi_offer_name") or ""),
        str(record.get("sku_key") or ""),
        str(record.get("my_size") or ""),
    )
    row = conn.execute(
        """
        SELECT sale_id
        FROM sales_fact_v2
        WHERE order_id = ?
          AND store_code = ?
          AND kaspi_offer_name = ?
          AND sku_key = ?
          AND COALESCE(my_size, '') = ?
        ORDER BY sale_id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row:
        return int(row["sale_id"])
    return None


def reconcile_sales_anchor_day(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    since: str | None = None,
    until: str | None = None,
    apply: bool = False,
) -> dict[str, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")
    if not workbook_path.exists():
        raise FileNotFoundError(f"workbook not found: {workbook_path}")
    if apply and os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required with --apply")

    since_iso = _to_iso_date(since) if since else None
    until_iso = _to_iso_date(until) if until else None

    rows = parse_sales_excel(str(workbook_path), sheet_name=sheet_name)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        day = _to_iso_date(row.get("order_date"))
        if day is None:
            continue
        if since_iso and day < since_iso:
            continue
        if until_iso and day > until_iso:
            continue
        net_rev = row.get("net_rev")
        if net_rev is None:
            continue
        filtered.append(row)

    summary = {
        "candidates": 0,
        "matched": 0,
        "missing": 0,
        "would_update": 0,
        "updated": 0,
    }
    if not filtered:
        return summary

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for row in filtered:
            summary["candidates"] += 1
            sale_id = _match_sale_id(conn, row)
            if sale_id is None:
                summary["missing"] += 1
                continue
            summary["matched"] += 1

            current = conn.execute(
                "SELECT net_rev, delivery_fee FROM sales_fact_v2 WHERE sale_id = ?",
                (sale_id,),
            ).fetchone()
            assert current is not None

            workbook_net = float(row.get("net_rev") or 0.0)
            workbook_fee = row.get("delivery_fee")
            if workbook_fee is None:
                workbook_fee = current["delivery_fee"]
            workbook_fee_f = float(workbook_fee or 0.0)

            current_net = float(current["net_rev"] or 0.0)
            current_fee = float(current["delivery_fee"] or 0.0)
            if abs(current_net - workbook_net) <= 1e-6 and abs(current_fee - workbook_fee_f) <= 1e-6:
                continue

            summary["would_update"] += 1
            if apply:
                conn.execute(
                    """
                    UPDATE sales_fact_v2
                    SET net_rev = ?, delivery_fee = ?
                    WHERE sale_id = ?
                    """,
                    (workbook_net, workbook_fee_f, sale_id),
                )
                summary["updated"] += 1

        if apply:
            conn.commit()
    finally:
        conn.close()

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile sales_fact_v2 economics from CRM workbook anchor")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--since", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--until", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = reconcile_sales_anchor_day(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet,
        since=args.since,
        until=args.until,
        apply=args.apply,
    )
    print(f"candidates={result['candidates']}")
    print(f"matched={result['matched']}")
    print(f"missing={result['missing']}")
    print(f"would_update={result['would_update']}")
    print(f"updated={result['updated']}")
    print("APPLY" if args.apply else "DRY RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
