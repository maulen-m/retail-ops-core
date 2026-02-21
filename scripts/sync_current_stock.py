#!/usr/bin/env python3
"""Sync inventory snapshot using single-truth stock + inbound anchors.

Default mode is dry-run. DB writes require:
1) ENABLE_STOCK_SNAPSHOT_WRITE=1
2) --apply
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_STOCK_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "STOCK_SNAPSHOT_LATEST.xlsx"
DEFAULT_INBOUND_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
DEFAULT_STOCK_SHEET = "Inventory_snapshots"
DEFAULT_INBOUND_SHEET = "Inbounds_sheet"


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str) and not value.strip():
        return 0
    return int(float(value))


def load_stock_snapshot_rows(excel_path: Path, sheet_name: str = DEFAULT_STOCK_SHEET) -> list[dict]:
    """Load normalized rows from stock snapshot workbook."""
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    required = {"SKU_key", "MY_SIZE", "Snapshot_date", "Stock_snapshot"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Stock snapshot missing required columns: {missing}")

    rows: list[dict] = []
    for _, row in df.iterrows():
        sku_key = _normalize_text(row.get("SKU_key"))
        my_size = _normalize_text(row.get("MY_SIZE"))
        if not sku_key or not my_size:
            continue
        rows.append(
            {
                "sku_key": sku_key,
                "my_size": my_size,
                "snapshot_date": pd.to_datetime(row.get("Snapshot_date")).date().isoformat(),
                "current_stock": _to_int(row.get("Stock_snapshot")),
                "snapshot_inbound_transit": _to_int(row.get("Inbound_transit", 0)),
            }
        )

    if not rows:
        raise ValueError("Stock snapshot has no valid rows after normalization.")
    snapshot_dates = {row["snapshot_date"] for row in rows}
    if len(snapshot_dates) != 1:
        raise ValueError(f"Expected single Snapshot_date in stock snapshot, got: {sorted(snapshot_dates)}")
    return rows


def load_inbound_transit_map(inbound_path: Path, sheet_name: str = DEFAULT_INBOUND_SHEET) -> dict[tuple[str, str], int]:
    """Build inbound transit qty map from inbound workbook."""
    df = pd.read_excel(inbound_path, sheet_name=sheet_name)
    required = {"SKU Key", "Size", "Status", "Actual_qty", "Order Qty_Approved"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Inbound workbook missing required columns: {missing}")

    inbound_map: dict[tuple[str, str], int] = {}
    for _, row in df.iterrows():
        status = _normalize_text(row.get("Status")).lower()
        if status != "transit":
            continue
        sku_key = _normalize_text(row.get("SKU Key"))
        my_size = _normalize_text(row.get("Size"))
        if not sku_key or not my_size:
            continue
        qty_raw = row.get("Actual_qty")
        qty = _to_int(qty_raw) if pd.notna(qty_raw) else _to_int(row.get("Order Qty_Approved"))
        key = (sku_key, my_size)
        inbound_map[key] = inbound_map.get(key, 0) + max(0, qty)
    return inbound_map


def merge_stock_and_inbound_rows(
    stock_rows: list[dict], inbound_map: dict[tuple[str, str], int]
) -> list[dict]:
    """Use Stock_snapshot for current stock and inbound workbook for inbound transit."""
    snapshot_date = stock_rows[0]["snapshot_date"]
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for row in stock_rows:
        key = (row["sku_key"], row["my_size"])
        seen.add(key)
        merged.append(
            {
                "snapshot_date": snapshot_date,
                "sku_id": f"{row['sku_key']}_{row['my_size']}",
                "sku_key": row["sku_key"],
                "my_size": row["my_size"],
                "current_stock": max(0, int(row["current_stock"])),
                "inbound_stock": max(0, int(inbound_map.get(key, 0))),
            }
        )

    for (sku_key, my_size), qty in sorted(inbound_map.items()):
        key = (sku_key, my_size)
        if key in seen:
            continue
        merged.append(
            {
                "snapshot_date": snapshot_date,
                "sku_id": f"{sku_key}_{my_size}",
                "sku_key": sku_key,
                "my_size": my_size,
                "current_stock": 0,
                "inbound_stock": max(0, int(qty)),
            }
        )
    return merged


def sync_stock_from_excel(
    *,
    excel_path: str,
    inbound_path: str,
    db_path: str = str(DEFAULT_DB_PATH),
    apply: bool = False,
) -> dict[str, Any]:
    """Sync stock snapshot rows to fact_inventory_snapshot_size."""
    stock_rows = load_stock_snapshot_rows(Path(excel_path))
    inbound_map = load_inbound_transit_map(Path(inbound_path))
    merged_rows = merge_stock_and_inbound_rows(stock_rows, inbound_map)

    snapshot_date = merged_rows[0]["snapshot_date"]
    summary = {
        "snapshot_date": snapshot_date,
        "rows": len(merged_rows),
        "total_current_stock": int(sum(row["current_stock"] for row in merged_rows)),
        "total_inbound_stock": int(sum(row["inbound_stock"] for row in merged_rows)),
        "apply": bool(apply),
    }

    if not apply:
        return summary

    if os.environ.get("ENABLE_STOCK_SNAPSHOT_WRITE") != "1":
        raise RuntimeError("ENABLE_STOCK_SNAPSHOT_WRITE=1 is required with --apply")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = ?", (snapshot_date,))
        conn.executemany(
            """
            INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
            VALUES (:snapshot_date, :sku_id, :sku_key, :my_size, :current_stock, :inbound_stock)
            """,
            merged_rows,
        )
        conn.commit()
    finally:
        conn.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync stock snapshot (Stock_snapshot column) + inbound transit from inbound workbook."
    )
    parser.add_argument("--excel", default=str(DEFAULT_STOCK_ANCHOR), help="Stock snapshot workbook path")
    parser.add_argument("--inbound", default=str(DEFAULT_INBOUND_ANCHOR), help="Inbound calendar workbook path")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Target sqlite db path")
    parser.add_argument("--apply", action="store_true", help="Apply DB writes (requires env gate)")
    args = parser.parse_args()

    summary = sync_stock_from_excel(
        excel_path=args.excel,
        inbound_path=args.inbound,
        db_path=args.db,
        apply=args.apply,
    )
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode} stock sync summary")
    print(f"snapshot_date: {summary['snapshot_date']}")
    print(f"rows: {summary['rows']}")
    print(f"total_current_stock: {summary['total_current_stock']}")
    print(f"total_inbound_stock: {summary['total_inbound_stock']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
