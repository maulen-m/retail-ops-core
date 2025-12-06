#!/usr/bin/env python3
"""
TASK-063: PO Draft Expiration Job

Auto-expire drafts after 48 hours to prevent stale recommendations.
Run daily after PO generation.

Usage:
    python scripts/expire_po_drafts.py
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def expire_stale_drafts(db_path: str, max_age_hours: int = 48) -> dict:
    """
    Mark old pending drafts as expired.

    Args:
        db_path: Path to database
        max_age_hours: Maximum age in hours before expiration

    Returns:
        Dict with expiration results
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get drafts to expire
    cursor.execute("""
        SELECT draft_id, created_at, total_units
        FROM fact_po_draft
        WHERE status = 'PENDING'
        AND (
            expires_at < datetime('now')
            OR created_at < datetime('now', '-{} hours')
        )
    """.format(max_age_hours))

    to_expire = cursor.fetchall()

    # Expire them
    cursor.execute("""
        UPDATE fact_po_draft
        SET status = 'EXPIRED',
            notes = 'Auto-expired after {} hours'
        WHERE status = 'PENDING'
        AND (
            expires_at < datetime('now')
            OR created_at < datetime('now', '-{} hours')
        )
    """.format(max_age_hours, max_age_hours))

    count = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        'expired_count': count,
        'expired_drafts': [
            {'draft_id': d[0], 'created_at': d[1], 'units': d[2]}
            for d in to_expire
        ]
    }


def get_expiration_stats(db_path: str) -> dict:
    """Get statistics on draft expirations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*)
        FROM fact_po_draft
        GROUP BY status
    """)

    stats = {}
    for row in cursor.fetchall():
        stats[row[0]] = row[1]

    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description='Expire stale PO drafts')
    parser.add_argument(
        '--max-age',
        type=int,
        default=48,
        help='Maximum age in hours (default: 48)'
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

    print(f"=== PO Draft Expiration ===")
    print(f"Database: {db_path}")
    print(f"Max age: {args.max_age} hours")
    print()

    # Run expiration
    result = expire_stale_drafts(str(db_path), args.max_age)

    if result['expired_count'] == 0:
        print("No drafts expired")
    else:
        print(f"Expired {result['expired_count']} draft(s):")
        for d in result['expired_drafts']:
            print(f"  #{d['draft_id']}: created {d['created_at']}, {d['units']} units")

    # Show stats
    stats = get_expiration_stats(str(db_path))
    print(f"\nCurrent draft status:")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")

    return 0


if __name__ == '__main__':
    exit(main())
