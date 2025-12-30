#!/usr/bin/env python3
"""
P0-3: Demand Estimator Regression Harness

Produces a CSV report for demand quality assurance, focusing on:
- LINE52 and LINE51 (always included)
- Top revenue SKUs
- SKUs with potential under-estimation issues

Flags:
- d_final < 0.7 * d_anchor (under-estimation)
- eligible_days == 0 (no valid data)
- ANCHOR_ONLY confidence (fallback-only mode)

Output: exports/demand_harness_YYYYMMDD.csv

Usage:
    python scripts/report_demand_top_skus.py
    python scripts/report_demand_top_skus.py --output custom_path.csv
"""

import argparse
import csv
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"


def get_demand_harness_data(conn: sqlite3.Connection, cutoff_date: str = None) -> list[dict]:
    """
    Query demand estimates and generate harness data.

    Returns list of dicts with demand metrics and flags.
    """
    conn.row_factory = sqlite3.Row

    # Get latest cutoff if not specified
    if not cutoff_date:
        cutoff_date = conn.execute(
            "SELECT MAX(cutoff_date) as latest FROM fact_demand_estimates"
        ).fetchone()['latest']

    if not cutoff_date:
        print("ERROR: No demand estimates found in fact_demand_estimates")
        return []

    print(f"Using cutoff_date: {cutoff_date}")

    # Query all demand estimates for the cutoff date
    rows = conn.execute("""
        SELECT
            de.sku_key,
            de.d_anchor,
            de.d_data,
            de.d_model,
            de.d_peak,
            de.d_final,
            de.confidence,
            de.anchor_weight,
            de.w,
            de.calendar_days,
            de.eligible_days,
            de.oos_days,
            de.unknown_days,
            de.availability_score,
            de.oos_type,
            de.partial_oos_sizes,
            de.estimator_version,
            ds.model,
            ds.product_type
        FROM fact_demand_estimates de
        LEFT JOIN dim_sku ds ON de.sku_key = ds.sku_key
        WHERE de.cutoff_date = ?
        ORDER BY de.d_final DESC
    """, (cutoff_date,)).fetchall()

    results = []
    for row in rows:
        d_anchor = row['d_anchor'] or 0
        d_data = row['d_data'] or 0
        d_final = row['d_final'] or 0
        eligible_days = row['eligible_days'] or 0

        # Calculate flags
        flags = []

        # Under-estimation: d_final < 0.7 * d_anchor
        if d_anchor > 0 and d_final < 0.7 * d_anchor:
            flags.append("UNDER_EST")

        # No eligible days
        if eligible_days == 0:
            flags.append("NO_DATA")

        # Anchor-only mode
        if row['confidence'] == 'ANCHOR_ONLY':
            flags.append("ANCHOR_ONLY")

        # Low availability
        if (row['availability_score'] or 0) < 0.3:
            flags.append("LOW_AVAIL")

        # Priority SKU check
        is_priority = 'LINE52' in (row['sku_key'] or '') or 'LINE51' in (row['sku_key'] or '')
        if is_priority:
            flags.append("PRIORITY")

        results.append({
            'sku_key': row['sku_key'],
            'model': row['model'],
            'product_type': row['product_type'],
            'd_anchor': round(d_anchor, 2),
            'd_data': round(d_data, 2),
            'd_model': round(row['d_model'] or 0, 2),
            'd_peak': round(row['d_peak'] or 0, 2),
            'd_final': round(d_final, 2),
            'confidence': row['confidence'],
            'anchor_weight': round(row['anchor_weight'] or 0, 2),
            'w': round(row['w'] or 0, 2),
            'calendar_days': row['calendar_days'],
            'eligible_days': eligible_days,
            'oos_days': row['oos_days'] or 0,
            'unknown_days': row['unknown_days'] or 0,
            'availability_score': round(row['availability_score'] or 0, 3),
            'oos_type': row['oos_type'],
            'partial_oos_sizes': row['partial_oos_sizes'],
            'flags': '|'.join(flags) if flags else '',
            'is_priority': is_priority,
            'under_est_pct': round((1 - d_final / d_anchor) * 100, 1) if d_anchor > 0 else 0,
        })

    return results


def generate_report(output_path: Path = None) -> dict:
    """
    Generate the demand harness report.

    Returns summary dict.
    """
    conn = sqlite3.connect(str(DB_PATH))

    data = get_demand_harness_data(conn)
    if not data:
        conn.close()
        return {'error': 'No data'}

    # Default output path
    if not output_path:
        today = date.today().strftime('%Y%m%d')
        output_path = EXPORTS_DIR / f"demand_harness_{today}.csv"

    # Ensure exports dir exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write CSV
    fieldnames = [
        'sku_key', 'model', 'product_type',
        'd_anchor', 'd_data', 'd_model', 'd_peak', 'd_final',
        'confidence', 'anchor_weight', 'w',
        'calendar_days', 'eligible_days', 'oos_days', 'unknown_days',
        'availability_score', 'oos_type', 'partial_oos_sizes',
        'flags', 'under_est_pct'
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)

    print(f"\nDemand harness exported to: {output_path}")

    # Generate summary
    total = len(data)
    flagged = [d for d in data if d['flags']]
    under_est = [d for d in data if 'UNDER_EST' in d['flags']]
    no_data = [d for d in data if 'NO_DATA' in d['flags']]
    anchor_only = [d for d in data if 'ANCHOR_ONLY' in d['flags']]
    priority = [d for d in data if d['is_priority']]

    print("\n" + "=" * 60)
    print("DEMAND HARNESS SUMMARY")
    print("=" * 60)
    print(f"Total SKUs: {total}")
    print(f"Flagged SKUs: {len(flagged)}")
    print(f"  - Under-estimated (d_final < 0.7*d_anchor): {len(under_est)}")
    print(f"  - No eligible days: {len(no_data)}")
    print(f"  - Anchor-only mode: {len(anchor_only)}")
    print(f"\nPriority SKUs (LINE52/LINE51): {len(priority)}")

    # Show top offenders
    if under_est:
        print("\n" + "-" * 60)
        print("TOP UNDER-ESTIMATION OFFENDERS:")
        print("-" * 60)
        under_est_sorted = sorted(under_est, key=lambda x: x['under_est_pct'], reverse=True)
        for i, sku in enumerate(under_est_sorted[:10]):
            print(f"  {i+1}. {sku['sku_key']}: "
                  f"anchor={sku['d_anchor']:.1f}, final={sku['d_final']:.1f}, "
                  f"under-est={sku['under_est_pct']:.0f}%")

    # Show priority SKUs detail
    if priority:
        print("\n" + "-" * 60)
        print("PRIORITY SKUs DETAIL:")
        print("-" * 60)
        for sku in priority:
            print(f"  {sku['sku_key']}:")
            print(f"    d_anchor={sku['d_anchor']}, d_data={sku['d_data']}, d_final={sku['d_final']}")
            print(f"    eligible_days={sku['eligible_days']}/{sku['calendar_days']}, "
                  f"availability={sku['availability_score']:.2f}")
            print(f"    confidence={sku['confidence']}, flags={sku['flags'] or 'none'}")

    conn.close()

    return {
        'total_skus': total,
        'flagged': len(flagged),
        'under_estimated': len(under_est),
        'no_data': len(no_data),
        'anchor_only': len(anchor_only),
        'priority_skus': len(priority),
        'output_path': str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate demand harness report")
    parser.add_argument("--output", "-o", help="Output CSV path")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None
    result = generate_report(output_path)

    if 'error' in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"\nReport complete: {result['output_path']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
