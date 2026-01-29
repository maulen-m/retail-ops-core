#!/usr/bin/env python3
"""
Seed the local dev DB so required gates pass end-to-end.

This is a convenience helper for setting up db/app.db with:
  - migrations (011/012/013_ledger)
  - dim_store seeds
  - fact_sales rebuild + daily aggregates (from CRM archive)
  - inventory snapshot seed for 2025-12-06 (tests expect this)
  - zeroed snapshot rows for yesterday (dashboard readiness)
  - demand override seeds
  - SKU metrics
  - a minimal alert log row for tests
  - normalization of empty MY_SIZE rows

Usage:
  python3 scripts/seed_dev_db.py --confirm
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import sqlite3
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"

SNAPSHOT_XLSX = PROJECT_ROOT / "excel" / "Current_stock_6.12.2025_day_start_before_daily_sales_ship.xlsx"
CRM_ARCHIVE_XLSX = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_GPT_15.9.25.xlsx"

STORES = [
    ("UNIVERSAL", "kaspi", "KZ", 1),
    ("ACMEWEAR", "kaspi", "KZ", 1),
    ("11KZ", "kaspi", "KZ", 1),
    ("MELVIS", "kaspi", "KZ", 1),
    ("STOREB", "kaspi", "KZ", 1),
]


def run_cmd(args: list[str]) -> None:
    subprocess.run(args, check=True)


def parse_snapshot_rows(xlsx_path: Path) -> list[tuple]:
    df = pd.read_excel(xlsx_path, sheet_name=0)
    col_map: dict[str, str] = {}
    for col in df.columns:
        key = col.lower().replace(" ", "_").replace("-", "_")
        if key in ["sku_id", "skuid"]:
            col_map[col] = "sku_id"
        elif key in ["sku_key", "skukey"]:
            col_map[col] = "sku_key"
        elif key in ["my_size", "mysize", "size"]:
            if "my_size" not in col_map.values():
                col_map[col] = "my_size"
        elif key in ["current_stock", "currentstock", "stock", "qty"]:
            col_map[col] = "current_stock"

    df = df.rename(columns=col_map)
    required = ["sku_id", "sku_key", "my_size", "current_stock"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in snapshot file: {missing}")

    rows: list[tuple] = []
    for _, row in df.iterrows():
        sku_id = str(row["sku_id"]).strip()
        if not sku_id or sku_id.lower() == "nan":
            continue
        sku_key = str(row["sku_key"]).strip()
        my_size = str(row["my_size"]).strip()
        stock = row["current_stock"]
        if pd.isna(stock):
            stock = 0
        else:
            stock = int(stock)
        rows.append(("2025-12-06", sku_id, sku_key, my_size, stock, 0))

    return rows


def seed_dim_store(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO dim_store (store_code, channel, region, active_flag)
        VALUES (?, ?, ?, ?)
        """,
        STORES,
    )


def normalize_empty_sizes(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT sku_id, sku_key
        FROM dim_sku_size
        WHERE my_size IS NULL OR my_size = ''
        """
    ).fetchall()
    for sku_id, sku_key in rows:
        if not sku_key:
            continue
        new_size = "UNKNOWN"
        new_id = f"{sku_key}_{new_size}"
        # Skip if target already exists
        existing = conn.execute(
            "SELECT 1 FROM dim_sku_size WHERE sku_id = ? LIMIT 1",
            (new_id,),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "UPDATE dim_sku_size SET sku_id = ?, my_size = ? WHERE sku_id = ?",
            (new_id, new_size, sku_id),
        )
        conn.execute(
            "UPDATE fact_sales SET sku_id = ?, my_size = ? WHERE sku_id = ?",
            (new_id, new_size, sku_id),
        )
        conn.execute(
            "UPDATE fact_sales_daily_size SET sku_id = ?, my_size = ? WHERE sku_id = ?",
            (new_id, new_size, sku_id),
        )
        conn.execute(
            "UPDATE fact_inventory_snapshot_size SET sku_id = ?, my_size = ? WHERE sku_id = ?",
            (new_id, new_size, sku_id),
        )


def seed_snapshot_2025_12_06(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.execute(
        "DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = '2025-12-06'"
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO fact_inventory_snapshot_size
        (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def seed_yesterday_snapshot(conn: sqlite3.Connection, snap_date: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO fact_inventory_snapshot_size
        (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
        SELECT ?, d.sku_id, d.sku_key, d.my_size, 0, 0
        FROM dim_sku_size d
        WHERE d.sku_id NOT IN (
            SELECT sku_id FROM fact_inventory_snapshot_size WHERE snapshot_date = ?
        )
        """,
        (snap_date, snap_date),
    )


def seed_alert_log(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        """
        SELECT COUNT(*) FROM fact_alert_log
        WHERE alert_date = '2025-12-06'
        """
    ).fetchone()[0]
    if existing:
        return
    conn.execute(
        """
        INSERT INTO fact_alert_log
        (alert_date, alert_time, alert_type, channel, store_code, sku_key, message, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2025-12-06",
            "2025-12-06 00:00:00",
            "REORDER",
            "telegram",
            "UNIVERSAL",
            "CL_OC_MEN_LINE52_BLACK",
            "Seed alert for tests",
            "SENT",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed dev DB for local gates")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Apply DB writes (required)",
    )
    args = parser.parse_args()

    if not args.confirm:
        print("This script writes to db/app.db. Re-run with --confirm.")
        return 2

    if not SNAPSHOT_XLSX.exists():
        print(f"Missing snapshot file: {SNAPSHOT_XLSX}")
        return 1
    if not CRM_ARCHIVE_XLSX.exists():
        print(f"Missing CRM archive file: {CRM_ARCHIVE_XLSX}")
        return 1

    # Ensure schema + migrations
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "migrate_011.py")])
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "migrate_012.py")])
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "migrate_013_ledger.py")])

    # Rebuild fact_sales (destructive but idempotent for this file)
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "rebuild_fact_sales.py")])

    # Bootstrap stock ledger from snapshot
    run_cmd([
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "bootstrap_ledger.py"),
        str(SNAPSHOT_XLSX),
        "--date",
        "2025-12-06",
    ])

    with sqlite3.connect(DB_PATH) as conn:
        seed_dim_store(conn)

        # Normalize empty sizes before snapshot seeding
        normalize_empty_sizes(conn)

        # Seed fact_inventory_snapshot_size for 2025-12-06
        rows = parse_snapshot_rows(SNAPSHOT_XLSX)
        seed_snapshot_2025_12_06(conn, rows)

        # Ensure yesterday snapshot rows exist
        snap_date = (date.today() - timedelta(days=1)).isoformat()
        seed_yesterday_snapshot(conn, snap_date)

        # Seed alert log row
        seed_alert_log(conn)

        conn.commit()

    # Demand overrides + SKU metrics
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "upsert_demand_overrides.py"), "--seed-defaults"])
    run_cmd([sys.executable, str(PROJECT_ROOT / "scripts" / "run_sku_metrics.py"), "--days", "30"])

    print("✅ Dev DB seeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
