#!/usr/bin/env python3
"""
TASK-032: Day-of-Week Analysis Report

Generates CSV report with DOW indices per SKU.
Identifies SKUs with strong weekend patterns for optimized forecasting.

Usage:
    python scripts/report_dow_analysis.py [--lookback 90] [--min-days 30]

Output:
    reports/dow_patterns_YYYY-MM-DD.csv
"""

import argparse
import csv
from datetime import date
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.calc.dow_patterns import (
    analyze_all_skus_dow,
    get_dow_name
)


def generate_dow_report(
    results: list[dict],
    output_path: Path
) -> None:
    """
    Generate DOW analysis CSV report.

    Args:
        results: List of DOW analysis dicts
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'sku_key',
            'mon_idx', 'tue_idx', 'wed_idx', 'thu_idx', 'fri_idx', 'sat_idx', 'sun_idx',
            'weekend_lift', 'pattern_strength', 'sample_days', 'has_strong_pattern'
        ])

        for result in results:
            indices = result['indices']
            writer.writerow([
                result['sku_key'],
                round(indices.get(0, 1.0), 3),
                round(indices.get(1, 1.0), 3),
                round(indices.get(2, 1.0), 3),
                round(indices.get(3, 1.0), 3),
                round(indices.get(4, 1.0), 3),
                round(indices.get(5, 1.0), 3),
                round(indices.get(6, 1.0), 3),
                result['weekend_lift'],
                result['pattern_strength'],
                result['sample_days'],
                'Yes' if result['has_strong_pattern'] else 'No'
            ])


def print_summary(results: list[dict]) -> None:
    """
    Print summary of DOW analysis.

    Args:
        results: List of DOW analysis dicts
    """
    if not results:
        print("No SKUs with sufficient data for DOW analysis")
        return

    # Count strong patterns
    strong_patterns = [r for r in results if r['has_strong_pattern']]

    # Calculate average weekend lift
    avg_lift = sum(r['weekend_lift'] for r in results) / len(results)

    # Find highest weekend lift SKUs
    sorted_by_lift = sorted(results, key=lambda x: x['weekend_lift'], reverse=True)

    print(f"Total SKUs analyzed: {len(results)}")
    print(f"SKUs with strong DOW patterns: {len(strong_patterns)}")
    print(f"Average weekend lift: {round(avg_lift, 1)}%")
    print()

    print("Top 5 SKUs by weekend lift:")
    for r in sorted_by_lift[:5]:
        print(f"  {r['sku_key']}: +{r['weekend_lift']}% weekend, strength={r['pattern_strength']}")

    print()
    print("SKUs with strong patterns (strength > 0.15):")
    for r in strong_patterns[:10]:
        indices = r['indices']
        print(f"  {r['sku_key']}:")
        print(f"    Mon={indices[0]:.2f} Tue={indices[1]:.2f} Wed={indices[2]:.2f} Thu={indices[3]:.2f}")
        print(f"    Fri={indices[4]:.2f} Sat={indices[5]:.2f} Sun={indices[6]:.2f}")


def main():
    parser = argparse.ArgumentParser(description='Generate DOW analysis report')
    parser.add_argument(
        '--lookback',
        type=int,
        default=90,
        help='Days of history to analyze (default: 90)'
    )
    parser.add_argument(
        '--min-days',
        type=int,
        default=30,
        help='Minimum days with sales required (default: 30)'
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

    print(f"=== Day-of-Week Analysis ===")
    print(f"Database: {db_path}")
    print(f"Lookback: {args.lookback} days")
    print(f"Minimum days: {args.min_days}")
    print()

    # Run analysis
    results = analyze_all_skus_dow(
        str(db_path),
        lookback_days=args.lookback,
        min_sales_days=args.min_days
    )

    # Generate report
    report_date = date.today().isoformat()
    report_path = project_root / 'reports' / f'dow_patterns_{report_date}.csv'
    generate_dow_report(results, report_path)
    print(f"Report saved: {report_path}")
    print()

    # Print summary
    print_summary(results)

    print(f"\nDOW analysis complete.")
    return 0


if __name__ == '__main__':
    exit(main())
