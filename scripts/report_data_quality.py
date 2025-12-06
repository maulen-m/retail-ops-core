#!/usr/bin/env python3
"""
TASK-048: Data Quality Report

Weekly data quality report with anomaly detection.
Sends Telegram alert if critical issues found.

Usage:
    python scripts/report_data_quality.py [--lookback 90] [--send-alert]

Output:
    reports/data_quality_YYYY-MM-DD.csv
"""

import argparse
import csv
from datetime import date
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.validation.data_quality import (
    detect_all_anomalies,
    get_data_quality_score
)


def generate_report(anomalies: dict, output_path: Path) -> None:
    """
    Generate CSV data quality report.

    Args:
        anomalies: Anomaly detection results
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'severity', 'type', 'date', 'sku_key', 'sku_id', 'order_id', 'details'
        ])

        for anomaly in anomalies['all_anomalies']:
            writer.writerow([
                anomaly.get('severity', ''),
                anomaly.get('type', ''),
                anomaly.get('date', ''),
                anomaly.get('sku_key', ''),
                anomaly.get('sku_id', ''),
                anomaly.get('order_id', ''),
                anomaly.get('details', '')
            ])


def send_quality_alert(anomalies: dict, score: float) -> bool:
    """
    Send Telegram alert for data quality issues.

    Args:
        anomalies: Anomaly detection results
        score: Data quality score

    Returns:
        True if sent successfully
    """
    try:
        from core.alerts.telegram import send_message

        status = "CRITICAL" if anomalies['has_critical'] else "WARNING" if len(anomalies['warnings']) > 5 else "OK"
        emoji = "" if anomalies['has_critical'] else "" if len(anomalies['warnings']) > 5 else ""

        message = (
            f"<b>{emoji} Data Quality Report</b>\n\n"
            f"Score: <b>{score:.0f}/100</b>\n"
            f"Status: <b>{status}</b>\n\n"
            f"Issues found:\n"
            f"• Critical: {len(anomalies['critical'])}\n"
            f"• Warnings: {len(anomalies['warnings'])}\n"
            f"• Info: {len(anomalies['info'])}\n"
        )

        if anomalies['critical']:
            message += f"\n<b>Critical Issues:</b>\n"
            for a in anomalies['critical'][:3]:
                message += f"• {a['details']}\n"

        send_message(message)
        return True

    except Exception as e:
        print(f"Failed to send alert: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate data quality report')
    parser.add_argument(
        '--lookback',
        type=int,
        default=90,
        help='Days to analyze (default: 90)'
    )
    parser.add_argument(
        '--send-alert',
        action='store_true',
        help='Send Telegram alert'
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

    print(f"=== Data Quality Report ===")
    print(f"Database: {db_path}")
    print(f"Lookback: {args.lookback} days")
    print()

    # Detect anomalies
    anomalies = detect_all_anomalies(str(db_path), args.lookback)
    score = get_data_quality_score(str(db_path))

    # Generate report
    report_date = date.today().isoformat()
    report_path = project_root / 'reports' / f'data_quality_{report_date}.csv'
    generate_report(anomalies, report_path)
    print(f"Report saved: {report_path}")
    print()

    # Print summary
    print(f"=== Summary ===")
    print(f"Data Quality Score: {score:.0f}/100")
    print(f"Total issues: {anomalies['total']}")
    print(f"  Critical: {len(anomalies['critical'])}")
    print(f"  Warnings: {len(anomalies['warnings'])}")
    print(f"  Info: {len(anomalies['info'])}")

    # Show critical issues
    if anomalies['critical']:
        print(f"\nCritical Issues:")
        for a in anomalies['critical'][:5]:
            print(f"  [{a['type']}] {a['details']}")

    # Show warnings
    if anomalies['warnings']:
        print(f"\nWarnings:")
        for a in anomalies['warnings'][:5]:
            print(f"  [{a['type']}] {a['details']}")

        if len(anomalies['warnings']) > 5:
            print(f"  ... and {len(anomalies['warnings']) - 5} more")

    # Send alert if critical or requested
    if args.send_alert or anomalies['has_critical']:
        if send_quality_alert(anomalies, score):
            print(f"\nTelegram alert sent")

    # Exit with error if critical issues
    if anomalies['has_critical']:
        print(f"\n DATA QUALITY ISSUES FOUND")
        return 1

    print(f"\nData quality check complete.")
    return 0


if __name__ == '__main__':
    exit(main())
