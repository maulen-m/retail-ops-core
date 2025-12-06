#!/usr/bin/env python3
"""
TASK-049: Executive Summary Export

One-page business health snapshot in JSON format.

Usage:
    python scripts/export_executive_summary.py

Output:
    exports/executive_summary_YYYY-MM-DD.json
"""

import argparse
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_revenue_metrics(db_path: str, days: int = 30) -> dict:
    """Get revenue and profit metrics for period."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT
            SUM(profit_line) as profit,
            SUM(line_net_rev) as revenue,
            SUM(cogs_line) as cogs,
            COUNT(DISTINCT order_id) as orders,
            SUM(quantity) as units
        FROM fact_sales
        WHERE order_date >= ?
    """, (cutoff,))

    row = cursor.fetchone()
    conn.close()

    if not row or row[0] is None:
        return {
            'revenue_30d_kzt': 0,
            'profit_30d_kzt': 0,
            'cogs_30d_kzt': 0,
            'margin_pct': 0,
            'orders_30d': 0,
            'units_30d': 0
        }

    profit = row[0] or 0
    revenue = row[1] or 0
    margin = (profit / revenue * 100) if revenue > 0 else 0

    return {
        'revenue_30d_kzt': round(revenue, 0),
        'profit_30d_kzt': round(profit, 0),
        'cogs_30d_kzt': round(row[2] or 0, 0),
        'margin_pct': round(margin, 1),
        'orders_30d': row[3] or 0,
        'units_30d': row[4] or 0
    }


def get_inventory_metrics(db_path: str) -> dict:
    """Get inventory value and turnover metrics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get total inventory value
    cursor.execute("""
        SELECT SUM(k_avg)
        FROM fact_sku_metrics
        WHERE k_avg > 0
    """)
    inv_value = cursor.fetchone()[0] or 0

    # Get COGS for last 365 days for turnover calculation
    cursor.execute("""
        SELECT SUM(cogs_line)
        FROM fact_sales
        WHERE order_date >= date('now', '-365 days')
    """)
    annual_cogs = cursor.fetchone()[0] or 0

    # Calculate turns
    avg_inventory = inv_value  # Simplified, should be average over period
    turns = annual_cogs / avg_inventory if avg_inventory > 0 else 0

    conn.close()

    return {
        'inventory_value_kzt': round(inv_value, 0),
        'inventory_turns_annual': round(turns, 1)
    }


def get_top_performers(db_path: str, limit: int = 5) -> list[dict]:
    """Get top performing SKUs by ROIC."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT sku_key, roic_monthly, d30, k_avg
        FROM fact_sku_metrics
        WHERE roic_monthly IS NOT NULL
        ORDER BY roic_monthly DESC
        LIMIT ?
    """, (limit,))

    results = []
    for row in cursor.fetchall():
        results.append({
            'sku_key': row[0],
            'roic_pct': round(row[1], 1) if row[1] else 0,
            'd30': round(row[2], 2) if row[2] else 0,
            'capital_kzt': round(row[3], 0) if row[3] else 0
        })

    conn.close()
    return results


def get_alert_counts(db_path: str) -> dict:
    """Get counts of various alerts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Reorder alerts
    cursor.execute("""
        SELECT COUNT(*)
        FROM fact_sku_metrics
        WHERE status = 'REORDER'
    """)
    reorder = cursor.fetchone()[0] or 0

    # Stockout events in last 30 days
    cursor.execute("""
        SELECT COUNT(*)
        FROM fact_stockout_events
        WHERE event_date >= date('now', '-30 days')
        AND resolved_at IS NULL
    """)
    stockouts = cursor.fetchone()[0] or 0

    conn.close()

    return {
        'reorder_alerts': reorder,
        'stockout_events_30d': stockouts
    }


def get_forecast_metrics(db_path: str) -> dict:
    """Get forecast accuracy metrics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT AVG(mape)
        FROM fact_forecast_accuracy
        WHERE accuracy_date = (SELECT MAX(accuracy_date) FROM fact_forecast_accuracy)
        AND horizon_days = 7
    """)

    result = cursor.fetchone()
    conn.close()

    return {
        'forecast_mape': round(result[0], 1) if result and result[0] else None
    }


def get_portfolio_metrics(db_path: str) -> dict:
    """Get portfolio-level metrics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            SUM(k_avg) as total_capital,
            SUM(roic_monthly * k_avg) / NULLIF(SUM(k_avg), 0) as weighted_roic
        FROM fact_sku_metrics
        WHERE k_avg > 0
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        'capital_deployed_kzt': round(row[0], 0) if row[0] else 0,
        'portfolio_roic_pct': round(row[1], 1) if row[1] else 0
    }


def main():
    parser = argparse.ArgumentParser(description='Export executive summary')
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve database path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"=== Executive Summary Export ===")
    print(f"Database: {db_path}")
    print()

    # Gather all metrics
    revenue = get_revenue_metrics(str(db_path))
    inventory = get_inventory_metrics(str(db_path))
    top_performers = get_top_performers(str(db_path))
    alerts = get_alert_counts(str(db_path))
    forecast = get_forecast_metrics(str(db_path))
    portfolio = get_portfolio_metrics(str(db_path))

    # Build export
    export = {
        'report_date': date.today().isoformat(),
        **revenue,
        **inventory,
        'top_performers': top_performers,
        **alerts,
        **forecast,
        **portfolio
    }

    # Write JSON
    exports_dir = project_root / 'exports'
    exports_dir.mkdir(parents=True, exist_ok=True)
    output_path = exports_dir / f'executive_summary_{date.today().isoformat()}.json'

    with open(output_path, 'w') as f:
        json.dump(export, f, indent=2)

    print(f"Export saved: {output_path}")
    print()
    print(f"=== Summary ===")
    print(f"Revenue (30d): {export['revenue_30d_kzt']:,.0f} KZT")
    print(f"Profit (30d): {export['profit_30d_kzt']:,.0f} KZT")
    print(f"Margin: {export['margin_pct']}%")
    print(f"Inventory Value: {export['inventory_value_kzt']:,.0f} KZT")
    print(f"Inventory Turns: {export['inventory_turns_annual']}x")
    print(f"Portfolio ROIC: {export['portfolio_roic_pct']}%")
    print(f"Forecast MAPE: {export['forecast_mape']}%")

    return 0


if __name__ == '__main__':
    exit(main())
