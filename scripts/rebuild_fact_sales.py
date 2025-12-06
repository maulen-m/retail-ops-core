#!/usr/bin/env python3
"""
Phase 6.5: Rebuild fact_sales from Archive_sales with correct grain.

Problem: fact_sales had ~16,212 records due to:
- Double imports (ActiveOrders + Archive overlap)
- Missing aggregation (unit-level rows not collapsed)
- Wrong composite key (order_id, sku_id) instead of (order_id, kaspi_offer_name, sku_id)

Solution: Clean import from single source of truth.
Grain: (order_id, kaspi_offer_name, sku_id, store_code)

Usage:
    python3 scripts/rebuild_fact_sales.py --dry-run  # Preview
    python3 scripts/rebuild_fact_sales.py            # Execute rebuild
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.calc.economics import calc_line_values

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXCEL_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_GPT_15.9.25.xlsx"
LOG_DIR = PROJECT_ROOT / "logs"

# Store normalization mapping
STORE_NORMALIZE = {
    "Universal": "UNIVERSAL",
    "AcmeWear": "ACMEWEAR",
    "11KZ": "11KZ",
    "MELVIS": "MELVIS",
    "STORE-B": "STOREB",
}
DEFAULT_STORE = "UNIVERSAL"


def normalize_store_code(raw_store: str | None) -> str:
    """Normalize store name to database format."""
    if pd.isna(raw_store) or not raw_store:
        return DEFAULT_STORE
    return STORE_NORMALIZE.get(str(raw_store).strip(), DEFAULT_STORE)


def parse_date(value) -> str | None:
    """Convert datetime or string to ISO date format."""
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return None


def load_excel_data(excel_path: Path) -> pd.DataFrame:
    """Load and validate Archive_sales sheet."""
    print(f"Loading {excel_path}...")
    df = pd.read_excel(excel_path, sheet_name="Archive_sales")

    # Required columns
    required = ["Date", "OrderID", "KASPI_OFFER_NAME", "SKU_key", "MY_SIZE",
                "Quantity", "Sell_price_kzt"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    print(f"  Raw rows: {len(df)}")
    return df


def get_sku_data(conn: sqlite3.Connection) -> dict[str, dict]:
    """Load SKU data from dim_sku."""
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


def get_existing_sku_sizes(conn: sqlite3.Connection) -> set[str]:
    """Get set of existing sku_id values in dim_sku_size."""
    cursor = conn.execute("SELECT sku_id FROM dim_sku_size")
    return {row[0] for row in cursor.fetchall()}


def create_sku_size(conn: sqlite3.Connection, sku_id: str, sku_key: str, my_size: str):
    """Create dim_sku_size entry if needed."""
    size_order_map = {
        "S": 1, "M": 2, "L": 3, "XL": 4, "2XL": 5, "3XL": 6, "4XL": 7,
        "24": 10, "26": 11, "28": 12, "30": 13, "32": 14, "34": 15,
    }
    size_order = size_order_map.get(my_size, 99)

    conn.execute("""
        INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
        VALUES (?, ?, ?, ?)
    """, (sku_id, sku_key, my_size, size_order))


def clean_and_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean data and aggregate to correct grain.
    Grain: (order_id, kaspi_offer_name, sku_id, store_code)
    """
    # Parse dates
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    invalid_dates = df["Date"].isna().sum()
    if invalid_dates > 0:
        print(f"  Warning: Dropping {invalid_dates} rows with invalid dates")
        df = df.dropna(subset=["Date"])

    # Normalize store codes
    df["store_code"] = df["STORE_NAME"].apply(normalize_store_code)

    # Ensure Quantity is numeric
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(1).astype(int)

    # Ensure Sell_price_kzt is numeric
    df["Sell_price_kzt"] = pd.to_numeric(df["Sell_price_kzt"], errors="coerce").fillna(0)

    # Normalize MY_SIZE to uppercase
    df["MY_SIZE"] = df["MY_SIZE"].astype(str).str.strip().str.upper()

    # Build sku_id from sku_key + my_size
    df["sku_id"] = df["SKU_key"] + "_" + df["MY_SIZE"]

    # Product type from column or extract from SKU_key
    if "Product_Type" in df.columns:
        df["Product_Type"] = df["Product_Type"].fillna("CL")
    else:
        df["Product_Type"] = df["SKU_key"].str.split("_").str[0].fillna("CL")

    # Drop rows with missing critical fields
    df = df.dropna(subset=["OrderID", "SKU_key", "KASPI_OFFER_NAME"])

    # Aggregate to correct grain
    # Group by (order_id, kaspi_offer_name, sku_id, store_code)
    # Sum Quantity, take first of everything else
    agg_df = df.groupby(
        ["OrderID", "KASPI_OFFER_NAME", "sku_id", "store_code"],
        as_index=False,
    ).agg({
        "Date": "first",
        "SKU_key": "first",
        "MY_SIZE": "first",
        "Quantity": "sum",
        "Sell_price_kzt": "first",
        "Product_Type": "first",
    })

    print(f"  After aggregation: {len(agg_df)} order lines")
    print(f"  Total units: {agg_df['Quantity'].sum():,}")

    return agg_df


def process_records(df: pd.DataFrame, conn: sqlite3.Connection, verbose: bool = True) -> list[dict]:
    """
    Process aggregated records and calculate economics.

    Returns list of dicts ready for insertion.
    """
    sku_data = get_sku_data(conn)
    existing_sizes = get_existing_sku_sizes(conn)

    if verbose:
        print(f"  Known SKUs in dim_sku: {len(sku_data)}")
        print(f"  Known sizes in dim_sku_size: {len(existing_sizes)}")

    records = []
    missing_skus = set()
    zero_cost_skus = set()
    sizes_created = 0

    for _, row in df.iterrows():
        sku_key = str(row["SKU_key"]).strip()
        sku_id = str(row["sku_id"]).strip()
        my_size = str(row["MY_SIZE"]).strip()
        order_id = str(int(row["OrderID"])) if isinstance(row["OrderID"], float) else str(row["OrderID"])
        kaspi_offer_name = str(row["KASPI_OFFER_NAME"]).strip()
        store_code = row["store_code"]
        order_date = parse_date(row["Date"])

        if not order_date:
            continue

        # Check if SKU exists
        if sku_key not in sku_data:
            missing_skus.add(sku_key)
            continue

        sku_info = sku_data[sku_key]

        # Check for zero cost
        if sku_info["base_cost_cny"] == 0 or sku_info["weight_kg"] == 0:
            zero_cost_skus.add(sku_key)
            continue

        # Auto-create dim_sku_size if needed
        if sku_id not in existing_sizes:
            create_sku_size(conn, sku_id, sku_key, my_size)
            existing_sizes.add(sku_id)
            sizes_created += 1

        # Calculate economics
        try:
            econ = calc_line_values(
                sell_price_kzt=float(row["Sell_price_kzt"]),
                base_cost_cny=sku_info["base_cost_cny"],
                weight_kg=sku_info["weight_kg"],
                quantity=int(row["Quantity"]),
            )
        except Exception as e:
            if verbose:
                print(f"  Warning: Calc error for order {order_id}: {e}")
            continue

        records.append({
            "order_id": order_id,
            "kaspi_offer_name": kaspi_offer_name,
            "store_code": store_code,
            "order_date": order_date,
            "sku_key": sku_key,
            "sku_id": sku_id,
            "my_size": my_size,
            "quantity": int(row["Quantity"]),
            "sell_price_kzt": float(row["Sell_price_kzt"]),
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

    if verbose:
        if missing_skus:
            print(f"\n  Warning: {len(missing_skus)} SKUs missing from dim_sku:")
            for sku in sorted(missing_skus)[:5]:
                print(f"    - {sku}")
            if len(missing_skus) > 5:
                print(f"    ... and {len(missing_skus) - 5} more")
        if zero_cost_skus:
            print(f"  Warning: {len(zero_cost_skus)} SKUs with zero cost/weight skipped")
        if sizes_created > 0:
            print(f"  Created {sizes_created} new dim_sku_size entries")

    return records


def rebuild_fact_sales(records: list[dict], conn: sqlite3.Connection, dry_run: bool = False):
    """Delete existing fact_sales and insert new records."""
    cursor = conn.cursor()

    if dry_run:
        cursor.execute("SELECT COUNT(*) FROM fact_sales")
        old_count = cursor.fetchone()[0]
        print(f"\n[DRY RUN] Would delete {old_count} existing fact_sales rows")
        print(f"[DRY RUN] Would insert {len(records)} new rows")
        return

    # Delete existing data
    cursor.execute("SELECT COUNT(*) FROM fact_sales")
    old_count = cursor.fetchone()[0]
    print(f"\nDeleting {old_count} existing fact_sales rows...")
    cursor.execute("DELETE FROM fact_sales")

    # Insert new data
    print(f"Inserting {len(records)} rows...")

    sql = """
        INSERT INTO fact_sales (
            order_id, kaspi_offer_name, store_code, order_date,
            sku_key, sku_id, my_size, quantity, sell_price_kzt,
            product_type, channel, delivery_fee, net_rev_unit,
            line_net_rev, cogs_unit, cogs_line, profit_unit, profit_line
        ) VALUES (
            :order_id, :kaspi_offer_name, :store_code, :order_date,
            :sku_key, :sku_id, :my_size, :quantity, :sell_price_kzt,
            :product_type, :channel, :delivery_fee, :net_rev_unit,
            :line_net_rev, :cogs_unit, :cogs_line, :profit_unit, :profit_line
        )
    """

    cursor.executemany(sql, records)
    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM fact_sales")
    new_count = cursor.fetchone()[0]
    print(f"  fact_sales now has {new_count} rows")


def rebuild_daily_aggregates(conn: sqlite3.Connection, dry_run: bool = False):
    """Rebuild fact_sales_daily and fact_sales_daily_size."""
    cursor = conn.cursor()

    if dry_run:
        print("\n[DRY RUN] Would rebuild daily aggregates")
        return

    # Delete existing
    cursor.execute("DELETE FROM fact_sales_daily")
    cursor.execute("DELETE FROM fact_sales_daily_size")

    # Rebuild fact_sales_daily (style-level)
    print("\nRebuilding fact_sales_daily...")
    cursor.execute("""
        INSERT INTO fact_sales_daily (sale_date, sku_key, store_code, units, revenue, cogs, profit)
        SELECT
            order_date,
            sku_key,
            store_code,
            SUM(quantity),
            SUM(line_net_rev),
            SUM(cogs_line),
            SUM(profit_line)
        FROM fact_sales
        WHERE order_date IS NOT NULL
        GROUP BY order_date, sku_key, store_code
    """)

    cursor.execute("SELECT COUNT(*) FROM fact_sales_daily")
    daily_count = cursor.fetchone()[0]
    print(f"  fact_sales_daily: {daily_count} rows")

    # Rebuild fact_sales_daily_size (size-level)
    print("Rebuilding fact_sales_daily_size...")
    cursor.execute("""
        INSERT INTO fact_sales_daily_size (sale_date, sku_id, sku_key, my_size, store_code, units, revenue, cogs, profit)
        SELECT
            order_date,
            sku_id,
            sku_key,
            my_size,
            store_code,
            SUM(quantity),
            SUM(line_net_rev),
            SUM(cogs_line),
            SUM(profit_line)
        FROM fact_sales
        WHERE order_date IS NOT NULL
        GROUP BY order_date, sku_id, sku_key, my_size, store_code
    """)

    cursor.execute("SELECT COUNT(*) FROM fact_sales_daily_size")
    size_count = cursor.fetchone()[0]
    print(f"  fact_sales_daily_size: {size_count} rows")

    conn.commit()


def validate_rebuild(conn: sqlite3.Connection):
    """Run validation queries and print results."""
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    # Total records
    cursor.execute("SELECT COUNT(*) FROM fact_sales")
    total = cursor.fetchone()[0]
    print(f"\nfact_sales records: {total:,}")
    if 13000 <= total <= 14000:
        print("  Within expected range")
    else:
        print(f"  Warning: expected ~13,400")

    # Date range
    cursor.execute("SELECT MIN(order_date), MAX(order_date) FROM fact_sales")
    min_date, max_date = cursor.fetchone()
    print(f"\nDate range: {min_date} to {max_date}")

    # Unique orders
    cursor.execute("SELECT COUNT(DISTINCT order_id) FROM fact_sales")
    unique_orders = cursor.fetchone()[0]
    print(f"Unique orders: {unique_orders:,}")

    # Total units
    cursor.execute("SELECT SUM(quantity) FROM fact_sales")
    total_units = cursor.fetchone()[0]
    print(f"Total units sold: {total_units:,}")

    # Check for duplicates
    cursor.execute("""
        SELECT order_id, kaspi_offer_name, sku_id, store_code, COUNT(*) as cnt
        FROM fact_sales
        GROUP BY order_id, kaspi_offer_name, sku_id, store_code
        HAVING cnt > 1
        LIMIT 5
    """)
    dups = cursor.fetchall()
    if dups:
        print(f"\nWarning: Found {len(dups)} duplicate order lines:")
        for d in dups:
            print(f"  {d}")
    else:
        print("\nNo duplicate order lines")

    # Top SKUs
    cursor.execute("""
        SELECT sku_key, SUM(quantity) as units, COUNT(*) as orders
        FROM fact_sales
        GROUP BY sku_key
        ORDER BY units DESC
        LIMIT 5
    """)
    print("\nTop 5 SKUs by volume:")
    for sku, units, orders in cursor.fetchall():
        print(f"  {sku}: {units:,} units, {orders:,} orders")

    # Daily aggregates
    cursor.execute("SELECT COUNT(*), SUM(units) FROM fact_sales_daily")
    daily_rows, daily_units = cursor.fetchone()
    print(f"\nfact_sales_daily: {daily_rows:,} rows, {daily_units:,} total units")

    cursor.execute("SELECT COUNT(*), SUM(units) FROM fact_sales_daily_size")
    size_rows, size_units = cursor.fetchone()
    print(f"fact_sales_daily_size: {size_rows:,} rows, {size_units:,} total units")

    # Cross-check totals
    if total_units == daily_units == size_units:
        print("\nUnit totals match across all tables")
    else:
        print(f"\nWarning: Unit mismatch - fact_sales={total_units}, daily={daily_units}, size={size_units}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Rebuild fact_sales from Archive_sales")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying DB")
    args = parser.parse_args()

    print("=" * 60)
    print("PHASE 6.5: SALES DATA REBUILD")
    print(f"Started: {datetime.now()}")
    print("=" * 60)

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Load Excel data
        df = load_excel_data(EXCEL_PATH)

        # Clean and aggregate
        df = clean_and_aggregate(df)

        # Connect to DB
        conn = sqlite3.connect(DB_PATH)

        # Process records and calculate economics
        print("\nProcessing records...")
        records = process_records(df, conn, verbose=True)
        print(f"  Valid records for import: {len(records):,}")

        # Rebuild fact_sales
        rebuild_fact_sales(records, conn, dry_run=args.dry_run)

        # Rebuild daily aggregates
        rebuild_daily_aggregates(conn, dry_run=args.dry_run)

        # Validate
        if not args.dry_run:
            validate_rebuild(conn)

        conn.close()

        print(f"\nRebuild complete: {datetime.now()}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
