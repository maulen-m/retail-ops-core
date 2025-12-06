#!/usr/bin/env python3
"""
TASK-064: PO Analytics Report

Generates analytics on PO drafts and approval patterns.

Usage:
    python scripts/report_po_analytics.py [--days 30]

Output:
    reports/po_analytics_YYYY-MM-DD.csv
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


def get_draft_statistics(db_path: str, days: int = 30) -> dict:
    """Get overall draft statistics."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Total drafts
    cursor.execute("""
        SELECT COUNT(*) FROM fact_po_draft WHERE created_at >= ?
    """, (cutoff,))
    total = cursor.fetchone()[0] or 0

    # By status
    cursor.execute("""
        SELECT status, COUNT(*)
        FROM fact_po_draft
        WHERE created_at >= ?
        GROUP BY status
    """, (cutoff,))

    by_status = {row[0]: row[1] for row in cursor.fetchall()}

    # Approval rate
    approved = by_status.get('APPROVED', 0)
    approval_rate = approved / total * 100 if total > 0 else 0

    # Average time to approval
    cursor.execute("""
        SELECT AVG(
            (julianday(approved_at) - julianday(created_at)) * 24
        )
        FROM fact_po_draft
        WHERE status = 'APPROVED'
        AND created_at >= ?
    """, (cutoff,))
    avg_approval_hours = cursor.fetchone()[0] or 0

    conn.close()

    return {
        'total_drafts': total,
        'by_status': by_status,
        'approval_rate': round(approval_rate, 1),
        'avg_approval_hours': round(avg_approval_hours, 1)
    }


def get_rejection_reasons(db_path: str, days: int = 30) -> list[dict]:
    """Get breakdown of rejection reasons."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT rejection_reason, COUNT(*)
        FROM fact_po_draft
        WHERE status = 'REJECTED'
        AND created_at >= ?
        GROUP BY rejection_reason
        ORDER BY COUNT(*) DESC
    """, (cutoff,))

    reasons = []
    for row in cursor.fetchall():
        reasons.append({
            'reason': row[0] or 'No reason',
            'count': row[1]
        })

    conn.close()
    return reasons


def get_confidence_vs_approval(db_path: str, days: int = 30) -> dict:
    """Analyze correlation between confidence and approval."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Approval rates by confidence bucket
    buckets = [
        (0.0, 0.5, 'Low (0-50%)'),
        (0.5, 0.7, 'Medium (50-70%)'),
        (0.7, 0.9, 'High (70-90%)'),
        (0.9, 1.1, 'Very High (90%+)')
    ]

    results = []
    for low, high, label in buckets:
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END) as approved
            FROM fact_po_draft
            WHERE created_at >= ?
            AND confidence_score >= ? AND confidence_score < ?
        """, (cutoff, low, high))

        row = cursor.fetchone()
        total = row[0] or 0
        approved = row[1] or 0
        rate = approved / total * 100 if total > 0 else 0

        results.append({
            'bucket': label,
            'total': total,
            'approved': approved,
            'rate': round(rate, 1)
        })

    conn.close()
    return results


def generate_report(stats: dict, reasons: list, confidence: list, output_path: Path) -> None:
    """Generate CSV analytics report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)

        # Summary section
        writer.writerow(['=== PO Analytics Summary ==='])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Drafts', stats['total_drafts']])
        writer.writerow(['Approval Rate', f"{stats['approval_rate']}%"])
        writer.writerow(['Avg Approval Time', f"{stats['avg_approval_hours']} hours"])
        writer.writerow([])

        # Status breakdown
        writer.writerow(['=== Status Breakdown ==='])
        writer.writerow(['Status', 'Count'])
        for status, count in stats['by_status'].items():
            writer.writerow([status, count])
        writer.writerow([])

        # Rejection reasons
        writer.writerow(['=== Rejection Reasons ==='])
        writer.writerow(['Reason', 'Count'])
        for r in reasons:
            writer.writerow([r['reason'], r['count']])
        writer.writerow([])

        # Confidence analysis
        writer.writerow(['=== Confidence vs Approval ==='])
        writer.writerow(['Confidence Bucket', 'Total', 'Approved', 'Rate'])
        for c in confidence:
            writer.writerow([c['bucket'], c['total'], c['approved'], f"{c['rate']}%"])


def main():
    parser = argparse.ArgumentParser(description='Generate PO analytics report')
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Days to analyze (default: 30)'
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

    print(f"=== PO Analytics Report ===")
    print(f"Database: {db_path}")
    print(f"Period: Last {args.days} days")
    print()

    # Gather data
    stats = get_draft_statistics(str(db_path), args.days)
    reasons = get_rejection_reasons(str(db_path), args.days)
    confidence = get_confidence_vs_approval(str(db_path), args.days)

    # Generate report
    report_date = date.today().isoformat()
    report_path = project_root / 'reports' / f'po_analytics_{report_date}.csv'
    generate_report(stats, reasons, confidence, report_path)
    print(f"Report saved: {report_path}")
    print()

    # Print summary
    print(f"=== Summary ===")
    print(f"Total drafts: {stats['total_drafts']}")
    print(f"Approval rate: {stats['approval_rate']}%")
    print(f"Avg approval time: {stats['avg_approval_hours']} hours")
    print()

    print("Status breakdown:")
    for status, count in stats['by_status'].items():
        print(f"  {status}: {count}")

    if reasons:
        print()
        print("Top rejection reasons:")
        for r in reasons[:3]:
            print(f"  {r['reason']}: {r['count']}")

    return 0


if __name__ == '__main__':
    exit(main())
