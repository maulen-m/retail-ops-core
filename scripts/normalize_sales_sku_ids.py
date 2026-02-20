#!/usr/bin/env python3
"""
Normalize sku_id values with stray spaces across sales + ledger tables.

Targets sku_id values that don't match dim_sku_size but can be normalized.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_sku_key, normalize_size
from core.ingest.sales_ingest import _load_size_synonyms


def _tables_with_sku_id(conn) -> list[str]:
    tables = []
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        name = row[0]
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({name})").fetchall()]
        if "sku_id" in cols:
            tables.append(name)
    return sorted(tables)


def _find_bad_sku_ids(conn, tables: list[str]) -> list[str]:
    bad = set()
    for table in tables:
        rows = conn.execute(
            f"SELECT DISTINCT sku_id FROM {table} WHERE sku_id LIKE '% %'"
        ).fetchall()
        bad.update(row[0] for row in rows if row[0])
    return sorted(bad)


def _resolve_canonical(conn, sku_id: str, synonyms: dict[str, str]) -> tuple[str, str, str] | None:
    raw = str(sku_id).strip()
    if "_" not in raw:
        return None
    base, suffix = raw.rsplit("_", 1)
    size = normalize_size(suffix, synonyms=synonyms)
    key = normalize_sku_key(base)
    if not size or not key:
        return None
    canonical = f"{key}_{size}"
    return canonical, key, size


def _table_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _apply_update(conn, table: str, raw: str, canonical: str, key: str, size: str) -> int:
    cols = _table_columns(conn, table)
    if table == "dim_sku_size":
        # If canonical row exists, drop the bad row instead of updating into conflict.
        exists = conn.execute(
            "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
            (canonical,),
        ).fetchone()
        if exists:
            cursor = conn.execute("DELETE FROM dim_sku_size WHERE sku_id = ?", (raw,))
            return cursor.rowcount

    if table in {"fact_inventory_snapshot_size", "fact_sales_daily_size"}:
        # These aggregates will be rebuilt; drop bad rows to avoid unique conflicts.
        cursor = conn.execute(
            f"DELETE FROM {table} WHERE sku_id = ?",
            (raw,),
        )
        return cursor.rowcount

    set_clauses = ["sku_id = ?"]
    params = [canonical]
    if "sku_key" in cols:
        set_clauses.append("sku_key = ?")
        params.append(key)
    if "my_size" in cols:
        set_clauses.append("my_size = ?")
        params.append(size)
    params.append(raw)
    cursor = conn.execute(
        f"""
        UPDATE {table}
        SET {", ".join(set_clauses)}
        WHERE sku_id = ?
        """,
        params,
    )
    return cursor.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize sku_id values with stray spaces")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    args = parser.parse_args()

    with get_db(args.db) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        synonyms = _load_size_synonyms(conn)
        tables = _tables_with_sku_id(conn)
        bad_skus = _find_bad_sku_ids(conn, tables)
        if not bad_skus:
            print("No sku_id values with spaces found.")
            return 0

        total_updates = 0
        data_tables = [t for t in tables if t != "dim_sku_size"]
        for raw in bad_skus:
            resolved = _resolve_canonical(conn, raw, synonyms)
            if not resolved:
                print(f"SKIP: {raw} (unable to resolve)")
                continue
            canonical, key, size = resolved
            if canonical == raw:
                continue
            print(f"{raw} -> {canonical} ({key}, {size})")
            for table in data_tables:
                count = conn.execute(
                    f"SELECT COUNT(1) FROM {table} WHERE sku_id = ?",
                    (raw,),
                ).fetchone()[0]
                if not count:
                    continue
                if args.apply:
                    updated = _apply_update(conn, table, raw, canonical, key, size)
                    total_updates += updated
                else:
                    print(f"  {table}: {count} rows")

            # Update dim_sku_size last to avoid FK constraint conflicts
            if args.apply:
                updated = _apply_update(conn, "dim_sku_size", raw, canonical, key, size)
                total_updates += updated
            else:
                count = conn.execute(
                    "SELECT COUNT(1) FROM dim_sku_size WHERE sku_id = ?",
                    (raw,),
                ).fetchone()[0]
                if count:
                    print("  dim_sku_size: 1 row")

        if args.apply:
            conn.commit()
            print(f"Total rows updated: {total_updates}")
        else:
            conn.rollback()
            print("Dry-run complete.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
