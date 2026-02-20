#!/usr/bin/env python3
"""Export a Kaspi pricelist allowlist (active SKU_IDs) from the DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def export_allowlist(db_path: Path, output_path: Path) -> int:
    with get_db(db_path) as conn:
        if not _table_exists(conn, "dim_sku") or not _table_exists(conn, "dim_sku_size"):
            raise RuntimeError("Missing dim_sku or dim_sku_size tables")

        sku_cols = _table_columns(conn, "dim_sku")
        size_cols = _table_columns(conn, "dim_sku_size")

        select_active_sku = "d.active_flag" if "active_flag" in sku_cols else "1"
        select_active_size = "s.active_flag" if "active_flag" in size_cols else "1"

        rows = conn.execute(
            f"""
            SELECT DISTINCT
                s.sku_id as sku_id,
                {select_active_sku} as sku_active,
                {select_active_size} as size_active
            FROM dim_sku_size s
            JOIN dim_sku d ON d.sku_key = s.sku_key
            WHERE s.sku_id IS NOT NULL AND TRIM(s.sku_id) != ''
            """
        ).fetchall()

    active_skus = []
    for row in rows:
        if int(row["sku_active"]) == 0 or int(row["size_active"]) == 0:
            continue
        active_skus.append(str(row["sku_id"]).strip())

    active_skus = sorted(set(active_skus))
    if not active_skus:
        raise RuntimeError("No active SKU_IDs found for allowlist")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(active_skus) + "\n", encoding="utf-8")
    return len(active_skus)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export active SKU_ID allowlist for Kaspi pricelist"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("exports/kaspi_pricelist/allowlist_active.txt"),
    )
    args = parser.parse_args()

    count = export_allowlist(db_path=args.db, output_path=args.output)
    print(f"Wrote {count} SKU_IDs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
