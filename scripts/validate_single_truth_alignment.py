#!/usr/bin/env python3
"""Validate cross-realm single-truth alignment for PO dashboard output."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import validate_cashflow_invariants
from scripts import validate_inventory_cost_drift


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _normalize_size(size: str | None) -> str:
    return str(size or "").strip().upper().replace(" ", "").replace("-", "")


def _po_has_part_rows(conn: sqlite3.Connection, po_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM po_line
        WHERE po_id = ?
          AND COALESCE(TRIM(po_part_id), '') <> ''
        LIMIT 1
        """,
        (po_id,),
    ).fetchone()
    return row is not None


def _load_po_totals(conn: sqlite3.Connection, po_id: str) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    sku_totals: dict[str, int] = {}
    size_totals: dict[tuple[str, str], int] = {}
    columns = [row[1] for row in conn.execute("PRAGMA table_info(po_line)").fetchall()]
    part_filter = ""
    if "po_part_id" in columns and _po_has_part_rows(conn, po_id):
        part_filter = "AND COALESCE(TRIM(po_part_id), '') <> ''"
    rows = conn.execute(
        f"""
        SELECT sku_key, my_size, SUM(order_qty) AS qty
        FROM po_line
        WHERE po_id = ?
        {part_filter}
        GROUP BY sku_key, my_size
        """,
        (po_id,),
    ).fetchall()
    for row in rows:
        sku_key = str(row["sku_key"] or "").strip()
        if not sku_key:
            continue
        size = _normalize_size(row["my_size"])
        qty = int(row["qty"] or 0)
        sku_totals[sku_key] = sku_totals.get(sku_key, 0) + qty
        size_totals[(sku_key, size)] = size_totals.get((sku_key, size), 0) + qty
    return (sku_totals, size_totals)


def _load_active_skus(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "dim_sku"):
        return set()
    rows = conn.execute(
        """
        SELECT sku_key, COALESCE(product_type, '') AS product_type
        FROM dim_sku
        WHERE COALESCE(active_flag, 1) = 1
        """
    ).fetchall()
    active: set[str] = set()
    for row in rows:
        sku_key = str(row["sku_key"] or "").strip()
        if not sku_key:
            continue
        product_type = str(row["product_type"] or "").strip().upper()
        if product_type == "BAG":
            continue
        active.add(sku_key)
    return active


def validate_alignment_payload(
    payload: dict,
    db_path: Path,
    run_cashflow: bool = True,
    run_drift: bool = True,
) -> list[str]:
    errors: list[str] = []

    if not db_path.exists():
        return [f"DB path not found: {db_path}"]

    pos = payload.get("pos", {})
    if not isinstance(pos, dict) or not pos:
        return ["dashboard output missing pos data"]

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        has_dim_sku = _table_exists(conn, "dim_sku")
        active_skus = _load_active_skus(conn)
        if not _table_exists(conn, "po_line"):
            errors.append("po_line table missing (cannot verify REAL_ARCHIVE quantities)")
        else:
            for po_name, po_data in pos.items():
                if not isinstance(po_data, dict):
                    continue
                if po_data.get("po_kind") != "REAL_ARCHIVE":
                    continue

                po_id = str(po_data.get("po_name") or po_name)
                sku_totals_db, size_totals_db = _load_po_totals(conn, po_id)
                if not sku_totals_db:
                    errors.append(f"{po_id}: no po_line rows found for REAL_ARCHIVE validation")
                    continue

                sku_rows = po_data.get("sku_level") or []
                size_rows = po_data.get("size_level") or []
                sku_totals_payload = {
                    str(row.get("sku_key")): int(row.get("po_qty_total", 0) or 0)
                    for row in sku_rows
                    if row.get("sku_key")
                }
                for sku_key, qty_db in sku_totals_db.items():
                    qty_payload = sku_totals_payload.get(sku_key)
                    if qty_payload is None:
                        if (not has_dim_sku) or (sku_key in active_skus):
                            errors.append(f"{po_id}/{sku_key}: missing from dashboard sku_level")
                    elif qty_payload != qty_db:
                        errors.append(
                            f"{po_id}/{sku_key}: po_line qty={qty_db} != dashboard qty={qty_payload}"
                        )

                size_totals_payload: dict[tuple[str, str], int] = {}
                for row in size_rows:
                    sku_key = row.get("sku_key")
                    if not sku_key:
                        continue
                    key = (str(sku_key), _normalize_size(row.get("size")))
                    size_totals_payload[key] = size_totals_payload.get(key, 0) + int(
                        row.get("order_qty", 0) or 0
                    )
                for key, qty_db in size_totals_db.items():
                    qty_payload = size_totals_payload.get(key)
                    if qty_payload is None:
                        if (not has_dim_sku) or (key[0] in active_skus):
                            errors.append(f"{po_id}/{key[0]}/{key[1]}: missing from dashboard size_level")
                    elif qty_payload != qty_db:
                        errors.append(
                            f"{po_id}/{key[0]}/{key[1]}: po_line qty={qty_db} != dashboard qty={qty_payload}"
                        )

            # Baseline date monotonicity applies to PLAN rows (future projections),
            # not REAL_ARCHIVE rows whose baseline snapshot can intentionally be newer.
            for po_name, po_data in pos.items():
                if not isinstance(po_data, dict):
                    continue
                if po_data.get("po_kind") == "REAL_ARCHIVE":
                    continue
                po_id = str(po_data.get("po_name") or po_name)
                po_message_date = po_data.get("po_message_date")
                for row in (po_data.get("sku_level") or []):
                    sku_key = row.get("sku_key")
                    if not sku_key:
                        continue
                    baseline = row.get("baseline_snapshot_date")
                    if baseline and po_message_date and str(baseline) > str(po_message_date):
                        errors.append(
                            f"{po_id}/{sku_key}: baseline_snapshot_date {baseline} > po_message_date {po_message_date}"
                        )
    finally:
        conn.close()

    if run_cashflow:
        rc = validate_cashflow_invariants.validate(db_path, tolerance=0.01)
        if rc != 0:
            errors.append("cashflow invariants failed")

    if run_drift:
        rc = validate_inventory_cost_drift.validate_drift(
            db_path,
            as_of=None,
            tolerance_pct=0.02,
            tolerance_kzt=50000.0,
        )
        if rc != 0:
            errors.append("inventory cost drift validation failed")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate single-truth alignment")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DASHBOARD_PATH,
        help="Dashboard JSON path (default: exports/po_dashboard_data.json)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite DB path (default: db/app.db)",
    )
    parser.add_argument(
        "--skip-cashflow",
        action="store_true",
        help="Skip validate_cashflow_invariants integration",
    )
    parser.add_argument(
        "--skip-drift",
        action="store_true",
        help="Skip validate_inventory_cost_drift integration",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: dashboard output missing: {args.input}")
        return 1
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid dashboard JSON: {exc}")
        return 1

    errors = validate_alignment_payload(
        payload,
        db_path=args.db,
        run_cashflow=not args.skip_cashflow,
        run_drift=not args.skip_drift,
    )
    if errors:
        print("ALIGNMENT FAILURES:")
        for err in errors[:30]:
            print(f"  - {err}")
        if len(errors) > 30:
            print(f"  ... {len(errors) - 30} more")
        return 1

    print("OK: single-truth alignment passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
