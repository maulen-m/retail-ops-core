#!/usr/bin/env python3
"""
Import Snapshot_Z values from Inventory_Core workbook into fact_inventory_snapshot_size.

Uses DIM_SKU_ID sheet columns:
  - SKU_ID, SKU_key, MY_SIZE
  - Snapshot_Z_date
  - Snapshot_Z

Default behavior clamps negative Snapshot_Z to 0.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import infer_size_from_sku_id


def _parse_date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    try:
        return pd.to_datetime(value, errors="coerce").date().isoformat()  # type: ignore[union-attr]
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Snapshot_Z stock into fact_inventory_snapshot_size")
    parser.add_argument(
        "--workbook",
        required=True,
        help="Path to Inventory_Core workbook (xlsx)",
    )
    parser.add_argument(
        "--snapshot-date",
        help="Override snapshot date (YYYY-MM-DD). Default: Snapshot_Z_date mode.",
    )
    parser.add_argument(
        "--allow-negative",
        action="store_true",
        help="Allow negative Snapshot_Z values (default clamps to 0)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path",
    )
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser()
    if not workbook_path.exists():
        raise SystemExit(f"Workbook not found: {workbook_path}")

    print(f"Reading DIM_SKU_ID from {workbook_path} ...")
    df = pd.read_excel(workbook_path, sheet_name="DIM_SKU_ID")

    required_cols = {"SKU_ID", "SKU_key", "MY_SIZE", "Snapshot_Z_date", "Snapshot_Z"}
    missing = required_cols.difference(set(df.columns))
    if missing:
        raise SystemExit(f"DIM_SKU_ID missing columns: {sorted(missing)}")

    df = df.rename(columns={
        "SKU_ID": "sku_id",
        "SKU_key": "sku_key",
        "MY_SIZE": "my_size",
        "Snapshot_Z_date": "snapshot_date",
        "Snapshot_Z": "current_stock",
    })

    df["snapshot_date"] = df["snapshot_date"].apply(_parse_date)

    if args.snapshot_date:
        snapshot_date = args.snapshot_date
        df["snapshot_date"] = snapshot_date
    else:
        snapshot_date = df["snapshot_date"].mode().iloc[0] if len(df) > 0 else None
        if not snapshot_date:
            raise SystemExit("Snapshot_Z_date missing or empty.")

    df["my_size"] = df["my_size"].where(df["my_size"].notna(), None)
    df["my_size"] = df["my_size"].apply(lambda value: str(value).strip() if value is not None else None)
    df.loc[df["my_size"] == "", "my_size"] = None

    missing_size_mask = df["my_size"].isna()
    if missing_size_mask.any():
        df.loc[missing_size_mask, "my_size"] = df.loc[missing_size_mask, "sku_id"].apply(
            infer_size_from_sku_id
        )

    df["current_stock"] = pd.to_numeric(df["current_stock"], errors="coerce").fillna(0).astype(int)
    if not args.allow_negative:
        df["current_stock"] = df["current_stock"].clip(lower=0)

    df["inbound_stock"] = 0

    cols = ["snapshot_date", "sku_id", "sku_key", "my_size", "current_stock", "inbound_stock"]
    df = df[cols].dropna(subset=["sku_id", "sku_key", "my_size"])

    with get_db(args.db) as conn:
        print(f"Clearing existing snapshot rows for {snapshot_date} ...")
        conn.execute(
            "DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = ?",
            (snapshot_date,),
        )
        df.to_sql("fact_inventory_snapshot_size", conn, if_exists="append", index=False)

    print(f"Inserted {len(df)} snapshot rows for {snapshot_date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
