#!/usr/bin/env python3
"""
Sync KSP_dlv_fee sheet into dim_ksp_dlv_fee table.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path
from core.db import get_db

DEFAULT_WORKBOOK = data_path("excel", "Inventory_Core_V18.1_V2.xlsx")
DEFAULT_SHEET = "KSP_dlv_fee"


def load_fee_table(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    df = df.rename(columns={
        "Order_Value_Min": "order_value_min",
        "Order_Value_Max": "order_value_max",
        "Weight_Min_kg": "weight_min_kg",
        "Weight_Max_kg": "weight_max_kg",
        "Fee_City": "fee_city",
        "Fee_Kazakhstan": "fee_kazakhstan",
        "Fee_Express": "fee_express",
        "Fee_blend": "fee_blend",
    })
    required = [
        "order_value_min",
        "order_value_max",
        "weight_min_kg",
        "weight_max_kg",
        "fee_blend",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in KSP_dlv_fee: {missing}")
    df = df[required + ["fee_city", "fee_kazakhstan", "fee_express"]].copy()
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync KSP delivery fee table")
    parser.add_argument("--file", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--db", type=Path, default=data_path("db", "app.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"Workbook not found: {args.file}")

    df = load_fee_table(args.file, args.sheet)
    if args.dry_run:
        print(df.head())
        print(f"Rows: {len(df)}")
        return

    with get_db(args.db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dim_ksp_dlv_fee (
                order_value_min REAL NOT NULL,
                order_value_max REAL NOT NULL,
                weight_min_kg REAL NOT NULL,
                weight_max_kg REAL NOT NULL,
                fee_city REAL,
                fee_kazakhstan REAL,
                fee_express REAL,
                fee_blend REAL NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            DELETE FROM dim_ksp_dlv_fee;
            """
        )
        df.to_sql("dim_ksp_dlv_fee", conn, if_exists="append", index=False)
        conn.commit()

    print(f"✅ dim_ksp_dlv_fee updated: {len(df)} rows")


if __name__ == "__main__":
    main()
