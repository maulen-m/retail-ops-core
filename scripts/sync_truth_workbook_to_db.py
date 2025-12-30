#!/usr/bin/env python3
"""
Sync truth workbook to database.

This script reads the authoritative truth workbook and updates database tables
needed for demand estimation and PO calculation.

Source of truth: excel/PO-generator_FILLED_2025-12-15_GPT_1.xlsx
Target: db/app.db (sales_fact_v2, fact_inventory_snapshot_size, fact_po_lines, etc.)

Usage:
    python scripts/sync_truth_workbook_to_db.py

Sheet → Table Mapping:
    Fact_Sales → sales_fact_v2 (Kaspi sales only)
    DIM_SKU_ID → fact_inventory_snapshot_size (current stock by size)
    Fact_PO_Lines + Dim_PO_Header → fact_po_lines (PO receipts with arrival dates)
    SizeMix_and_Di_Anchor → dim_anchor (new table for demand anchors)
    Dim_SKU → dim_sku (SKU master)
    Dim_Params_PT → dim_params (product-type parameters)
"""

import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
TRUTH_WORKBOOK = PROJECT_ROOT / "excel" / "PO-generator_FILLED_2025-12-15_GPT_1.xlsx"
DB_PATH = PROJECT_ROOT / "db" / "app.db"


def create_anchor_table(conn: sqlite3.Connection) -> None:
    """Create dim_anchor table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_anchor (
            sku_key TEXT PRIMARY KEY,
            d_active REAL NOT NULL DEFAULT 0,
            sigma REAL DEFAULT 0,
            S_share REAL DEFAULT 0,
            M_share REAL DEFAULT 0,
            L_share REAL DEFAULT 0,
            XL_share REAL DEFAULT 0,
            "2XL_share" REAL DEFAULT 0,
            "3XL_share" REAL DEFAULT 0,
            "4XL_share" REAL DEFAULT 0,
            "22_share" REAL DEFAULT 0,
            "24_share" REAL DEFAULT 0,
            "26_share" REAL DEFAULT 0,
            "28_share" REAL DEFAULT 0,
            "30_share" REAL DEFAULT 0,
            S_D REAL DEFAULT 0,
            M_D REAL DEFAULT 0,
            L_D REAL DEFAULT 0,
            XL_D REAL DEFAULT 0,
            "2XL_D" REAL DEFAULT 0,
            "3XL_D" REAL DEFAULT 0,
            "4XL_D" REAL DEFAULT 0,
            "22_D" REAL DEFAULT 0,
            "24_D" REAL DEFAULT 0,
            "26_D" REAL DEFAULT 0,
            "28_D" REAL DEFAULT 0,
            "30_D" REAL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def sync_sales(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync Fact_Sales sheet to sales_fact_v2.

    Returns dict with row counts and max date.
    """
    print("Reading Fact_Sales sheet...")
    df = pd.read_excel(xl, sheet_name='Fact_Sales')

    # Filter Kaspi only
    df = df[df['Channel'] == 'Kaspi'].copy()

    # Convert date column
    df['Date'] = pd.to_datetime(df['Date']).dt.date

    # Rename columns to match DB schema
    df = df.rename(columns={
        'Date': 'order_date',
        'OrderID': 'order_id',
        'SKU_key': 'sku_key',
        'SKU_ID': 'sku_id',
        'Quantity': 'quantity',
        'Sell_price_kzt': 'sell_price_kzt',
        'Delivery_fee': 'delivery_fee',
        'COGS_unit': 'cogs',
        'Net_rev_unit': 'net_rev',
        'Profit_unit': 'profit',
        'Kaspi_Offer_name': 'kaspi_offer_name'
    })

    # Extract MY_SIZE from SKU_ID (e.g., CL_OC_MEN_LINE52_BLACK_XL -> XL)
    df['my_size'] = df['sku_id'].apply(lambda x: str(x).split('_')[-1] if pd.notna(x) else 'UNKNOWN')

    # Add default columns
    df['store_code'] = 'UNIVERSAL'
    df['status'] = 'DELIVERED'
    df['return_flag'] = 0

    # Filter required columns
    cols = ['order_id', 'order_date', 'sku_key', 'sku_id', 'my_size', 'kaspi_offer_name',
            'store_code', 'quantity', 'sell_price_kzt', 'delivery_fee', 'cogs',
            'net_rev', 'profit', 'status', 'return_flag']
    df = df[cols].copy()

    # Remove rows with missing required fields
    df = df.dropna(subset=['order_id', 'sku_id', 'sku_key', 'kaspi_offer_name'])

    # Convert order_id to string
    df['order_id'] = df['order_id'].astype(str)
    df['order_date'] = df['order_date'].astype(str)

    # Deduplicate by unique constraint columns (keep first occurrence)
    df = df.drop_duplicates(subset=['order_id', 'sku_id', 'store_code', 'kaspi_offer_name'], keep='first')

    # Delete existing data and insert fresh (for clean sync)
    print(f"  Clearing sales_fact_v2 and inserting {len(df)} rows...")
    conn.execute("DELETE FROM sales_fact_v2")

    # Insert in batches
    batch_size = 1000
    inserted = 0
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        batch.to_sql('sales_fact_v2', conn, if_exists='append', index=False)
        inserted += len(batch)

    # Get stats
    max_date = df['order_date'].max()
    min_date = df['order_date'].min()

    return {
        'table': 'sales_fact_v2',
        'rows_inserted': inserted,
        'min_date': min_date,
        'max_date': max_date
    }


def sync_stock_snapshot(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync DIM_SKU_ID sheet to fact_inventory_snapshot_size.

    Returns dict with row counts.
    """
    print("Reading DIM_SKU_ID sheet...")
    df = pd.read_excel(xl, sheet_name='DIM_SKU_ID')

    # Rename columns
    df = df.rename(columns={
        'SKU_ID': 'sku_id',
        'SKU_key': 'sku_key',
        'MY_SIZE': 'my_size',
        'Stock_date': 'snapshot_date',
        'Current_stock': 'current_stock',
        'Inbound_stock': 'inbound_stock'
    })

    # Convert date
    df['snapshot_date'] = pd.to_datetime(df['snapshot_date']).dt.date.astype(str)

    # Fill NaN stock values with 0
    df['current_stock'] = df['current_stock'].fillna(0).astype(int)
    df['inbound_stock'] = df['inbound_stock'].fillna(0).astype(int)

    # Filter required columns
    cols = ['snapshot_date', 'sku_id', 'sku_key', 'my_size', 'current_stock', 'inbound_stock']
    df = df[cols].copy()

    # Remove rows with missing required fields
    df = df.dropna(subset=['sku_id', 'sku_key', 'my_size'])

    # Get the snapshot date (should be consistent, use mode)
    snapshot_date = df['snapshot_date'].mode().iloc[0] if len(df) > 0 else None

    # Delete existing data for this date and insert fresh
    print(f"  Clearing fact_inventory_snapshot_size for date {snapshot_date}...")
    conn.execute("DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date = ?", (snapshot_date,))

    # Insert
    df.to_sql('fact_inventory_snapshot_size', conn, if_exists='append', index=False)

    return {
        'table': 'fact_inventory_snapshot_size',
        'rows_inserted': len(df),
        'snapshot_date': snapshot_date
    }


def sync_po_lines(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync Fact_PO_Lines + Dim_PO_Header to fact_po_lines.

    Returns dict with row counts.
    """
    print("Reading Fact_PO_Lines and Dim_PO_Header sheets...")
    lines_df = pd.read_excel(xl, sheet_name='Fact_PO_Lines')
    header_df = pd.read_excel(xl, sheet_name='Dim_PO_Header')

    # Join lines with header on Internal_order_code
    df = lines_df.merge(
        header_df[['Internal_order_code', 'PO_Date', 'Est_arrival_date', 'Actual_arrival_date', 'Status']],
        on='Internal_order_code',
        how='left',
        suffixes=('', '_header')
    )

    # Rename columns to match fact_po_lines schema
    df = df.rename(columns={
        'Internal_order_code': 'po_id',
        'SKU_KEY': 'sku_key',
        'SKU_ID': 'sku_id',
        'MY_SIZE': 'my_size',
        'Order_Quantity': 'order_quantity',
        'Unit_COGS_KZT': 'unit_cost_kzt',
        'PO_Date': 'po_date',
        'Est_arrival_date': 'est_arrival_date',
        'Actual_arrival_date': 'actual_arrival_date',
        'Status_header': 'status',
        'Received_Qty': 'received_qty'
    })

    # Convert dates
    for col in ['po_date', 'est_arrival_date', 'actual_arrival_date']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            df[col] = df[col].apply(lambda x: str(x) if pd.notna(x) else None)

    # Add store_code
    df['store_code'] = 'UNIVERSAL'

    # Fill NaN
    df['order_quantity'] = df['order_quantity'].fillna(0).astype(int)
    df['received_qty'] = df['received_qty'].fillna(0).astype(int)
    df['status'] = df['status'].fillna('UNPAID')

    # Filter required columns
    cols = ['po_id', 'store_code', 'sku_key', 'sku_id', 'my_size', 'order_quantity',
            'unit_cost_kzt', 'po_date', 'est_arrival_date', 'actual_arrival_date',
            'status', 'received_qty']
    df = df[cols].copy()

    # Remove rows with missing required fields
    df = df.dropna(subset=['po_id', 'sku_id', 'sku_key'])

    # Delete existing and insert fresh
    print(f"  Clearing fact_po_lines and inserting {len(df)} rows...")
    conn.execute("DELETE FROM fact_po_lines")

    # Insert
    df.to_sql('fact_po_lines', conn, if_exists='append', index=False)

    # Count POs with arrival dates
    has_arrival = df['actual_arrival_date'].notna().sum()

    return {
        'table': 'fact_po_lines',
        'rows_inserted': len(df),
        'rows_with_arrival_date': has_arrival,
        'unique_pos': df['po_id'].nunique()
    }


def sync_anchors(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync SizeMix_and_Di_Anchor to dim_anchor table.

    Returns dict with row counts.
    """
    print("Reading SizeMix_and_Di_Anchor sheet...")
    df = pd.read_excel(xl, sheet_name='SizeMix_and_Di_Anchor')

    # Rename SKU_key
    df = df.rename(columns={'SKU_key': 'sku_key'})

    # Filter required columns (all share and D columns + sigma)
    share_cols = [c for c in df.columns if c.endswith('_share')]
    d_cols = [c for c in df.columns if c.endswith('_D') and c != 'D_active']

    cols = ['sku_key', 'D_active', 'sigma'] + share_cols + d_cols
    cols = [c for c in cols if c in df.columns]
    df = df[cols].copy()

    # Rename D_active to d_active
    df = df.rename(columns={'D_active': 'd_active'})

    # Fill NaN with 0
    for col in df.columns:
        if col != 'sku_key':
            df[col] = df[col].fillna(0)

    # Remove rows with missing sku_key
    df = df.dropna(subset=['sku_key'])

    # Delete existing and insert fresh
    print(f"  Clearing dim_anchor and inserting {len(df)} rows...")
    conn.execute("DELETE FROM dim_anchor")

    # Insert
    df.to_sql('dim_anchor', conn, if_exists='append', index=False)

    return {
        'table': 'dim_anchor',
        'rows_inserted': len(df),
        'avg_d_active': df['d_active'].mean()
    }


def resolve_avg_sell_price(
    sku_key: str,
    dim_sku_price: float,
    conn: sqlite3.Connection,
    cutoff_date: str
) -> tuple[float, str, int]:
    """
    Resolve avg_sell_price with priority logic:

    1. Dim_SKU.Avg_price_90D if > 0
    2. Fact_Sales: 30d weighted avg (prefer recent sales)
    3. Fact_Sales: 90d weighted avg
    4. Median of last 5 sales
    5. NULL + price_missing_flag=1

    Returns: (price_kzt, source, missing_flag)
    """
    # Priority 1: Use Dim_SKU price if available
    if dim_sku_price is not None and dim_sku_price > 0:
        return dim_sku_price, 'DIM_SKU', 0

    # Priority 2: 30-day weighted average from Fact_Sales
    result = conn.execute("""
        SELECT
            SUM(sell_price_kzt * quantity) / SUM(quantity) as weighted_avg,
            SUM(quantity) as total_qty
        FROM fact_sales
        WHERE sku_key = ?
          AND order_date >= date(?, '-30 days')
          AND order_date <= ?
    """, (sku_key, cutoff_date, cutoff_date)).fetchone()

    if result and result[0] and result[1] and result[1] >= 3:  # Need at least 3 units sold
        return result[0], 'FACT_SALES_30D', 0

    # Priority 3: 90-day weighted average
    result = conn.execute("""
        SELECT
            SUM(sell_price_kzt * quantity) / SUM(quantity) as weighted_avg,
            SUM(quantity) as total_qty
        FROM fact_sales
        WHERE sku_key = ?
          AND order_date >= date(?, '-90 days')
          AND order_date <= ?
    """, (sku_key, cutoff_date, cutoff_date)).fetchone()

    if result and result[0] and result[1] and result[1] >= 3:
        return result[0], 'FACT_SALES_90D', 0

    # Priority 4: Median of last 5 sales
    result = conn.execute("""
        SELECT sell_price_kzt
        FROM fact_sales
        WHERE sku_key = ?
          AND order_date <= ?
        ORDER BY order_date DESC
        LIMIT 5
    """, (sku_key, cutoff_date)).fetchall()

    if result and len(result) >= 1:
        prices = sorted([r[0] for r in result if r[0] is not None])
        if prices:
            median_idx = len(prices) // 2
            median_price = prices[median_idx] if len(prices) % 2 == 1 else (prices[median_idx-1] + prices[median_idx]) / 2
            return median_price, 'MEDIAN_5', 0

    # Priority 5: No price available
    return None, 'MISSING', 1


def sync_dim_sku(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync Dim_SKU sheet to dim_sku table.

    Now includes price resolution with priority logic:
    1. Dim_SKU.Avg_price_90D if > 0
    2. Fact_Sales: 30d weighted avg
    3. Fact_Sales: 90d weighted avg
    4. Median last 5 sales
    5. NULL + price_missing_flag=1

    Returns dict with row counts.
    """
    print("Reading Dim_SKU sheet...")
    df = pd.read_excel(xl, sheet_name='Dim_SKU')

    # Get cutoff date (latest sale date in DB)
    cutoff_result = conn.execute("SELECT MAX(order_date) FROM fact_sales").fetchone()
    cutoff_date = cutoff_result[0] if cutoff_result and cutoff_result[0] else date.today().isoformat()
    print(f"  Using cutoff date: {cutoff_date}")

    # Rename columns
    df = df.rename(columns={
        'SKU_key': 'sku_key',
        'Product_Type': 'product_type',
        'Weight_kg': 'weight_kg',
        'BaseCost_CNY': 'base_cost_cny',
        'Base_cost_kzt': 'cogs_kzt',
        'Current_stock': 'current_stock',
        'Avg_price_90D': 'avg_price_90d',
        'Is_Active': 'active_flag'
    })

    # Extract model and color from sku_key (e.g., CL_OC_MEN_LINE52_BLACK -> LINE52, BLACK)
    def parse_sku_key(sku_key):
        parts = str(sku_key).split('_')
        if len(parts) >= 5:
            return parts[-2], parts[-1]  # model, color
        elif len(parts) >= 2:
            return parts[-1], None
        return sku_key, None

    df['model'] = df['sku_key'].apply(lambda x: parse_sku_key(x)[0])
    df['color'] = df['sku_key'].apply(lambda x: parse_sku_key(x)[1])

    # Convert active_flag
    df['active_flag'] = df['active_flag'].apply(lambda x: 1 if x == 'YES' or x == 1 or x == True else 0)

    # Fill defaults
    df['weight_kg'] = df['weight_kg'].fillna(0.5)
    df['base_cost_cny'] = df['base_cost_cny'].fillna(50)
    df['product_type'] = df['product_type'].fillna('CL')

    # Remove rows with missing sku_key
    df = df.dropna(subset=['sku_key'])

    # Upsert with price resolution
    print(f"  Updating dim_sku with {len(df)} rows (resolving prices)...")

    price_sources = {'DIM_SKU': 0, 'FACT_SALES_30D': 0, 'FACT_SALES_90D': 0, 'MEDIAN_5': 0, 'MISSING': 0}

    for _, row in df.iterrows():
        sku_key = row['sku_key']
        dim_sku_price = row.get('avg_price_90d')

        # Resolve price using priority logic
        price_used, price_source, missing_flag = resolve_avg_sell_price(
            sku_key, dim_sku_price, conn, cutoff_date
        )

        price_sources[price_source] = price_sources.get(price_source, 0) + 1

        conn.execute("""
            INSERT OR REPLACE INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg,
                active_flag, cogs_kzt, avg_sell_price_kzt_used, avg_sell_price_source, price_missing_flag
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sku_key, row.get('model'), row.get('color'), row['product_type'],
            row['base_cost_cny'], row['weight_kg'], row['active_flag'], row.get('cogs_kzt'),
            price_used, price_source, missing_flag
        ))

    conn.commit()

    print(f"  Price resolution summary:")
    for source, count in price_sources.items():
        if count > 0:
            print(f"    {source}: {count}")

    return {
        'table': 'dim_sku',
        'rows_updated': len(df),
        'active_count': int(df['active_flag'].sum()),
        'price_sources': price_sources
    }


def sync_dim_sku_size(conn: sqlite3.Connection, xl: pd.ExcelFile) -> dict:
    """
    Sync DIM_SKU_ID sheet to dim_sku_size table.

    Returns dict with row counts.
    """
    print("Reading DIM_SKU_ID for dim_sku_size...")
    df = pd.read_excel(xl, sheet_name='DIM_SKU_ID')

    # Rename columns
    df = df.rename(columns={
        'SKU_ID': 'sku_id',
        'SKU_key': 'sku_key',
        'MY_SIZE': 'my_size'
    })

    # Filter required columns
    cols = ['sku_id', 'sku_key', 'my_size']
    df = df[cols].copy()

    # Remove duplicates and missing
    df = df.dropna(subset=['sku_id', 'sku_key', 'my_size'])
    df = df.drop_duplicates(subset=['sku_id'])

    # Add size_order for sorting
    size_order_map = {
        'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, '2XL': 5, '3XL': 6, '4XL': 7, '5XL': 8,
        '22': 22, '24': 24, '26': 26, '28': 28, '30': 30, '32': 32, '34': 34, '36': 36
    }
    df['size_order'] = df['my_size'].map(size_order_map).fillna(99).astype(int)
    df['active_flag'] = 1

    # Upsert
    print(f"  Updating dim_sku_size with {len(df)} rows...")

    for _, row in df.iterrows():
        conn.execute("""
            INSERT OR REPLACE INTO dim_sku_size (sku_id, sku_key, my_size, size_order, active_flag)
            VALUES (?, ?, ?, ?, ?)
        """, (row['sku_id'], row['sku_key'], row['my_size'], row['size_order'], row['active_flag']))

    conn.commit()

    return {
        'table': 'dim_sku_size',
        'rows_updated': len(df),
        'unique_sku_keys': df['sku_key'].nunique()
    }


def main():
    """Main sync function."""
    print("=" * 60)
    print("SYNC TRUTH WORKBOOK TO DATABASE")
    print("=" * 60)
    print(f"Source: {TRUTH_WORKBOOK}")
    print(f"Target: {DB_PATH}")
    print(f"Run at: {datetime.now().isoformat()}")
    print()

    if not TRUTH_WORKBOOK.exists():
        print(f"ERROR: Truth workbook not found: {TRUTH_WORKBOOK}")
        sys.exit(1)

    # Load workbook
    print("Loading workbook...")
    xl = pd.ExcelFile(TRUTH_WORKBOOK)
    print(f"  Sheets: {xl.sheet_names}")
    print()

    # Connect to DB
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Create anchor table if needed
    create_anchor_table(conn)

    results = []

    # Sync each table
    try:
        # 1. Dim tables first (dependencies)
        results.append(sync_dim_sku(conn, xl))
        results.append(sync_dim_sku_size(conn, xl))

        # 2. Fact tables
        results.append(sync_sales(conn, xl))
        results.append(sync_stock_snapshot(conn, xl))
        results.append(sync_po_lines(conn, xl))
        results.append(sync_anchors(conn, xl))

        conn.commit()

    except Exception as e:
        print(f"ERROR during sync: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    # Print summary
    print()
    print("=" * 60)
    print("SYNC SUMMARY")
    print("=" * 60)
    for r in results:
        print(f"\n{r['table']}:")
        for k, v in r.items():
            if k != 'table':
                print(f"  {k}: {v}")

    # Verify sales max date
    conn = sqlite3.connect(str(DB_PATH))
    max_date = conn.execute("SELECT MAX(order_date) FROM sales_fact_v2").fetchone()[0]
    conn.close()

    print()
    print("=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    print(f"Sales max date in DB: {max_date}")

    expected_date = "2025-12-16"
    if max_date == expected_date:
        print(f"  [OK] Sales data through {expected_date}")
    else:
        print(f"  [WARNING] Expected max date {expected_date}, got {max_date}")

    print()
    print("Sync complete.")


if __name__ == "__main__":
    main()
