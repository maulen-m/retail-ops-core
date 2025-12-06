#!/usr/bin/env python3
"""
Run SKU Metrics: Compute inventory metrics for all active SKUs.

This script:
1. Calculates D30 from fact_sales_daily (last 30 days)
2. Gets avg price and economics from fact_sales
3. Computes all inventory metrics (SS, ROP, ROIC, Status)
4. Outputs to fact_sku_metrics table or CSV

Output columns:
- sku_key, store_code
- d30, sigma, ss_total, rop
- avg_price, avg_cogs, avg_profit
- roic_monthly, k_avg
- current_stock, inbound_stock, total_stock
- status, suggested_order_qty

Usage:
    python scripts/run_sku_metrics.py              # Compute and save to DB
    python scripts/run_sku_metrics.py --csv output.csv  # Export to CSV
    python scripts/run_sku_metrics.py --dry-run    # Preview without saving
"""

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db
from core.calc.inventory import calc_all_metrics, calc_suggested_order_qty
from core.calc.status import calc_status


def get_d30_by_sku(conn, days: int = 30) -> dict:
    """
    Get D30 (avg daily units) for each SKU from fact_sales_daily.

    Returns dict: {(sku_key, store_code): d30}
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = """
        SELECT
            sku_key,
            store_code,
            SUM(units) as total_units,
            COUNT(DISTINCT sale_date) as days_with_sales
        FROM fact_sales_daily
        WHERE sale_date >= :cutoff_date
        GROUP BY sku_key, store_code
    """

    cursor = conn.execute(query, {"cutoff_date": cutoff_date})
    result = {}

    for row in cursor.fetchall():
        sku_key, store_code, total_units, days_with_sales = row
        # D30 = total units / 30 days (not days_with_sales)
        d30 = total_units / days
        result[(sku_key, store_code)] = {
            "d30": d30,
            "total_units": total_units,
            "days_with_sales": days_with_sales,
        }

    return result


def get_avg_economics_by_sku(conn, days: int = 30) -> dict:
    """
    Get average economics (price, COGS, profit) for each SKU.

    Returns dict: {(sku_key, store_code): {avg_price, avg_cogs, avg_profit}}
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = """
        SELECT
            sku_key,
            store_code,
            AVG(sell_price_kzt) as avg_price,
            AVG(cogs_unit) as avg_cogs,
            AVG(profit_unit) as avg_profit,
            SUM(quantity) as total_qty,
            SUM(line_net_rev) as total_revenue,
            SUM(profit_line) as total_profit
        FROM fact_sales
        WHERE order_date >= :cutoff_date
        GROUP BY sku_key, store_code
    """

    cursor = conn.execute(query, {"cutoff_date": cutoff_date})
    result = {}

    for row in cursor.fetchall():
        sku_key, store_code = row[0], row[1]
        result[(sku_key, store_code)] = {
            "avg_price": row[2],
            "avg_cogs": row[3],
            "avg_profit": row[4],
            "total_qty": row[5],
            "total_revenue": row[6],
            "total_profit": row[7],
        }

    return result


def get_inventory_by_sku(conn, snapshot_date: str = None) -> dict:
    """
    Get current inventory levels for each SKU from fact_inventory_snapshot_size.

    Args:
        conn: Database connection
        snapshot_date: Optional date to use (default: latest available)

    Returns dict: {(sku_key, store_code): {current_stock, inbound_stock, total_stock}}
    """
    # Get latest snapshot date if not specified
    if snapshot_date is None:
        result = conn.execute(
            "SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size"
        ).fetchone()
        snapshot_date = result[0] if result and result[0] else None

    if not snapshot_date:
        return {}

    # Aggregate size-level inventory to style-level
    # Note: inventory file doesn't have store_code, so we use 'ALL'
    query = """
        SELECT
            sku_key,
            SUM(current_stock) as current_stock,
            SUM(inbound_stock) as inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = :snapshot_date
        GROUP BY sku_key
    """

    cursor = conn.execute(query, {"snapshot_date": snapshot_date})
    result = {}

    for row in cursor.fetchall():
        sku_key = row[0]
        current_stock = row[1] or 0
        inbound_stock = row[2] or 0
        # Use 'ALL' as store_code since inventory is aggregated
        result[(sku_key, "ALL")] = {
            "current_stock": current_stock,
            "inbound_stock": inbound_stock,
            "total_stock": current_stock + inbound_stock,
        }

    return result


def compute_sku_metrics(
    d30_data: dict,
    economics_data: dict,
    inventory_data: dict,
) -> list[dict]:
    """
    Compute all metrics for each SKU.

    Returns list of metric dicts, one per (sku_key, store_code).
    """
    results = []

    # Get all unique SKU/store combinations
    all_keys = set(d30_data.keys()) | set(economics_data.keys())

    for key in all_keys:
        sku_key, store_code = key

        # Get D30 data
        d30_info = d30_data.get(key, {"d30": 0, "total_units": 0, "days_with_sales": 0})
        d30 = d30_info["d30"]

        # Get economics
        econ = economics_data.get(key, {})
        avg_cogs = econ.get("avg_cogs", 0) or 0
        avg_profit = econ.get("avg_profit", 0) or 0
        avg_price = econ.get("avg_price", 0) or 0

        # Skip SKUs with no sales or invalid economics
        if d30 <= 0 or avg_cogs <= 0:
            continue

        # Compute inventory metrics
        metrics = calc_all_metrics(d30, avg_cogs, avg_profit)

        # Get inventory levels (default to 0 if not available)
        # Inventory may be keyed by (sku_key, 'ALL') if aggregated across stores
        inv = inventory_data.get(key, {})
        if not inv:
            inv = inventory_data.get((sku_key, "ALL"), {})
        current_stock = inv.get("current_stock", 0)
        inbound_stock = inv.get("inbound_stock", 0)
        total_stock = current_stock + inbound_stock

        # Calculate status and suggested order
        status = calc_status(current_stock, total_stock, metrics["rop"])
        suggested_qty = calc_suggested_order_qty(
            d30, current_stock, inbound_stock, ss_total=metrics["ss_total"]
        )

        results.append({
            "sku_key": sku_key,
            "store_code": store_code,
            "d30": round(d30, 3),
            "sigma": round(metrics["sigma"], 3),
            "ss_demand": round(metrics["ss_demand"], 1),
            "ss_floor": round(metrics["ss_floor"], 1),
            "ss_mix": round(metrics["ss_mix"], 1),
            "ss_total": round(metrics["ss_total"], 1),
            "rop": round(metrics["rop"], 1),
            "target_stock": round(metrics["target_stock"], 1),
            "avg_price": round(avg_price, 0),
            "avg_cogs": round(avg_cogs, 2),
            "avg_profit": round(avg_profit, 2),
            "k_avg": round(metrics["k_avg"], 0),
            "roic_monthly": round(metrics["roic_monthly"], 2),
            "current_stock": current_stock,
            "inbound_stock": inbound_stock,
            "total_stock": total_stock,
            "status": status,
            "suggested_order_qty": suggested_qty,
            "days_with_sales": d30_info["days_with_sales"],
            "total_units_30d": d30_info["total_units"],
        })

    # Sort by status priority, then ROIC descending
    from core.calc.status import get_status_priority
    results.sort(key=lambda x: (get_status_priority(x["status"]), -x["roic_monthly"]))

    return results


def save_to_csv(metrics: list[dict], filepath: str) -> int:
    """Save metrics to CSV file."""
    if not metrics:
        return 0

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=metrics[0].keys())
        writer.writeheader()
        writer.writerows(metrics)

    return len(metrics)


def create_metrics_table(conn):
    """Create fact_sku_metrics table if not exists."""
    sql = """
        CREATE TABLE IF NOT EXISTS fact_sku_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            computed_at TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            store_code TEXT NOT NULL,
            d30 REAL NOT NULL,
            sigma REAL NOT NULL,
            ss_demand REAL NOT NULL,
            ss_floor REAL NOT NULL,
            ss_mix REAL NOT NULL,
            ss_total REAL NOT NULL,
            rop REAL NOT NULL,
            target_stock REAL NOT NULL,
            avg_price REAL,
            avg_cogs REAL,
            avg_profit REAL,
            k_avg REAL,
            roic_monthly REAL,
            current_stock INTEGER DEFAULT 0,
            inbound_stock INTEGER DEFAULT 0,
            total_stock INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            suggested_order_qty INTEGER DEFAULT 0,
            days_with_sales INTEGER,
            total_units_30d INTEGER,
            UNIQUE(computed_at, sku_key, store_code)
        )
    """
    conn.execute(sql)
    conn.commit()


def save_to_db(conn, metrics: list[dict], computed_at: str) -> int:
    """Save metrics to fact_sku_metrics table."""
    if not metrics:
        return 0

    create_metrics_table(conn)

    sql = """
        INSERT OR REPLACE INTO fact_sku_metrics (
            computed_at, sku_key, store_code, d30, sigma,
            ss_demand, ss_floor, ss_mix, ss_total, rop, target_stock,
            avg_price, avg_cogs, avg_profit, k_avg, roic_monthly,
            current_stock, inbound_stock, total_stock,
            status, suggested_order_qty, days_with_sales, total_units_30d
        ) VALUES (
            :computed_at, :sku_key, :store_code, :d30, :sigma,
            :ss_demand, :ss_floor, :ss_mix, :ss_total, :rop, :target_stock,
            :avg_price, :avg_cogs, :avg_profit, :k_avg, :roic_monthly,
            :current_stock, :inbound_stock, :total_stock,
            :status, :suggested_order_qty, :days_with_sales, :total_units_30d
        )
    """

    for m in metrics:
        m["computed_at"] = computed_at

    conn.executemany(sql, metrics)
    conn.commit()

    return len(metrics)


def run_metrics(
    days: int = 30,
    csv_path: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Main function to compute and save SKU metrics.

    Args:
        days: Number of days for D30 calculation
        csv_path: Optional path to export CSV
        dry_run: If True, compute but don't save
        verbose: Print progress

    Returns:
        Dict with stats
    """
    with get_db() as conn:
        computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if verbose:
            print(f"Computing metrics for last {days} days...")

        # Gather data
        d30_data = get_d30_by_sku(conn, days)
        if verbose:
            print(f"  Found {len(d30_data)} SKU/store combinations with sales")

        economics_data = get_avg_economics_by_sku(conn, days)
        if verbose:
            print(f"  Found {len(economics_data)} SKU/store economics records")

        inventory_data = get_inventory_by_sku(conn)
        if verbose:
            print(f"  Found {len(inventory_data)} inventory records")

        # Compute metrics
        if verbose:
            print("Computing metrics...")
        metrics = compute_sku_metrics(d30_data, economics_data, inventory_data)
        if verbose:
            print(f"  Computed metrics for {len(metrics)} SKUs")

        # Show sample
        if verbose and metrics:
            print("\nTop 5 SKUs by ROIC:")
            for m in sorted(metrics, key=lambda x: -x["roic_monthly"])[:5]:
                print(f"  {m['sku_key']}: D30={m['d30']:.2f}, ROIC={m['roic_monthly']:.1f}%, Status={m['status']}")

            print("\nStatus summary:")
            status_counts = {}
            for m in metrics:
                status_counts[m["status"]] = status_counts.get(m["status"], 0) + 1
            for status, count in sorted(status_counts.items()):
                print(f"  {status}: {count}")

        # Save results
        saved_count = 0
        if not dry_run:
            if csv_path:
                saved_count = save_to_csv(metrics, csv_path)
                if verbose:
                    print(f"\nExported {saved_count} records to {csv_path}")
            else:
                saved_count = save_to_db(conn, metrics, computed_at)
                if verbose:
                    print(f"\nSaved {saved_count} records to fact_sku_metrics")

        return {
            "computed_at": computed_at,
            "sku_count": len(metrics),
            "saved_count": saved_count,
            "metrics": metrics if dry_run else None,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Compute inventory metrics for all active SKUs"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days for D30 calculation (default: 30)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Export to CSV file instead of DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute but don't save",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Run SKU Metrics")
    print("=" * 60)

    result = run_metrics(
        days=args.days,
        csv_path=args.csv,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 60)
    print(f"Completed at {result['computed_at']}")
    print(f"Total SKUs processed: {result['sku_count']}")
    if not args.dry_run:
        print(f"Records saved: {result['saved_count']}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
