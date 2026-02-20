#!/usr/bin/env python3
"""
Reconcile CRM sales with DB/ledger for a date range.

Reads SALES_KSP_CRM_V3.xlsx, builds canonical keys, and removes DB/ledger
rows that are not present in CRM for the same date range.

Default behavior is dry-run unless --apply is set.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Iterable
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.ingest.sales_ingest import parse_sales_excel, resolve_sales_identity
from core.utils.sku_normalize import normalize_size


DEFAULT_CRM_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _load_size_synonyms(conn) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_size_synonyms'"
    ).fetchone()
    if not rows:
        return {}
    synonyms: dict[str, str] = {}
    for row in conn.execute("SELECT alias, canonical_size FROM dim_size_synonyms").fetchall():
        if not row[0] or not row[1]:
            continue
        key = str(row[0]).upper().replace(" ", "").replace("-", "")
        synonyms[key] = str(row[1]).strip()
    return synonyms


def _normalize_key(
    order_id: str,
    store_code: str,
    kaspi_offer_name: str,
    sku_key: str,
    my_size: str | None,
    synonyms: dict[str, str],
) -> tuple[str, str, str, str, str]:
    size = normalize_size(str(my_size or "").strip(), synonyms=synonyms) or ""
    return (
        str(order_id or "").strip(),
        str(store_code or "").strip(),
        str(kaspi_offer_name or "").strip(),
        str(sku_key or "").strip(),
        size,
    )


def _build_crm_keys(
    records: Iterable[dict],
    conn,
    start_date: date,
    end_date: date,
) -> tuple[dict[tuple, int], int, int]:
    synonyms = _load_size_synonyms(conn)
    qty_map: dict[tuple, int] = defaultdict(int)
    unmapped = 0
    kept = 0

    for rec in records:
        order_date = rec.get("order_date")
        if not order_date or not (start_date <= order_date <= end_date):
            continue

        sku_key, sku_id, my_size = resolve_sales_identity(
            conn,
            rec.get("sku_id"),
            rec.get("sku_key"),
            rec.get("my_size"),
            rec.get("kaspi_offer_name"),
        )
        if not sku_key or not my_size:
            unmapped += 1
            continue

        key = _normalize_key(
            rec.get("order_id"),
            rec.get("store_code"),
            rec.get("kaspi_offer_name"),
            sku_key,
            my_size,
            synonyms,
        )
        qty_map[key] += int(rec.get("quantity") or 0)
        kept += 1

    return qty_map, kept, unmapped


def _fetch_table_rows(conn, table: str, start: date, end: date) -> list[dict]:
    date_field = "order_date"
    if table == "stock_ledger":
        date_field = "event_date"
    rows = conn.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE {date_field} BETWEEN ? AND ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _reconcile_table(
    conn,
    table: str,
    rows: list[dict],
    crm_qty: dict[tuple, int],
    apply: bool,
) -> dict[str, int]:
    synonyms = _load_size_synonyms(conn)
    stats = {"delete": 0, "update": 0, "kept": 0}
    key_to_rows: dict[tuple, list[dict]] = defaultdict(list)

    for row in rows:
        order_id = row.get("order_id") if table != "stock_ledger" else row.get("reference_id")
        store_code = row.get("store_code")
        kaspi_offer_name = row.get("kaspi_offer_name")
        sku_key = row.get("sku_key")
        my_size = row.get("my_size")
        key = _normalize_key(order_id, store_code, kaspi_offer_name, sku_key, my_size, synonyms)
        key_to_rows[key].append(row)

    for key, grouped in key_to_rows.items():
        target_qty = crm_qty.get(key)
        if target_qty is None:
            for row in grouped:
                stats["delete"] += 1
                if apply:
                    _delete_row(conn, table, row)
            continue

        # Calculate current total qty in DB for this key
        if table == "stock_ledger":
            current_qty = sum(int(-(row.get("qty_change") or 0)) for row in grouped)
        else:
            current_qty = sum(int(row.get("quantity") or 0) for row in grouped)

        if current_qty <= target_qty:
            stats["kept"] += len(grouped)
            continue

        # Remove excess rows/events until quantities match
        excess = current_qty - target_qty
        # Prefer deleting highest id/ledger_id entries first
        if table == "stock_ledger":
            id_field = "ledger_id"
        elif table == "sales_fact_v2":
            id_field = "sale_id"
        else:
            id_field = "id"
        grouped_sorted = sorted(grouped, key=lambda r: r.get(id_field, 0), reverse=True)

        for row in grouped_sorted:
            if excess <= 0:
                stats["kept"] += 1
                continue
            if table == "stock_ledger":
                qty = int(-(row.get("qty_change") or 0))
            else:
                qty = int(row.get("quantity") or 0)
            if qty <= excess:
                stats["delete"] += 1
                excess -= qty
                if apply:
                    _delete_row(conn, table, row)
            else:
                # Reduce quantity for this row to match remaining
                new_qty = qty - excess
                if table == "stock_ledger":
                    new_change = -new_qty
                    stats["update"] += 1
                    if apply:
                        conn.execute(
                            "UPDATE stock_ledger SET qty_change = ? WHERE ledger_id = ?",
                            (new_change, row["ledger_id"]),
                        )
                else:
                    stats["update"] += 1
                    if apply:
                        conn.execute(
                            f"UPDATE {table} SET quantity = ? WHERE id = ?",
                            (new_qty, row["id"]),
                        )
                excess = 0
                stats["kept"] += 1

    return stats


def _delete_row(conn, table: str, row: dict) -> None:
    if table == "stock_ledger":
        conn.execute("DELETE FROM stock_ledger WHERE ledger_id = ?", (row["ledger_id"],))
    elif table == "sales_fact_v2":
        conn.execute("DELETE FROM sales_fact_v2 WHERE sale_id = ?", (row["sale_id"],))
    else:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile CRM sales with DB/ledger for a date range")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--file", type=Path, default=DEFAULT_CRM_PATH, help="CRM workbook path")
    parser.add_argument("--sheet", default="SALES_KSP_CRM_1", help="Sheet name")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply deletions/updates (default: dry-run)")
    args = parser.parse_args()

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    if not args.file.exists():
        raise SystemExit(f"CRM workbook not found: {args.file}")

    print(f"CRM source: {args.file} [{args.sheet}]")
    print(f"Date range: {start_date} -> {end_date}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")

    records = parse_sales_excel(str(args.file), args.sheet)

    with get_db(args.db) as conn:
        crm_qty, kept, unmapped = _build_crm_keys(records, conn, start_date, end_date)
        print(f"CRM records kept: {kept}")
        print(f"CRM records unmapped (skipped): {unmapped}")
        print(f"CRM unique keys: {len(crm_qty)}")

        tables = ["fact_sales", "sales_fact_v2", "stock_ledger"]
        for table in tables:
            rows = _fetch_table_rows(conn, table, start_date, end_date)
            stats = _reconcile_table(conn, table, rows, crm_qty, args.apply)
            print(f"{table}: delete={stats['delete']} update={stats['update']} kept={stats['kept']}")

        if args.apply:
            conn.commit()
            print("DB changes committed.")
        else:
            conn.rollback()
            print("Dry-run complete (no DB changes).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
