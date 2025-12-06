#!/usr/bin/env python3
"""
Build daily capital allocation snapshot.
Calculates capital deployed, ROIC, and portfolio metrics for each SKU.

Run: python scripts/build_capital_snapshot.py [--date YYYY-MM-DD]

TASK-075
"""
import sqlite3
import argparse
from pathlib import Path
from datetime import date, timedelta

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def build_snapshot(snapshot_date: date):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"Building capital snapshot for {snapshot_date}...")

    # Delete existing snapshot for this date
    cursor.execute(
        "DELETE FROM fact_capital_allocation WHERE snapshot_date = ?",
        (snapshot_date.isoformat(),)
    )

    # Calculate 30-day metrics per SKU
    date_30d_ago = (snapshot_date - timedelta(days=30)).isoformat()

    # Insert capital allocation data
    cursor.execute("""
        INSERT INTO fact_capital_allocation (
            snapshot_date, sku_key, store_code,
            inventory_units, inventory_value_kzt,
            on_order_units, on_order_value_kzt, total_capital_kzt,
            revenue_30d_kzt, profit_30d_kzt, roic_30d_pct,
            lifecycle_status
        )
        SELECT
            ? as snapshot_date,
            sk.sku_key,
            'UNIVERSAL' as store_code,

            -- Inventory (from latest snapshot or default to 0)
            COALESCE(inv.total_stock, 0) as inventory_units,
            COALESCE(inv.total_stock * sk.cogs_kzt, 0) as inventory_value_kzt,

            -- On order (from PO lines in transit)
            COALESCE(po.on_order, 0) as on_order_units,
            COALESCE(po.on_order * sk.cogs_kzt, 0) as on_order_value_kzt,
            COALESCE((inv.total_stock + COALESCE(po.on_order, 0)) * sk.cogs_kzt, 0) as total_capital_kzt,

            -- 30-day performance
            COALESCE(sales.revenue_30d, 0) as revenue_30d_kzt,
            COALESCE(sales.profit_30d, 0) as profit_30d_kzt,

            -- ROIC: (Profit / Capital) * 12.17 for annualized (365/30)
            CASE
                WHEN COALESCE(inv.total_stock * sk.cogs_kzt, 0) > 0
                THEN ROUND(COALESCE(sales.profit_30d, 0) / (inv.total_stock * sk.cogs_kzt) * 12.17 * 100, 2)
                ELSE 0
            END as roic_30d_pct,

            -- Lifecycle (from dim_sku_lifecycle if exists)
            COALESCE(lc.lifecycle_status, 'UNKNOWN') as lifecycle_status

        FROM dim_sku sk

        LEFT JOIN (
            -- Aggregate inventory by sku_key (latest snapshot)
            SELECT sku_key, SUM(current_stock) as total_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size)
            GROUP BY sku_key
        ) inv ON sk.sku_key = inv.sku_key

        LEFT JOIN (
            -- 30-day sales aggregates (all stores combined)
            SELECT
                sku_key,
                SUM(revenue) as revenue_30d,
                SUM(profit) as profit_30d
            FROM fact_sales_daily
            WHERE sale_date > ?
            GROUP BY sku_key
        ) sales ON sk.sku_key = sales.sku_key

        LEFT JOIN (
            -- On order from PO lines
            SELECT sku_key, SUM(order_quantity - COALESCE(received_qty, 0)) as on_order
            FROM fact_po_lines
            WHERE status IN ('UNPAID', 'PAID', 'IN_TRANSIT')
            GROUP BY sku_key
        ) po ON sk.sku_key = po.sku_key

        LEFT JOIN dim_sku_lifecycle lc ON sk.sku_key = lc.sku_key

        WHERE sk.active_flag = 1 OR sales.revenue_30d > 0 OR inv.total_stock > 0
    """, (snapshot_date.isoformat(), date_30d_ago))

    rows_inserted = cursor.rowcount
    print(f"  Inserted {rows_inserted} allocation rows")

    # Calculate portfolio metrics
    cursor.execute("""
        SELECT SUM(total_capital_kzt) FROM fact_capital_allocation
        WHERE snapshot_date = ?
    """, (snapshot_date.isoformat(),))
    total_capital = cursor.fetchone()[0] or 0

    if total_capital > 0:
        # Update capital share percentages
        cursor.execute("""
            UPDATE fact_capital_allocation
            SET capital_share_pct = ROUND(total_capital_kzt / ? * 100, 2)
            WHERE snapshot_date = ?
        """, (total_capital, snapshot_date.isoformat()))

        # Update ROIC rankings
        cursor.execute("""
            WITH ranked AS (
                SELECT allocation_id,
                       ROW_NUMBER() OVER (ORDER BY roic_30d_pct DESC) as rank
                FROM fact_capital_allocation
                WHERE snapshot_date = ?
            )
            UPDATE fact_capital_allocation
            SET roic_rank = (
                SELECT rank FROM ranked
                WHERE ranked.allocation_id = fact_capital_allocation.allocation_id
            )
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(), snapshot_date.isoformat()))

    # Build portfolio summary
    cursor.execute(
        "DELETE FROM fact_portfolio_summary WHERE summary_date = ?",
        (snapshot_date.isoformat(),)
    )

    cursor.execute("""
        INSERT INTO fact_portfolio_summary (
            summary_date, total_skus, total_capital_kzt, total_inventory_units,
            revenue_30d_kzt, profit_30d_kzt, portfolio_roic_pct,
            top_10_capital_share_pct, bottom_10_roic_avg_pct,
            grow_count, maintain_count, harvest_count, kill_count
        )
        SELECT
            ? as summary_date,
            COUNT(*) as total_skus,
            SUM(total_capital_kzt) as total_capital_kzt,
            SUM(inventory_units) as total_inventory_units,
            SUM(revenue_30d_kzt) as revenue_30d_kzt,
            SUM(profit_30d_kzt) as profit_30d_kzt,

            -- Weighted portfolio ROIC
            CASE
                WHEN SUM(total_capital_kzt) > 0
                THEN ROUND(SUM(profit_30d_kzt) / SUM(total_capital_kzt) * 12.17 * 100, 2)
                ELSE 0
            END as portfolio_roic_pct,

            -- Top 10 concentration
            (SELECT SUM(capital_share_pct)
             FROM fact_capital_allocation
             WHERE snapshot_date = ? AND roic_rank <= 10) as top_10_capital_share_pct,

            -- Bottom 10 avg ROIC
            (SELECT AVG(roic_30d_pct)
             FROM fact_capital_allocation
             WHERE snapshot_date = ?
             AND roic_rank > (SELECT MAX(roic_rank) - 10 FROM fact_capital_allocation WHERE snapshot_date = ?)) as bottom_10_roic_avg_pct,

            -- Lifecycle counts
            SUM(CASE WHEN lifecycle_status = 'GROW' THEN 1 ELSE 0 END),
            SUM(CASE WHEN lifecycle_status = 'MAINTAIN' THEN 1 ELSE 0 END),
            SUM(CASE WHEN lifecycle_status = 'HARVEST' THEN 1 ELSE 0 END),
            SUM(CASE WHEN lifecycle_status = 'KILL' THEN 1 ELSE 0 END)

        FROM fact_capital_allocation
        WHERE snapshot_date = ?
    """, (snapshot_date.isoformat(),) * 5)

    conn.commit()

    # Print summary
    cursor.execute("""
        SELECT total_skus, total_capital_kzt, portfolio_roic_pct,
               grow_count, maintain_count, harvest_count, kill_count
        FROM fact_portfolio_summary WHERE summary_date = ?
    """, (snapshot_date.isoformat(),))

    row = cursor.fetchone()
    if row:
        print(f"\n=== PORTFOLIO SNAPSHOT {snapshot_date} ===")
        print(f"Total SKUs: {row[0]}")
        print(f"Total Capital: {row[1]:,.0f} KZT")
        print(f"Portfolio ROIC: {row[2]:.1f}%")
        print(f"Lifecycle: GROW={row[3]}, MAINTAIN={row[4]}, HARVEST={row[5]}, KILL={row[6]}")

    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, help='Snapshot date (YYYY-MM-DD)',
                        default=date.today().isoformat())
    args = parser.parse_args()

    snapshot_date = date.fromisoformat(args.date)
    build_snapshot(snapshot_date)


if __name__ == "__main__":
    main()
