#!/usr/bin/env python3
"""
TASK-035: Stockout Cost Report

Generates report of stockout costs and patterns.
Sends weekly Telegram summary.

Usage:
    python scripts/report_stockout_costs.py [--days 90] [--send-summary]

Output:
    reports/stockout_costs_YYYY-MM-DD.csv
"""

import argparse
import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_stockout_summary(db_path: str, days: int = 90) -> list[dict]:
    """
    Get stockout summary per SKU.

    Args:
        db_path: Path to database
        days: Lookback period in days

    Returns:
        List of dicts with stockout stats per SKU
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT
            sku_key,
            COUNT(*) as stockout_events,
            SUM(days_out_of_stock) as total_stockout_days,
            SUM(estimated_lost_units) as total_lost_units,
            SUM(estimated_lost_profit) as total_lost_profit_kzt,
            AVG(CASE
                WHEN resolved_at IS NOT NULL THEN
                    julianday(resolved_at) - julianday(detected_at)
                ELSE NULL
            END) as avg_days_to_resolve,
            COUNT(*) * 30.0 / ? as stockout_frequency_per_month
        FROM fact_stockout_events
        WHERE event_date >= ?
        GROUP BY sku_key
        ORDER BY total_lost_profit_kzt DESC
    """, (days, cutoff))

    results = []
    for row in cursor.fetchall():
        results.append({
            'sku_key': row[0],
            'stockout_events': row[1],
            'total_stockout_days': row[2] or 0,
            'total_lost_units': round(row[3] or 0, 1),
            'total_lost_profit_kzt': round(row[4] or 0, 0),
            'avg_days_to_resolve': round(row[5], 1) if row[5] else None,
            'stockout_frequency': round(row[6], 2)
        })

    conn.close()
    return results


def get_overall_stats(db_path: str, days: int = 90) -> dict:
    """
    Get overall stockout statistics.

    Args:
        db_path: Path to database
        days: Lookback period in days

    Returns:
        Dict with overall stats
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT
            COUNT(*) as total_events,
            SUM(days_out_of_stock) as total_days,
            SUM(estimated_lost_units) as total_units,
            SUM(estimated_lost_profit) as total_profit,
            COUNT(DISTINCT sku_key) as affected_skus
        FROM fact_stockout_events
        WHERE event_date >= ?
    """, (cutoff,))

    row = cursor.fetchone()
    conn.close()

    return {
        'total_events': row[0] or 0,
        'total_stockout_days': row[1] or 0,
        'total_lost_units': round(row[2] or 0, 1),
        'total_lost_profit_kzt': round(row[3] or 0, 0),
        'affected_skus': row[4] or 0
    }


def generate_report(results: list[dict], output_path: Path) -> None:
    """
    Generate CSV stockout cost report.

    Args:
        results: List of stockout summary dicts
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'sku_key',
            'total_stockout_days',
            'total_lost_units',
            'total_lost_profit_kzt',
            'avg_days_to_resolve',
            'stockout_frequency'
        ])

        for result in results:
            writer.writerow([
                result['sku_key'],
                result['total_stockout_days'],
                result['total_lost_units'],
                result['total_lost_profit_kzt'],
                result['avg_days_to_resolve'] or '',
                result['stockout_frequency']
            ])


def send_weekly_summary(overall: dict, top_offenders: list[dict]) -> bool:
    """
    Send weekly Telegram summary.

    Args:
        overall: Overall stats dict
        top_offenders: Top SKUs by lost profit

    Returns:
        True if sent successfully
    """
    try:
        from core.alerts.telegram import send_message

        message = (
            f"<b>Weekly Stockout Report</b>\n\n"
            f"Total Events: {overall['total_events']}\n"
            f"Total Stockout Days: {overall['total_stockout_days']}\n"
            f"Est. Lost Units: {overall['total_lost_units']:.1f}\n"
            f"Est. Lost Profit: {overall['total_lost_profit_kzt']:,.0f} KZT\n"
            f"Affected SKUs: {overall['affected_skus']}\n\n"
        )

        if top_offenders:
            message += "<b>Top Offenders:</b>\n"
            for sku in top_offenders[:3]:
                message += (
                    f"• {sku['sku_key']}: "
                    f"{sku['total_stockout_days']} days, "
                    f"{sku['total_lost_profit_kzt']:,.0f} KZT lost\n"
                )

        send_message(message)
        return True

    except Exception as e:
        print(f"Failed to send summary: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate stockout cost report')
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Lookback period in days (default: 90)'
    )
    parser.add_argument(
        '--send-summary',
        action='store_true',
        help='Send Telegram weekly summary'
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

    print(f"=== Stockout Cost Report ===")
    print(f"Database: {db_path}")
    print(f"Lookback: {args.days} days")
    print()

    # Get data
    results = get_stockout_summary(str(db_path), args.days)
    overall = get_overall_stats(str(db_path), args.days)

    # Generate report
    report_date = date.today().isoformat()
    report_path = project_root / 'reports' / f'stockout_costs_{report_date}.csv'
    generate_report(results, report_path)
    print(f"Report saved: {report_path}")
    print()

    # Print summary
    print(f"=== Summary (Last {args.days} Days) ===")
    print(f"Total stockout events: {overall['total_events']}")
    print(f"Total stockout days: {overall['total_stockout_days']}")
    print(f"Est. lost units: {overall['total_lost_units']}")
    print(f"Est. lost profit: {overall['total_lost_profit_kzt']:,.0f} KZT")
    print(f"SKUs affected: {overall['affected_skus']}")

    if results:
        print(f"\nTop SKUs by Lost Profit:")
        for r in results[:5]:
            print(f"  {r['sku_key']}: {r['total_stockout_days']} days, "
                  f"{r['total_lost_profit_kzt']:,.0f} KZT")

    # Send summary if requested
    if args.send_summary:
        if send_weekly_summary(overall, results):
            print(f"\nTelegram summary sent")

    print(f"\nReport complete.")
    return 0


if __name__ == '__main__':
    exit(main())
