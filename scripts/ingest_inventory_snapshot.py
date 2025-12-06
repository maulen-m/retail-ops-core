#!/usr/bin/env python3
"""
Ingest Inventory Snapshot: Import current stock levels from Excel into DB.

This script:
1. Parses inventory Excel file with columns: SKU_ID, SKU_key, MY_SIZE, Current_stock
2. Inserts/updates records in fact_inventory_snapshot_size table
3. Aggregates to fact_inventory_snapshot (style-level) for metrics calculation

Usage:
    python scripts/ingest_inventory_snapshot.py excel/Current_stock_*.xlsx
    python scripts/ingest_inventory_snapshot.py excel/Current_stock_*.xlsx --date 2025-12-06
    python scripts/ingest_inventory_snapshot.py excel/Current_stock_*.xlsx --dry-run
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db


def parse_inventory_excel(filepath: str) -> list[dict]:
    """
    Parse inventory Excel file.

    Expected columns: SKU_ID, SKU_key, MY_SIZE, Current_stock

    Returns list of dicts with keys: sku_id, sku_key, my_size, current_stock
    """
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb["Sheet1"]

    # Get headers from first row
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]

    # Map expected columns
    col_map = {}
    expected = {"SKU_ID": "sku_id", "SKU_key": "sku_key", "MY_SIZE": "my_size", "Current_stock": "current_stock"}

    for idx, header in enumerate(headers):
        if header in expected:
            col_map[idx] = expected[header]

    if len(col_map) < 4:
        missing = set(expected.keys()) - {headers[i] for i in col_map}
        raise ValueError(f"Missing columns in Excel: {missing}")

    records = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:  # Skip empty rows
            continue

        record = {}
        for idx, key in col_map.items():
            value = row[idx]
            if key == "current_stock":
                # Handle None, empty, or non-numeric values
                record[key] = int(value) if value and str(value).strip() else 0
            else:
                record[key] = str(value).strip() if value else ""
        records.append(record)

    wb.close()
    return records


def create_tables_if_needed(conn):
    """Create snapshot tables if they don't exist."""
    # Size-level snapshot (no FK constraints - may have SKUs not in dim tables)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(snapshot_date, sku_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inv_snapshot_size_date
        ON fact_inventory_snapshot_size(snapshot_date)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inv_snapshot_size_sku
        ON fact_inventory_snapshot_size(sku_key)
    """)
    conn.commit()


def save_snapshot(
    conn,
    records: list[dict],
    snapshot_date: str,
    dry_run: bool = False,
) -> dict:
    """
    Save inventory snapshot to database.

    Returns dict with stats: size_records, style_records, total_units
    """
    if dry_run:
        # Just count and return
        style_totals = {}
        total_units = 0
        for r in records:
            sku_key = r["sku_key"]
            stock = r["current_stock"]
            style_totals[sku_key] = style_totals.get(sku_key, 0) + stock
            total_units += stock
        return {
            "size_records": len(records),
            "style_records": len(style_totals),
            "total_units": total_units,
        }

    create_tables_if_needed(conn)

    # Delete existing snapshot for this date (idempotent)
    conn.execute(
        "DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = ?",
        (snapshot_date,)
    )

    # Insert size-level records
    insert_sql = """
        INSERT INTO fact_inventory_snapshot_size
        (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
        VALUES (?, ?, ?, ?, ?, 0)
    """
    for r in records:
        conn.execute(insert_sql, (
            snapshot_date,
            r["sku_id"],
            r["sku_key"],
            r["my_size"],
            r["current_stock"],
        ))

    conn.commit()

    # Aggregate to style-level for stats
    style_totals = {}
    for r in records:
        sku_key = r["sku_key"]
        stock = r["current_stock"]
        style_totals[sku_key] = style_totals.get(sku_key, 0) + stock

    return {
        "size_records": len(records),
        "style_records": len(style_totals),
        "total_units": sum(style_totals.values()),
    }


def ingest_inventory(
    filepath: str,
    snapshot_date: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Main function to ingest inventory snapshot.

    Args:
        filepath: Path to Excel file
        snapshot_date: ISO date string (default: today)
        dry_run: If True, parse but don't save
        verbose: Print progress

    Returns:
        Dict with stats
    """
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

    if verbose:
        print(f"Parsing {filepath}...")

    records = parse_inventory_excel(filepath)

    if verbose:
        print(f"  Found {len(records)} size-level records")
        # Show sample
        with_stock = [r for r in records if r["current_stock"] > 0]
        print(f"  Records with stock > 0: {len(with_stock)}")
        if with_stock:
            sample = with_stock[0]
            print(f"  Sample: {sample['sku_id']} = {sample['current_stock']} units")

    with get_db() as conn:
        stats = save_snapshot(conn, records, snapshot_date, dry_run)

    if verbose:
        action = "Would save" if dry_run else "Saved"
        print(f"\n{action}:")
        print(f"  Size-level records: {stats['size_records']}")
        print(f"  Style-level records: {stats['style_records']}")
        print(f"  Total units: {stats['total_units']}")

    stats["snapshot_date"] = snapshot_date
    stats["filepath"] = filepath
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Ingest inventory snapshot from Excel"
    )
    parser.add_argument(
        "filepath",
        type=str,
        help="Path to inventory Excel file",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Snapshot date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse but don't save",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Ingest Inventory Snapshot")
    print("=" * 60)

    result = ingest_inventory(
        filepath=args.filepath,
        snapshot_date=args.date,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 60)
    print(f"Snapshot date: {result['snapshot_date']}")
    if args.dry_run:
        print("DRY RUN - no changes made")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
