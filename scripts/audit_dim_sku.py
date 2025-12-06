#!/usr/bin/env python3
"""
Audit dim_sku for missing cost/weight data.
Identifies SKUs that need manual data entry.

Run: python scripts/audit_dim_sku.py
Output: reports/dim_sku_gaps_YYYY-MM-DD.csv

TASK-070
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
REPORT_PATH = Path(__file__).parent.parent / "reports"


def audit_sku_gaps():
    conn = sqlite3.connect(DB_PATH)

    # Find SKUs with missing data
    df = pd.read_sql_query("""
        SELECT
            s.sku_key,
            s.cogs_kzt,
            s.base_cost_cny,
            s.weight_kg,
            s.product_type,
            COUNT(f.order_id) as sales_count,
            SUM(f.quantity) as total_units,
            SUM(f.sell_price_kzt * f.quantity) as total_revenue
        FROM dim_sku s
        LEFT JOIN fact_sales f ON s.sku_key = f.sku_key
        WHERE s.cogs_kzt IS NULL OR s.cogs_kzt = 0
           OR s.base_cost_cny IS NULL OR s.base_cost_cny = 0
        GROUP BY s.sku_key
        ORDER BY total_units DESC NULLS LAST
    """, conn)

    conn.close()

    # Save report
    REPORT_PATH.mkdir(exist_ok=True)
    output_file = REPORT_PATH / f"dim_sku_gaps_{datetime.now():%Y-%m-%d}.csv"
    df.to_csv(output_file, index=False)

    print("=== DIM_SKU GAP AUDIT ===")
    print(f"SKUs with missing COGS: {len(df)}")
    print(f"Affected sales records: {df['sales_count'].sum()}")
    print(f"Affected units: {df['total_units'].sum()}")
    print(f"Affected revenue: {df['total_revenue'].sum():,.0f} KZT")
    print(f"\nReport saved: {output_file}")

    # Show top 10 by impact
    print(f"\nTop 10 by sales volume:")
    print(df.head(10).to_string(index=False))

    return df


if __name__ == "__main__":
    audit_sku_gaps()
