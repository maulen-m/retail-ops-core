#!/usr/bin/env python3
"""
TASK-034: Stockout Detection Script

Daily script to identify and log stockout events.
Estimates lost sales based on D30/forecast.

Usage:
    python scripts/detect_stockouts.py [--dry-run] [--no-alert]
"""

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_active_skus_with_history(db_path: str, min_sales_days: int = 7) -> list[dict]:
    """
    Get active SKUs that have recent sales history.

    Args:
        db_path: Path to database
        min_sales_days: Minimum days with sales in last 30 days

    Returns:
        List of dicts with sku_key, d30, profit_unit
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get SKUs with sales in last 30 days
    cursor.execute("""
        SELECT
            s.sku_key,
            COUNT(DISTINCT d.sale_date) as days_with_sales,
            COALESCE(SUM(d.units), 0) / 30.0 as d30,
            COALESCE(AVG(f.profit_unit), 0) as avg_profit
        FROM dim_sku s
        LEFT JOIN fact_sales_daily d ON s.sku_key = d.sku_key
            AND d.sale_date >= date('now', '-30 days')
        LEFT JOIN fact_sales f ON s.sku_key = f.sku_key
        WHERE s.active_flag = 1
        GROUP BY s.sku_key
        HAVING days_with_sales >= ?
    """, (min_sales_days,))

    skus = []
    for row in cursor.fetchall():
        skus.append({
            'sku_key': row[0],
            'days_with_sales': row[1],
            'd30': float(row[2]) if row[2] else 0.0,
            'profit_unit': float(row[3]) if row[3] else 0.0
        })

    conn.close()
    return skus


def get_current_stock(db_path: str, sku_key: str) -> int:
    """
    Get current stock for a SKU from latest snapshot.

    Args:
        db_path: Path to database
        sku_key: SKU to check

    Returns:
        Current stock (0 if not found)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT SUM(current_stock)
        FROM fact_inventory_snapshot_size
        WHERE sku_key = ?
        AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size
        )
    """, (sku_key,))

    result = cursor.fetchone()
    conn.close()

    return int(result[0]) if result[0] else 0


def get_existing_stockout(db_path: str, sku_key: str, store_code: str) -> dict:
    """
    Check for existing unresolved stockout event.

    Args:
        db_path: Path to database
        sku_key: SKU to check
        store_code: Store code

    Returns:
        Existing event dict or None
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT event_id, event_date, days_out_of_stock
        FROM fact_stockout_events
        WHERE sku_key = ? AND store_code = ? AND resolved_at IS NULL
        ORDER BY event_date DESC
        LIMIT 1
    """, (sku_key, store_code))

    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            'event_id': result[0],
            'event_date': result[1],
            'days_out_of_stock': result[2]
        }
    return None


def create_stockout_event(
    db_path: str,
    sku_key: str,
    store_code: str,
    d30: float,
    profit_unit: float
) -> int:
    """
    Create new stockout event.

    Args:
        db_path: Path to database
        sku_key: SKU with stockout
        store_code: Store code
        d30: Daily demand estimate
        profit_unit: Profit per unit

    Returns:
        New event_id
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    estimated_lost_units = d30
    estimated_lost_profit = d30 * profit_unit

    cursor.execute("""
        INSERT INTO fact_stockout_events (
            event_date, sku_key, store_code, days_out_of_stock,
            estimated_lost_units, estimated_lost_profit
        ) VALUES (?, ?, ?, 1, ?, ?)
    """, (
        date.today().isoformat(),
        sku_key,
        store_code,
        estimated_lost_units,
        estimated_lost_profit
    ))

    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return event_id


def update_stockout_event(
    db_path: str,
    event_id: int,
    d30: float,
    profit_unit: float
) -> None:
    """
    Update existing stockout event (increment days).

    Args:
        db_path: Path to database
        event_id: Event to update
        d30: Daily demand estimate
        profit_unit: Profit per unit
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE fact_stockout_events
        SET days_out_of_stock = days_out_of_stock + 1,
            estimated_lost_units = estimated_lost_units + ?,
            estimated_lost_profit = estimated_lost_profit + ?
        WHERE event_id = ?
    """, (d30, d30 * profit_unit, event_id))

    conn.commit()
    conn.close()


def resolve_stockout_event(db_path: str, event_id: int) -> None:
    """
    Mark stockout event as resolved.

    Args:
        db_path: Path to database
        event_id: Event to resolve
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE fact_stockout_events
        SET resolved_at = datetime('now')
        WHERE event_id = ?
    """, (event_id,))

    conn.commit()
    conn.close()


def detect_stockouts(db_path: str, dry_run: bool = False) -> dict:
    """
    Main stockout detection logic.

    Args:
        db_path: Path to database
        dry_run: If True, don't write to database

    Returns:
        Dict with detection results
    """
    store_code = 'ALL'  # Aggregate across stores

    # Get active SKUs with sales history
    skus = get_active_skus_with_history(db_path, min_sales_days=3)

    new_stockouts = []
    continued_stockouts = []
    resolved_stockouts = []

    for sku in skus:
        sku_key = sku['sku_key']
        d30 = sku['d30']
        profit_unit = sku['profit_unit']

        # Get current stock
        current_stock = get_current_stock(db_path, sku_key)

        # Check for existing stockout
        existing = get_existing_stockout(db_path, sku_key, store_code)

        if current_stock == 0:
            # Stockout condition
            if existing:
                # Continue existing stockout
                if not dry_run:
                    update_stockout_event(db_path, existing['event_id'], d30, profit_unit)
                continued_stockouts.append({
                    'sku_key': sku_key,
                    'event_id': existing['event_id'],
                    'days': existing['days_out_of_stock'] + 1,
                    'lost_profit_daily': d30 * profit_unit
                })
            else:
                # New stockout
                if not dry_run:
                    event_id = create_stockout_event(
                        db_path, sku_key, store_code, d30, profit_unit
                    )
                else:
                    event_id = -1
                new_stockouts.append({
                    'sku_key': sku_key,
                    'event_id': event_id,
                    'd30': d30,
                    'lost_profit_daily': d30 * profit_unit
                })
        else:
            # Not a stockout
            if existing:
                # Resolve existing stockout
                if not dry_run:
                    resolve_stockout_event(db_path, existing['event_id'])
                resolved_stockouts.append({
                    'sku_key': sku_key,
                    'event_id': existing['event_id'],
                    'days': existing['days_out_of_stock']
                })

    return {
        'new_stockouts': new_stockouts,
        'continued_stockouts': continued_stockouts,
        'resolved_stockouts': resolved_stockouts,
        'total_skus_checked': len(skus)
    }


def send_stockout_alerts(stockouts: list[dict], db_path: str) -> None:
    """
    Send Telegram alerts for new stockouts.

    Args:
        stockouts: List of new stockout dicts
        db_path: Path to database for config
    """
    if not stockouts:
        return

    try:
        from core.alerts.telegram import send_message

        for stockout in stockouts[:5]:  # Limit to 5 alerts
            message = (
                f"<b>STOCKOUT DETECTED</b>\n\n"
                f"SKU: <b>{stockout['sku_key']}</b>\n"
                f"D30: {stockout['d30']:.1f} units/day\n"
                f"Est. Lost Profit: {stockout['lost_profit_daily']:,.0f} KZT/day\n\n"
                f"Action: Check inbound orders or initiate PO"
            )
            send_message(message)

    except Exception as e:
        print(f"Failed to send alerts: {e}")


def main():
    parser = argparse.ArgumentParser(description='Detect stockout events')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing to database'
    )
    parser.add_argument(
        '--no-alert',
        action='store_true',
        help='Disable Telegram alerts'
    )
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

    print(f"=== Stockout Detection ===")
    print(f"Database: {db_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    # Run detection
    results = detect_stockouts(str(db_path), dry_run=args.dry_run)

    print(f"SKUs checked: {results['total_skus_checked']}")
    print(f"New stockouts: {len(results['new_stockouts'])}")
    print(f"Continued stockouts: {len(results['continued_stockouts'])}")
    print(f"Resolved stockouts: {len(results['resolved_stockouts'])}")

    # Show details
    if results['new_stockouts']:
        print(f"\nNew Stockouts:")
        for s in results['new_stockouts']:
            print(f"  {s['sku_key']}: D30={s['d30']:.1f}, Lost={s['lost_profit_daily']:,.0f} KZT/day")

    if results['continued_stockouts']:
        print(f"\nContinued Stockouts:")
        for s in results['continued_stockouts']:
            print(f"  {s['sku_key']}: Day {s['days']}, Lost={s['lost_profit_daily']:,.0f} KZT/day")

    if results['resolved_stockouts']:
        print(f"\nResolved Stockouts:")
        for s in results['resolved_stockouts']:
            print(f"  {s['sku_key']}: Was out for {s['days']} days")

    # Send alerts
    if not args.no_alert and not args.dry_run:
        send_stockout_alerts(results['new_stockouts'], str(db_path))

    print(f"\nStockout detection complete.")
    return 0


if __name__ == '__main__':
    exit(main())
