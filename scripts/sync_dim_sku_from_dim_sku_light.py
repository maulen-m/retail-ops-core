#!/usr/bin/env python3
"""Restore dim_sku values from the live DIM_SKU_light_v7 workbook surface."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.excel.dim_sku_light_parser import parse_dim_sku_light


DEFAULT_XLSX = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/"
    "Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_SHEET = "DIM_SKU_light_v7"
_GUARD_KEY = "dim_sku_weight_kg"
_GUARD_SOURCE = "sync_dim_sku_from_dim_sku_light"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _activate_weight_guard(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "dim_sku_weight_write_guard"):
        return False
    conn.execute(
        """
        INSERT OR IGNORE INTO dim_sku_weight_write_guard
        (guard_key, allow_updates, source, expires_at, updated_at)
        VALUES (?, 0, NULL, NULL, datetime('now'))
        """,
        (_GUARD_KEY,),
    )
    conn.execute(
        """
        UPDATE dim_sku_weight_write_guard
        SET allow_updates = 1,
            source = ?,
            expires_at = datetime('now', '+10 minutes'),
            updated_at = datetime('now')
        WHERE guard_key = ?
        """,
        (_GUARD_SOURCE, _GUARD_KEY),
    )
    return True


def _deactivate_weight_guard(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "dim_sku_weight_write_guard"):
        return
    conn.execute(
        """
        UPDATE dim_sku_weight_write_guard
        SET allow_updates = 0,
            source = NULL,
            expires_at = NULL,
            updated_at = datetime('now')
        WHERE guard_key = ?
        """,
        (_GUARD_KEY,),
    )


def sync_dim_sku_from_dim_sku_light(
    *,
    xlsx_path: Path,
    db_path: Path,
    sheet_name: str = DEFAULT_SHEET,
    apply: bool = False,
    update_base_cost: bool = False,
    weight_tol_kg: float = 1e-9,
    base_tol_cny: float = 1e-9,
) -> dict[str, Any]:
    if apply and os.environ.get("ENABLE_DIM_SKU_SYNC_WRITE") != "1":
        raise RuntimeError("ENABLE_DIM_SKU_SYNC_WRITE=1 is required with --apply")

    parsed, diagnostics = parse_dim_sku_light(
        xlsx_path,
        sheet_name=sheet_name,
    )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    guard_active = False
    try:
        if not _table_exists(conn, "dim_sku"):
            raise RuntimeError("dim_sku table not found")
        if apply:
            guard_active = _activate_weight_guard(conn)

        rows = conn.execute(
            """
            SELECT
                sku_key,
                base_cost_cny,
                weight_kg,
                COALESCE(active_flag, 1) AS active_flag
            FROM dim_sku
            """
        ).fetchall()
        db_by_sku = {str(row["sku_key"]): row for row in rows if row["sku_key"]}

        rows_compared = 0
        rows_missing_in_db = 0
        rows_would_update = 0
        rows_updated = 0
        weight_updates = 0
        base_updates = 0
        large_weight_shift_count = 0

        for sku_key, workbook_row in parsed.items():
            db_row = db_by_sku.get(sku_key)
            if db_row is None:
                rows_missing_in_db += 1
                continue
            if int(db_row["active_flag"] or 0) != 1:
                continue

            rows_compared += 1
            old_weight = float(db_row["weight_kg"] or 0.0)
            old_base = float(db_row["base_cost_cny"] or 0.0)
            new_weight = float(workbook_row["weight_kg"])
            new_base = float(workbook_row["base_cost_cny"])

            update_fields: list[tuple[str, float]] = []
            if abs(old_weight - new_weight) > float(weight_tol_kg):
                update_fields.append(("weight_kg", new_weight))
                weight_updates += 1
                if old_weight > 0 and abs(new_weight - old_weight) / old_weight > 0.20:
                    large_weight_shift_count += 1
            if update_base_cost and abs(old_base - new_base) > float(base_tol_cny):
                update_fields.append(("base_cost_cny", new_base))
                base_updates += 1

            if not update_fields:
                continue

            rows_would_update += 1
            if apply:
                set_clause = ", ".join(f"{col} = ?" for col, _ in update_fields)
                values = [val for _, val in update_fields] + [sku_key]
                conn.execute(
                    f"UPDATE dim_sku SET {set_clause} WHERE sku_key = ?",
                    values,
                )
                rows_updated += 1

        if apply:
            conn.commit()
    finally:
        if apply and guard_active:
            try:
                _deactivate_weight_guard(conn)
                conn.commit()
            except Exception:
                conn.rollback()
        conn.close()

    return {
        "apply": apply,
        "update_base_cost": update_base_cost,
        "source_xlsx": str(xlsx_path),
        "sheet_name": sheet_name,
        "rows_parsed": len(parsed),
        "rows_compared": rows_compared,
        "rows_missing_in_db": rows_missing_in_db,
        "rows_would_update": rows_would_update,
        "rows_updated": rows_updated,
        "weight_updates": weight_updates,
        "base_updates": base_updates,
        "large_weight_shift_count": large_weight_shift_count,
        "parser_diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync dim_sku from Dim sku light workbook")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Dim sku light workbook path")
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET, help="Workbook sheet name")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database path")
    parser.add_argument("--apply", action="store_true", help="Apply writes")
    parser.add_argument(
        "--update-base-cost",
        action="store_true",
        help="Also update base_cost_cny from workbook (default: reference-only, no base updates)",
    )
    args = parser.parse_args()

    try:
        result = sync_dim_sku_from_dim_sku_light(
            xlsx_path=args.xlsx,
            db_path=args.db,
            sheet_name=args.sheet,
            apply=args.apply,
            update_base_cost=args.update_base_cost,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    mode = "APPLY" if result["apply"] else "DRY-RUN"
    print(
        f"dim_sku light sync {mode}: parsed={result['rows_parsed']} compared={result['rows_compared']} "
        f"missing_in_db={result['rows_missing_in_db']} would_update={result['rows_would_update']}"
    )
    print(
        f"updates: weight={result['weight_updates']} base={result['base_updates']} "
        f"applied={result['rows_updated']} large_weight_shift={result['large_weight_shift_count']}"
    )
    diag = result["parser_diagnostics"]
    print(
        "parser:",
        f"header_row={diag['header_row_index']}",
        f"valid={diag['rows_valid']}",
        f"helper_filtered={diag['filtered_helper_rows']}",
        f"invalid_sku_filtered={diag['filtered_invalid_sku_rows']}",
        f"duplicates={diag['duplicate_sku_keys']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
