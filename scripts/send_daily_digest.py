#!/usr/bin/env python3
"""
TASK-050: Daily Digest Telegram Notification

Sends morning digest with key metrics and alerts.
Recommended cron: 0 8 * * * python scripts/send_daily_digest.py

Usage:
    python scripts/send_daily_digest.py [--dry-run]
"""

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_yesterday_sales(db_path: str) -> dict:
    """Get yesterday's sales summary."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    cursor.execute("""
        SELECT
            COUNT(DISTINCT order_id) as orders,
            SUM(line_net_rev) as revenue,
            SUM(quantity) as units
        FROM fact_sales
        WHERE order_date = ?
    """, (yesterday,))

    row = cursor.fetchone()
    conn.close()

    return {
        'date': yesterday,
        'orders': row[0] or 0,
        'revenue': round(row[1] or 0, 0),
        'units': row[2] or 0
    }


def get_top_sku_yesterday(db_path: str) -> dict:
    """Get top selling SKU yesterday."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    cursor.execute("""
        SELECT sku_key, SUM(quantity) as units
        FROM fact_sales
        WHERE order_date = ?
        GROUP BY sku_key
        ORDER BY units DESC
        LIMIT 1
    """, (yesterday,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'sku_key': row[0],
            'units': row[1]
        }
    return None


def get_alerts(db_path: str) -> list[dict]:
    """Get current active alerts."""
    alerts = []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Reorder alerts
    cursor.execute("""
        SELECT sku_key, current_stock, rop
        FROM fact_sku_metrics
        WHERE status = 'REORDER'
        LIMIT 3
    """)

    for row in cursor.fetchall():
        alerts.append({
            'type': 'REORDER',
            'sku_key': row[0],
            'details': f"stock: {row[1]}, ROP: {row[2]:.0f}"
        })

    # Low ROIC alerts
    cursor.execute("""
        SELECT sku_key, roic_monthly
        FROM fact_sku_metrics
        WHERE roic_monthly < 10
        AND roic_monthly IS NOT NULL
        LIMIT 2
    """)

    for row in cursor.fetchall():
        alerts.append({
            'type': 'LOW_ROIC',
            'sku_key': row[0],
            'details': f"ROIC: {row[1]:.1f}%"
        })

    conn.close()
    return alerts


def get_tomorrow_forecast(db_path: str) -> dict:
    """Get forecast for tomorrow."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    today = date.today().isoformat()

    cursor.execute("""
        SELECT SUM(predicted_units) as total_forecast
        FROM fact_demand_forecast
        WHERE target_date = ?
        AND forecast_date = (SELECT MAX(forecast_date) FROM fact_demand_forecast)
    """, (tomorrow,))

    row = cursor.fetchone()
    forecast = row[0] if row and row[0] else 0

    # Get DOW adjustment hint
    tomorrow_dow = (date.today() + timedelta(days=1)).weekday()
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    is_weekend = tomorrow_dow >= 5

    conn.close()

    return {
        'date': tomorrow,
        'day': dow_names[tomorrow_dow],
        'forecast_units': round(forecast, 0),
        'is_weekend': is_weekend,
        'dow_note': '+15-20% weekend traffic expected' if is_weekend else ''
    }


def format_digest_message(
    sales: dict,
    top_sku: dict,
    alerts: list[dict],
    forecast: dict
) -> str:
    """Format the daily digest message."""
    msg = f"<b>Daily Digest - {date.today().strftime('%b %d')}</b>\n\n"

    # Yesterday's sales
    msg += f"<b>Sales ({sales['date']})</b>\n"
    msg += f"Orders: {sales['orders']}\n"
    msg += f"Revenue: {sales['revenue']:,.0f} KZT\n"

    if top_sku:
        msg += f"Top SKU: {top_sku['sku_key']} ({top_sku['units']} units)\n"

    msg += "\n"

    # Alerts
    if alerts:
        msg += "<b>Alerts</b>\n"
        for alert in alerts:
            emoji = "" if alert['type'] == 'REORDER' else ""
            msg += f"{emoji} {alert['type']}: {alert['sku_key']} ({alert['details']})\n"
        msg += "\n"

    # Tomorrow forecast
    msg += f"<b>Forecast ({forecast['day']} {forecast['date']})</b>\n"
    msg += f"Expected: ~{forecast['forecast_units']:.0f} units\n"
    if forecast['dow_note']:
        msg += f"Note: {forecast['dow_note']}\n"

    return msg


def send_digest(message: str, dry_run: bool = False) -> bool:
    """Send the digest via Telegram."""
    if dry_run:
        print("DRY RUN - Would send:")
        print("-" * 40)
        # Convert HTML to plain text for display
        plain = message.replace('<b>', '').replace('</b>', '')
        print(plain)
        print("-" * 40)
        return True

    try:
        from core.alerts.telegram import send_message
        send_message(message)
        return True
    except Exception as e:
        print(f"Failed to send digest: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Send daily digest')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print message without sending'
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

    print(f"=== Daily Digest ===")
    print(f"Database: {db_path}")
    print()

    # Gather data
    sales = get_yesterday_sales(str(db_path))
    top_sku = get_top_sku_yesterday(str(db_path))
    alerts = get_alerts(str(db_path))
    forecast = get_tomorrow_forecast(str(db_path))

    # Format message
    message = format_digest_message(sales, top_sku, alerts, forecast)

    # Send
    if send_digest(message, args.dry_run):
        print("Digest sent successfully")
        return 0
    else:
        print("Failed to send digest")
        return 1


if __name__ == '__main__':
    exit(main())
