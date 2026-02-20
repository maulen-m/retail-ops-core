#!/usr/bin/env python3
"""
Validate DB snapshot vs Snapshot_Z from Inventory_Core workbook.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_sku_key, normalize_size, normalize_sku_id


EXPORT_DIR = PROJECT_ROOT / "exports"
CANARY_SKUS = {"CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE51_WHITE"}


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
    parser = argparse.ArgumentParser(description="Validate snapshot vs Snapshot_Z")
    parser.add_argument(
        "--workbook",
        default=str(PROJECT_ROOT / "excel" / "Inventory_Core_V18.1_V2.xlsx"),
        help="Path to Inventory_Core workbook",
    )
    parser.add_argument("--snapshot-date", help="Snapshot date YYYY-MM-DD (default: Snapshot_Z_date mode)")
    parser.add_argument("--tolerance", type=int, default=1, help="Max abs diff per size (default 1)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument(
        "--report",
        default=str(EXPORT_DIR / "validate_snapshot_vs_snapshot_z_report.csv"),
        help="Output report path",
    )
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser()
    if not workbook_path.exists():
        raise SystemExit(f"Workbook not found: {workbook_path}")

    df = pd.read_excel(
        workbook_path,
        sheet_name="DIM_SKU_ID",
        dtype={
            "SKU_ID": "string",
            "SKU_key": "string",
            "MY_SIZE": "string",
        },
    )

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

    df["sku_key"] = df["sku_key"].apply(lambda v: normalize_sku_key(str(v).strip()) if pd.notna(v) else None)
    df["my_size"] = df["my_size"].apply(lambda v: normalize_size(v, "CL") if pd.notna(v) else None)
    df["sku_id"] = df.apply(lambda r: normalize_sku_id(r["sku_id"], r["sku_key"]), axis=1)
    df["current_stock"] = pd.to_numeric(df["current_stock"], errors="coerce").fillna(0).astype(int)

    df = df[df["snapshot_date"] == snapshot_date]
    df = df[df["sku_key"].isin(CANARY_SKUS)]
    df = df.dropna(subset=["sku_key", "my_size"])

    snapshot_z = (
        df.groupby(["sku_key", "my_size"], as_index=False)["current_stock"].sum()
        .rename(columns={"current_stock": "snapshot_z"})
    )

    with get_db(args.db) as conn:
        rows = conn.execute(
            """
            SELECT sku_key, my_size, SUM(current_stock) as current_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
              AND sku_key IN ('CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE51_WHITE')
            GROUP BY sku_key, my_size
            """,
            (snapshot_date,),
        ).fetchall()

    db_rows = { (r["sku_key"], r["my_size"]): int(r["current_stock"] or 0) for r in rows }

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)

    failures = 0
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sku_key", "my_size", "snapshot_z", "db_stock", "diff"])
        for _, row in snapshot_z.iterrows():
            key = (row["sku_key"], row["my_size"])
            db_stock = db_rows.get(key, 0)
            diff = int(db_stock) - int(row["snapshot_z"])
            writer.writerow([row["sku_key"], row["my_size"], int(row["snapshot_z"]), db_stock, diff])
            if abs(diff) > args.tolerance:
                failures += 1

    if failures:
        print(f"FAIL: {failures} size rows exceed tolerance (report: {report_path})")
        return 1

    print(f"PASS: Snapshot_Z within tolerance (report: {report_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
