#!/usr/bin/env python3
"""
Import size-share anchors from an XLSX into dim_anchor.

- Updates only *_share columns.
- Leaves d_active, sigma, and *_D columns unchanged.
- Dry-run by default; apply requires ENABLE_PARAM_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "db" / "app.db"

REQUIRED_HEADER = "SKU_key"


def _normalize_header(name: str) -> str:
    return str(name or "").strip()


def load_rows(xlsx_path: Path) -> list[dict]:
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SystemExit("Empty workbook")

    headers = [_normalize_header(h) for h in rows[0]]
    if REQUIRED_HEADER not in headers:
        raise SystemExit(f"Missing required header: {REQUIRED_HEADER}")

    out = []
    for raw in rows[1:]:
        if not any(raw):
            continue
        record = {headers[i]: raw[i] for i in range(len(headers))}
        sku_key = str(record.get(REQUIRED_HEADER, "") or "").strip()
        if not sku_key:
            continue
        out.append(record)

    wb.close()
    return out


def get_share_columns(conn: sqlite3.Connection) -> list[str]:
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(dim_anchor)")]
    return [c for c in cols if c.endswith("_share")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Import size-share anchors into dim_anchor")
    parser.add_argument("--input", type=Path, required=True, help="Path to XLSX with size-share anchors")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to app.db")
    parser.add_argument("--apply", action="store_true", help="Apply changes (requires ENABLE_PARAM_WRITE=1)")
    args = parser.parse_args()

    if args.apply and os.environ.get("ENABLE_PARAM_WRITE") != "1":
        raise SystemExit("ENABLE_PARAM_WRITE=1 required for --apply")

    records = load_rows(args.input)
    if not records:
        raise SystemExit("No records found")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        share_cols = get_share_columns(conn)
        if not share_cols:
            raise SystemExit("dim_anchor has no *_share columns")

        updated = 0
        inserted = 0
        missing = []

        for record in records:
            sku_key = str(record.get(REQUIRED_HEADER, "") or "").strip()
            if not sku_key:
                continue

            share_values = {}
            for col in share_cols:
                if col in record:
                    try:
                        share_values[col] = float(record.get(col) or 0.0)
                    except (TypeError, ValueError):
                        share_values[col] = 0.0

            if not share_values:
                continue

            row = conn.execute(
                "SELECT sku_key FROM dim_anchor WHERE sku_key = ?",
                (sku_key,),
            ).fetchone()

            if row:
                if args.apply:
                    sets = ", ".join([f'\"{c}\" = ?' for c in share_values.keys()])
                    params = list(share_values.values()) + [datetime.now().isoformat(), sku_key]
                    conn.execute(
                        f"UPDATE dim_anchor SET {sets}, updated_at = ? WHERE sku_key = ?",
                        params,
                    )
                updated += 1
            else:
                # Insert with zeroed d_active/sigma if missing
                if args.apply:
                    cols = ["sku_key", "d_active", "sigma", *share_values.keys(), "updated_at"]
                    col_list = ", ".join([f'\"{c}\"' for c in cols])
                    placeholders = ",".join(["?"] * len(cols))
                    values = [sku_key, 0.0, 0.0, *share_values.values(), datetime.now().isoformat()]
                    conn.execute(
                        f"INSERT INTO dim_anchor ({col_list}) VALUES ({placeholders})",
                        values,
                    )
                inserted += 1

        if args.apply:
            conn.commit()

        print(f"Records in file: {len(records)}")
        print(f"Updated: {updated}")
        print(f"Inserted: {inserted}")
        if missing:
            print(f"Missing sku_keys: {len(missing)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
