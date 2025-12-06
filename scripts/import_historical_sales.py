#!/usr/bin/env python3
"""
Import Historical Sales: Parse Archive_sales → fact_sales with calculated economics.

This script:
1. Reads historical sales from Archive_sales sheet in Excel
2. Normalizes store codes (Universal → UNIVERSAL, etc.)
3. Validates SKUs exist in dim_sku (skips + logs missing)
4. Auto-creates dim_sku_size entries if needed
5. Calculates economics using core/calc/economics.py
6. Inserts to fact_sales (INSERT OR IGNORE - existing records win)

Idempotent: Safe to re-run. Duplicates are skipped.

Usage:
    python scripts/import_historical_sales.py excel_ui/SALES_KSP_CRM_GPT_15.9.25.xlsx
    python scripts/import_historical_sales.py --dry-run
    python scripts/import_historical_sales.py --limit 100 --verbose
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.db import get_db
from core.calc.economics import calc_line_values


# Store normalization mapping (Excel values → DB values)
STORE_NORMALIZE = {
    "Universal": "UNIVERSAL",
    "AcmeWear": "ACMEWEAR",
    "11KZ": "11KZ",
    "MELVIS": "MELVIS",
    "STORE-B": "STOREB",
}
DEFAULT_STORE = "UNIVERSAL"

# Warnings log file
WARNINGS_LOG = Path(__file__).parent.parent / "data" / "import_warnings.log"


def normalize_store_code(raw_store: str | None) -> str:
    """Normalize store name to database format."""
    if pd.isna(raw_store) or not raw_store:
        return DEFAULT_STORE
    return STORE_NORMALIZE.get(str(raw_store).strip(), DEFAULT_STORE)


def parse_date(value) -> str:
    """Convert datetime or string to ISO date format."""
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    # Try parsing string
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return None


def get_sku_data(conn) -> dict[str, dict]:
    """
    Load all SKU data from dim_sku.

    Returns dict mapping sku_key → {base_cost_cny, weight_kg, product_type}
    """
    cursor = conn.execute("""
        SELECT sku_key, base_cost_cny, weight_kg, product_type
        FROM dim_sku
        WHERE active_flag = 1
    """)
    return {
        row[0]: {
            "base_cost_cny": row[1] or 0,
            "weight_kg": row[2] or 0,
            "product_type": row[3] or "CL",
        }
        for row in cursor.fetchall()
    }


def get_existing_sku_sizes(conn) -> set[str]:
    """Get set of existing sku_id values in dim_sku_size."""
    cursor = conn.execute("SELECT sku_id FROM dim_sku_size")
    return {row[0] for row in cursor.fetchall()}


def create_sku_size(
    conn,
    sku_id: str,
    sku_key: str,
    my_size: str,
    dry_run: bool = False,
) -> bool:
    """
    Create dim_sku_size entry if it doesn't exist.

    Returns True if created, False if dry_run.
    """
    if dry_run:
        return False

    # Determine size_order for sorting
    size_order_map = {
        "S": 1, "M": 2, "L": 3, "XL": 4, "2XL": 5, "3XL": 6, "4XL": 7,
        "24": 10, "26": 11, "28": 12, "30": 13, "32": 14, "34": 15,
    }
    size_order = size_order_map.get(my_size, 99)

    conn.execute("""
        INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
        VALUES (?, ?, ?, ?)
    """, (sku_id, sku_key, my_size, size_order))

    return True


def log_warning(message: str, verbose: bool = True):
    """Log warning to file and optionally console."""
    # Ensure data directory exists
    WARNINGS_LOG.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"

    with open(WARNINGS_LOG, "a") as f:
        f.write(log_line)

    if verbose:
        print(f"  WARNING: {message}")


def parse_archive_sales(
    filepath: str,
    sheet_name: str = "Archive_sales",
    limit: int | None = None,
) -> list[dict]:
    """
    Parse Archive_sales sheet from Excel.

    Returns list of dicts with keys:
    - order_date, store_code, order_id, sku_key, sku_id, my_size
    - quantity, sell_price_kzt, product_type
    """
    df = pd.read_excel(filepath, sheet_name=sheet_name)

    if limit:
        df = df.head(limit)

    records = []
    for _, row in df.iterrows():
        # Parse date
        order_date = parse_date(row.get("Date"))
        if not order_date:
            continue

        # Get required fields
        order_id = row.get("OrderID")
        sku_key = row.get("SKU_key")
        my_size = row.get("MY_SIZE")
        quantity = row.get("Quantity")
        sell_price = row.get("Sell_price_kzt")

        # Skip rows with missing required fields
        if pd.isna(order_id) or pd.isna(sku_key) or pd.isna(my_size):
            continue
        if pd.isna(quantity) or pd.isna(sell_price):
            continue

        # Normalize values
        store_code = normalize_store_code(row.get("STORE_NAME"))
        sku_key = str(sku_key).strip()
        my_size = str(my_size).strip().upper()
        sku_id = f"{sku_key}_{my_size}"
        product_type = row.get("Product_Type", "CL")
        if pd.isna(product_type):
            product_type = "CL"

        records.append({
            "order_date": order_date,
            "store_code": store_code,
            "order_id": str(int(order_id)) if isinstance(order_id, float) else str(order_id),
            "sku_key": sku_key,
            "sku_id": sku_id,
            "my_size": my_size,
            "quantity": int(quantity),
            "sell_price_kzt": float(sell_price),
            "product_type": str(product_type).strip(),
        })

    return records


def import_historical_sales(
    filepath: str,
    sheet_name: str = "Archive_sales",
    dry_run: bool = False,
    verbose: bool = True,
    limit: int | None = None,
) -> dict:
    """
    Main import function.

    Returns dict with stats:
    - parsed_count, inserted_count, skipped_duplicates
    - skipped_missing_sku, created_sku_sizes, errors
    """
    stats = {
        "parsed_count": 0,
        "valid_count": 0,
        "inserted_count": 0,
        "skipped_duplicates": 0,
        "skipped_missing_sku": 0,
        "skipped_zero_cost": 0,
        "created_sku_sizes": 0,
        "errors": 0,
        "missing_skus": set(),
    }

    if verbose:
        print(f"Parsing {filepath}...")
        print(f"  Sheet: {sheet_name}")

    # Parse Excel
    records = parse_archive_sales(filepath, sheet_name, limit)
    stats["parsed_count"] = len(records)

    if verbose:
        print(f"  Parsed rows: {len(records)}")

    if not records:
        return stats

    with get_db() as conn:
        # Load SKU dimension data
        sku_data = get_sku_data(conn)
        existing_sizes = get_existing_sku_sizes(conn)

        if verbose:
            print(f"  Known SKUs in dim_sku: {len(sku_data)}")
            print(f"  Known sizes in dim_sku_size: {len(existing_sizes)}")

        # Get existing fact_sales count for comparison
        cursor = conn.execute("SELECT COUNT(*) FROM fact_sales")
        before_count = cursor.fetchone()[0]

        # Process each record
        insert_records = []

        for rec in records:
            sku_key = rec["sku_key"]
            sku_id = rec["sku_id"]

            # Check if SKU exists in dim_sku
            if sku_key not in sku_data:
                stats["skipped_missing_sku"] += 1
                stats["missing_skus"].add(sku_key)
                log_warning(f"Missing SKU: {sku_key} (order {rec['order_id']})", verbose=False)
                continue

            sku_info = sku_data[sku_key]

            # Check for zero cost/weight (would produce invalid COGS)
            if sku_info["base_cost_cny"] == 0 or sku_info["weight_kg"] == 0:
                stats["skipped_zero_cost"] += 1
                continue

            # Auto-create dim_sku_size if needed
            if sku_id not in existing_sizes:
                create_sku_size(conn, sku_id, sku_key, rec["my_size"], dry_run)
                existing_sizes.add(sku_id)
                stats["created_sku_sizes"] += 1

            # Calculate economics
            try:
                econ = calc_line_values(
                    sell_price_kzt=rec["sell_price_kzt"],
                    base_cost_cny=sku_info["base_cost_cny"],
                    weight_kg=sku_info["weight_kg"],
                    quantity=rec["quantity"],
                )
            except Exception as e:
                stats["errors"] += 1
                log_warning(f"Calc error for order {rec['order_id']}: {e}", verbose)
                continue

            # Build fact_sales record
            insert_records.append({
                "order_id": rec["order_id"],
                "store_code": rec["store_code"],
                "order_date": rec["order_date"],
                "sku_key": sku_key,
                "sku_id": sku_id,
                "quantity": rec["quantity"],
                "sell_price_kzt": rec["sell_price_kzt"],
                "product_type": sku_info["product_type"],
                "channel": "kaspi",
                "delivery_fee": econ["delivery_fee"],
                "net_rev_unit": econ["net_rev_unit"],
                "line_net_rev": econ["line_net_rev"],
                "cogs_unit": econ["cogs_unit"],
                "cogs_line": econ["cogs_line"],
                "profit_unit": econ["profit_unit"],
                "profit_line": econ["profit_line"],
            })

        stats["valid_count"] = len(insert_records)

        if verbose:
            print(f"\nValid records for import: {len(insert_records)}")
            if stats["skipped_missing_sku"] > 0:
                print(f"Skipped (missing SKU): {stats['skipped_missing_sku']}")
                print(f"  Unique missing SKUs: {len(stats['missing_skus'])}")
            if stats["skipped_zero_cost"] > 0:
                print(f"Skipped (zero cost/weight): {stats['skipped_zero_cost']}")

        # Insert to fact_sales
        if not dry_run and insert_records:
            if verbose:
                print("\nWriting to fact_sales...")

            sql = """
                INSERT OR IGNORE INTO fact_sales (
                    order_id, store_code, order_date, sku_key, sku_id,
                    quantity, sell_price_kzt, product_type, channel,
                    delivery_fee, net_rev_unit, line_net_rev,
                    cogs_unit, cogs_line, profit_unit, profit_line
                ) VALUES (
                    :order_id, :store_code, :order_date, :sku_key, :sku_id,
                    :quantity, :sell_price_kzt, :product_type, :channel,
                    :delivery_fee, :net_rev_unit, :line_net_rev,
                    :cogs_unit, :cogs_line, :profit_unit, :profit_line
                )
            """

            conn.executemany(sql, insert_records)
            conn.commit()

            # Calculate actual inserts vs duplicates
            cursor = conn.execute("SELECT COUNT(*) FROM fact_sales")
            after_count = cursor.fetchone()[0]

            stats["inserted_count"] = after_count - before_count
            stats["skipped_duplicates"] = len(insert_records) - stats["inserted_count"]
        else:
            if verbose:
                print("\nDRY RUN - no changes made")
            stats["inserted_count"] = 0
            stats["skipped_duplicates"] = len(insert_records)

        # Log missing SKUs to file
        if stats["missing_skus"]:
            log_warning(
                f"Import session missing SKUs: {sorted(stats['missing_skus'])}",
                verbose=False
            )

        # Show sample record
        if verbose and insert_records:
            sample = insert_records[0]
            print("\nSample record:")
            print(f"  Order: {sample['order_id']}")
            print(f"  Date: {sample['order_date']}")
            print(f"  SKU: {sample['sku_key']} / {sample['sku_id']}")
            print(f"  Store: {sample['store_code']}")
            print(f"  Price: {sample['sell_price_kzt']:,.0f} KZT")
            print(f"  COGS: {sample['cogs_unit']:,.2f} KZT")
            print(f"  Profit: {sample['profit_unit']:,.2f} KZT")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import historical sales from Archive_sales Excel sheet"
    )
    parser.add_argument(
        "filepath",
        nargs="?",
        default="excel_ui/SALES_KSP_CRM_GPT_15.9.25.xlsx",
        help="Path to Excel file (default: excel_ui/SALES_KSP_CRM_GPT_15.9.25.xlsx)",
    )
    parser.add_argument(
        "--sheet",
        default="Archive_sales",
        help="Sheet name to import (default: Archive_sales)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without making changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows to process",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Import Historical Sales: Archive_sales → fact_sales")
    print("=" * 60)

    # Verify file exists
    if not Path(args.filepath).exists():
        print(f"ERROR: File not found: {args.filepath}")
        return 1

    stats = import_historical_sales(
        filepath=args.filepath,
        sheet_name=args.sheet,
        dry_run=args.dry_run,
        verbose=not args.quiet,
        limit=args.limit,
    )

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Parsed rows: {stats['parsed_count']}")
    print(f"  Valid for import: {stats['valid_count']}")
    print(f"  Inserted: {stats['inserted_count']}")
    print(f"  Skipped (duplicates): {stats['skipped_duplicates']}")
    print(f"  Skipped (missing SKU): {stats['skipped_missing_sku']}")
    print(f"  Skipped (zero cost): {stats['skipped_zero_cost']}")
    print(f"  SKU sizes created: {stats['created_sku_sizes']}")
    print(f"  Errors: {stats['errors']}")
    print("=" * 60)

    if stats["missing_skus"]:
        print(f"\nMissing SKUs logged to: {WARNINGS_LOG}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
