#!/usr/bin/env python3
"""
Generate list of SKUs recommended for liquidation.
Includes liquidation strategy and expected recovery.

Run: python scripts/generate_kill_list.py

TASK-079
"""
import sqlite3
from pathlib import Path
from datetime import date
import csv

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
REPORT_PATH = Path(__file__).parent.parent / "reports"


def generate_kill_list():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            lc.sku_key,
            lc.lifecycle_status,
            lc.status_reason,
            ca.inventory_units,
            ca.inventory_value_kzt,
            ca.roic_30d_pct,
            sk.cogs_kzt,

            -- Days of inventory
            CASE WHEN d.avg_daily > 0
                THEN ROUND(ca.inventory_units / d.avg_daily, 1)
                ELSE 999
            END as days_of_inventory,

            -- Recovery estimates
            ROUND(ca.inventory_value_kzt * 0.7, 0) as recovery_70pct,
            ROUND(ca.inventory_value_kzt * 0.5, 0) as recovery_50pct

        FROM dim_sku_lifecycle lc
        JOIN fact_capital_allocation ca ON lc.sku_key = ca.sku_key
        JOIN dim_sku sk ON lc.sku_key = sk.sku_key
        LEFT JOIN (
            SELECT sku_key, AVG(units) as avg_daily
            FROM fact_sales_daily
            WHERE sale_date > date('now', '-90 days')
            GROUP BY sku_key
        ) d ON lc.sku_key = d.sku_key

        WHERE lc.lifecycle_status IN ('KILL', 'HARVEST')
          AND ca.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_capital_allocation)
          AND ca.inventory_units > 0
        ORDER BY ca.inventory_value_kzt DESC
    """)

    results = cursor.fetchall()
    conn.close()

    if not results:
        print("No SKUs flagged for kill/harvest with inventory")
        return

    # Generate report
    REPORT_PATH.mkdir(exist_ok=True)
    report_file = REPORT_PATH / f"kill_list_{date.today()}.csv"

    with open(report_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'sku_key', 'status', 'reason', 'units', 'value_kzt', 'roic_pct',
            'cogs_unit', 'days_of_inventory', 'recovery_70pct', 'recovery_50pct',
            'recommended_action'
        ])

        total_capital = 0
        total_recovery = 0

        for row in results:
            sku_key, status, reason, units, value, roic, cogs, doi, r70, r50 = row
            total_capital += value or 0

            # Determine action
            if status == 'KILL':
                if doi and doi > 180:
                    action = f"LIQUIDATE at 50% ({r50:,.0f} KZT) - dead stock"
                    total_recovery += r50 or 0
                else:
                    action = f"LIQUIDATE at 70% ({r70:,.0f} KZT)"
                    total_recovery += r70 or 0
            else:  # HARVEST
                action = "SELL THROUGH - no new orders"
                total_recovery += value or 0

            writer.writerow([
                sku_key, status, reason, units, value, roic,
                cogs, doi, r70, r50, action
            ])

    print("=== KILL LIST GENERATED ===")
    print(f"SKUs flagged: {len(results)}")
    print(f"Capital tied up: {total_capital:,.0f} KZT")
    print(f"Expected recovery: {total_recovery:,.0f} KZT")
    print(f"Capital to free: {total_capital - total_recovery:,.0f} KZT (write-off)")
    print(f"\nReport: {report_file}")


if __name__ == "__main__":
    generate_kill_list()
