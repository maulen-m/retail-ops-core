#!/usr/bin/env python3
"""
TASK-038: Export Forecast Accuracy Trends

Generates JSON export of accuracy metrics for dashboards.

Usage:
    python scripts/export_accuracy_trends.py [--days 30]

Output:
    exports/accuracy_trends.json
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


def get_overall_mape(db_path: str, days: int = 30) -> float:
    """Get average MAPE across all SKUs."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT AVG(mape)
        FROM fact_forecast_accuracy
        WHERE accuracy_date >= ?
    """, (cutoff,))

    result = cursor.fetchone()
    conn.close()

    return round(result[0], 2) if result and result[0] else None


def get_mape_by_sku(db_path: str, days: int = 30) -> list[dict]:
    """Get MAPE trends per SKU."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Get latest MAPE per SKU
    cursor.execute("""
        SELECT
            sku_key,
            mape,
            bias
        FROM fact_forecast_accuracy
        WHERE accuracy_date = (SELECT MAX(accuracy_date) FROM fact_forecast_accuracy)
        ORDER BY mape
    """)

    results = []
    for row in cursor.fetchall():
        sku_key, mape, bias = row

        # Determine trend by comparing to previous period
        cursor.execute("""
            SELECT mape
            FROM fact_forecast_accuracy
            WHERE sku_key = ?
            AND accuracy_date < (SELECT MAX(accuracy_date) FROM fact_forecast_accuracy)
            ORDER BY accuracy_date DESC
            LIMIT 1
        """, (sku_key,))

        prev = cursor.fetchone()
        if prev and prev[0]:
            if mape < prev[0] * 0.9:
                trend = 'improving'
            elif mape > prev[0] * 1.1:
                trend = 'degrading'
            else:
                trend = 'stable'
        else:
            trend = 'new'

        results.append({
            'sku_key': sku_key,
            'mape': round(mape, 1) if mape else None,
            'bias': round(bias, 1) if bias else None,
            'trend': trend
        })

    conn.close()
    return results


def get_mape_by_horizon(db_path: str) -> dict:
    """Get average MAPE per forecast horizon."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT horizon_days, AVG(mape)
        FROM fact_forecast_accuracy
        WHERE accuracy_date = (SELECT MAX(accuracy_date) FROM fact_forecast_accuracy)
        GROUP BY horizon_days
    """)

    result = {}
    for row in cursor.fetchall():
        horizon, mape = row
        result[str(horizon)] = round(mape, 1) if mape else None

    conn.close()
    return result


def get_accuracy_history(db_path: str, days: int = 30) -> list[dict]:
    """Get daily MAPE history."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT accuracy_date, AVG(mape), AVG(bias)
        FROM fact_forecast_accuracy
        WHERE accuracy_date >= ?
        GROUP BY accuracy_date
        ORDER BY accuracy_date
    """, (cutoff,))

    results = []
    for row in cursor.fetchall():
        results.append({
            'date': row[0],
            'mape': round(row[1], 1) if row[1] else None,
            'bias': round(row[2], 1) if row[2] else None
        })

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description='Export accuracy trends')
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Days of history (default: 30)'
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

    print(f"=== Export Accuracy Trends ===")
    print(f"Database: {db_path}")
    print()

    # Gather data
    overall_mape = get_overall_mape(str(db_path), args.days)
    mape_by_sku = get_mape_by_sku(str(db_path), args.days)
    mape_by_horizon = get_mape_by_horizon(str(db_path))
    history = get_accuracy_history(str(db_path), args.days)

    # Build export
    export = {
        'report_date': date.today().isoformat(),
        'overall_mape': overall_mape,
        'mape_by_sku': mape_by_sku,
        'mape_by_horizon': mape_by_horizon,
        'history': history
    }

    # Write JSON
    exports_dir = project_root / 'exports'
    exports_dir.mkdir(parents=True, exist_ok=True)
    output_path = exports_dir / 'accuracy_trends.json'

    with open(output_path, 'w') as f:
        json.dump(export, f, indent=2)

    print(f"Export saved: {output_path}")
    print(f"\nSummary:")
    print(f"  Overall MAPE: {overall_mape}%")
    print(f"  SKUs tracked: {len(mape_by_sku)}")
    print(f"  Horizons: {list(mape_by_horizon.keys())}")
    print(f"  History days: {len(history)}")

    return 0


if __name__ == '__main__':
    exit(main())
