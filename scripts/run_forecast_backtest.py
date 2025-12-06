#!/usr/bin/env python3
"""
TASK-037: Forecast Backtest Runner

Weekly backtest to measure forecast accuracy using walk-forward validation.
Stores results in fact_forecast_accuracy and generates reports.

Usage:
    python scripts/run_forecast_backtest.py --test-days 30 --horizon 7
"""

import argparse
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.calc.forecast_accuracy import (
    backtest_forecast,
    backtest_all_skus,
    get_accuracy_grade
)


def store_accuracy_results(
    db_path: str,
    results: list[dict],
    horizon: int,
    model_version: str = 'v1.0'
) -> int:
    """
    Store backtest results in fact_forecast_accuracy.

    Args:
        db_path: Path to database
        results: List of backtest result dicts
        horizon: Forecast horizon used
        model_version: Model version identifier

    Returns:
        Number of rows inserted
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    accuracy_date = date.today().isoformat()
    store_code = 'ALL'
    inserted = 0

    for result in results:
        if result.get('mape') is None:
            continue

        cursor.execute("""
            INSERT OR REPLACE INTO fact_forecast_accuracy (
                accuracy_date, sku_key, store_code, horizon_days,
                mape, bias, sample_size, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            accuracy_date,
            result['sku_key'],
            store_code,
            horizon,
            result['mape'],
            result['bias'],
            result['sample_size'],
            model_version
        ))
        inserted += 1

    conn.commit()
    conn.close()

    return inserted


def generate_accuracy_report(
    results: list[dict],
    output_path: Path,
    horizon: int
) -> None:
    """
    Generate CSV accuracy report.

    Args:
        results: List of backtest result dicts
        output_path: Path to write CSV
        horizon: Forecast horizon used
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'sku_key', 'horizon_days', 'mape', 'wmape', 'bias',
            'mae', 'sample_size', 'grade'
        ])

        for result in results:
            if result.get('mape') is None:
                continue

            writer.writerow([
                result['sku_key'],
                horizon,
                result['mape'],
                result.get('wmape', ''),
                result['bias'],
                result.get('mae', ''),
                result['sample_size'],
                get_accuracy_grade(result['mape'])
            ])


def calculate_overall_metrics(results: list[dict]) -> dict:
    """
    Calculate overall accuracy metrics.

    Args:
        results: List of backtest result dicts

    Returns:
        Dict with overall MAPE, bias, etc.
    """
    valid_results = [r for r in results if r.get('mape') is not None]

    if not valid_results:
        return {
            'overall_mape': None,
            'overall_bias': None,
            'skus_tested': 0,
            'grade': 'N/A'
        }

    total_mape = sum(r['mape'] for r in valid_results)
    total_bias = sum(r['bias'] for r in valid_results)
    n = len(valid_results)

    avg_mape = total_mape / n
    avg_bias = total_bias / n

    return {
        'overall_mape': round(avg_mape, 2),
        'overall_bias': round(avg_bias, 2),
        'skus_tested': n,
        'grade': get_accuracy_grade(avg_mape)
    }


def send_alert_if_degraded(
    overall_mape: float,
    threshold: float = 25.0,
    db_path: str = None
) -> bool:
    """
    Send Telegram alert if accuracy degrades beyond threshold.

    Args:
        overall_mape: Overall MAPE value
        threshold: Alert threshold (default: 25%)
        db_path: Path to database for alert config

    Returns:
        True if alert was sent
    """
    if overall_mape is None or overall_mape <= threshold:
        return False

    try:
        from core.alerts.telegram import send_message

        message = (
            f"<b>Forecast Accuracy Alert</b>\n\n"
            f"MAPE: <b>{overall_mape}%</b> (target: &lt;20%)\n"
            f"Status: <b>DEGRADED</b>\n\n"
            f"Action: Review forecast model parameters"
        )

        send_message(message)
        return True
    except Exception as e:
        print(f"Failed to send alert: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run forecast backtest')
    parser.add_argument(
        '--test-days',
        type=int,
        default=30,
        help='Number of days to test (default: 30)'
    )
    parser.add_argument(
        '--horizon',
        type=int,
        default=7,
        help='Forecast horizon in days (default: 7)'
    )
    parser.add_argument(
        '--sku',
        help='Run backtest for single SKU only'
    )
    parser.add_argument(
        '--min-days',
        type=int,
        default=60,
        help='Minimum sales days required (default: 60)'
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

    print(f"=== Forecast Backtest ===")
    print(f"Database: {db_path}")
    print(f"Test days: {args.test_days}")
    print(f"Horizon: {args.horizon} days")
    print()

    # Run backtest
    if args.sku:
        print(f"Running backtest for: {args.sku}")
        result = backtest_forecast(
            sku_key=args.sku,
            db_path=str(db_path),
            test_days=args.test_days,
            horizon=args.horizon
        )
        result['sku_key'] = args.sku
        results = [result]
    else:
        print(f"Running backtest for all SKUs with >= {args.min_days} days of sales...")
        results = backtest_all_skus(
            db_path=str(db_path),
            test_days=args.test_days,
            horizon=args.horizon,
            min_sales_days=args.min_days
        )

    # Calculate overall metrics
    overall = calculate_overall_metrics(results)

    print(f"\n=== Results ===")
    print(f"SKUs tested: {overall['skus_tested']}")
    print(f"Overall MAPE: {overall['overall_mape']}%")
    print(f"Overall Bias: {overall['overall_bias']}%")
    print(f"Grade: {overall['grade']}")

    # Store results in database
    if results:
        inserted = store_accuracy_results(
            str(db_path),
            results,
            args.horizon
        )
        print(f"\nStored {inserted} accuracy records in fact_forecast_accuracy")

        # Generate report
        report_date = date.today().isoformat()
        report_path = project_root / 'reports' / f'forecast_accuracy_{report_date}.csv'
        generate_accuracy_report(results, report_path, args.horizon)
        print(f"Generated report: {report_path}")

    # Show individual results
    valid_results = [r for r in results if r.get('mape') is not None]
    if valid_results:
        print(f"\nIndividual SKU Results:")
        sorted_results = sorted(valid_results, key=lambda x: x['mape'])
        for r in sorted_results[:10]:
            grade = get_accuracy_grade(r['mape'])
            print(f"  {r['sku_key']}: MAPE={r['mape']}%, Bias={r['bias']}%, Grade={grade}")

        if len(sorted_results) > 10:
            print(f"  ... and {len(sorted_results) - 10} more")

    # Alert if degraded
    if not args.no_alert and overall['overall_mape'] is not None:
        if send_alert_if_degraded(overall['overall_mape'], 25.0, str(db_path)):
            print(f"\nAlert sent: MAPE exceeds threshold")

    # Exit with error if MAPE too high
    if overall['overall_mape'] is not None and overall['overall_mape'] > 30:
        print(f"\nWARNING: MAPE > 30% - forecast model needs attention")
        return 1

    print(f"\nBacktest complete.")
    return 0


if __name__ == '__main__':
    exit(main())
