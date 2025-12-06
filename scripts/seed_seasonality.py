#!/usr/bin/env python3
"""
TASK-027: Seed dim_seasonality with Kazakhstan retail patterns.

Seasonality multipliers reflect Kazakhstan CL (Clothing) retail patterns:
- Nauryz (March holiday) spike
- Summer vacation dip
- Back-to-school September boost
- December holiday peak

Usage:
    python scripts/seed_seasonality.py [--db path/to/app.db]
"""

import argparse
import sqlite3
from pathlib import Path


# Kazakhstan CL (Clothing) seasonal patterns
SEASONALITY_DATA = [
    # (month, product_type, multiplier, notes)
    (1, 'CL', 0.70, 'Post-holiday slump'),
    (2, 'CL', 0.75, 'Winter slow period'),
    (3, 'CL', 1.10, 'Spring pickup, Nauryz prep'),
    (4, 'CL', 1.20, 'Nauryz holiday, spring demand'),
    (5, 'CL', 1.00, 'Baseline month'),
    (6, 'CL', 0.90, 'Summer dip starts'),
    (7, 'CL', 0.80, 'Summer vacation peak'),
    (8, 'CL', 0.95, 'Back-to-school prep'),
    (9, 'CL', 1.15, 'Back-to-school, fall season'),
    (10, 'CL', 1.10, 'Fall demand'),
    (11, 'CL', 1.00, 'Pre-winter transition'),
    (12, 'CL', 1.25, 'Holiday shopping peak'),

    # ELS (Elastic/Sportswear) - similar pattern with fitness resolutions
    (1, 'ELS', 0.90, 'New year fitness resolutions'),
    (2, 'ELS', 0.85, 'Resolution drop-off'),
    (3, 'ELS', 1.05, 'Spring fitness prep'),
    (4, 'ELS', 1.10, 'Outdoor season starts'),
    (5, 'ELS', 1.15, 'Peak outdoor season'),
    (6, 'ELS', 1.10, 'Summer outdoor activities'),
    (7, 'ELS', 1.00, 'Vacation period'),
    (8, 'ELS', 0.95, 'End of summer'),
    (9, 'ELS', 1.05, 'Fall fitness restart'),
    (10, 'ELS', 1.00, 'Baseline'),
    (11, 'ELS', 0.90, 'Pre-winter slowdown'),
    (12, 'ELS', 0.95, 'Holiday gifts'),

    # FUR (Outerwear/Fur) - winter-heavy pattern
    (1, 'FUR', 0.60, 'Post-winter clearance'),
    (2, 'FUR', 0.50, 'Deep winter end'),
    (3, 'FUR', 0.40, 'Spring transition'),
    (4, 'FUR', 0.30, 'Off-season'),
    (5, 'FUR', 0.25, 'Off-season'),
    (6, 'FUR', 0.20, 'Summer low'),
    (7, 'FUR', 0.20, 'Summer low'),
    (8, 'FUR', 0.40, 'Early buyers'),
    (9, 'FUR', 0.80, 'Fall pre-order'),
    (10, 'FUR', 1.20, 'Winter prep'),
    (11, 'FUR', 1.50, 'Peak winter demand'),
    (12, 'FUR', 1.40, 'Holiday + winter peak'),
]


def seed_seasonality(db_path: str) -> int:
    """
    Seed dim_seasonality table with Kazakhstan retail patterns.

    Args:
        db_path: Path to SQLite database

    Returns:
        Number of rows inserted
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Clear existing data (idempotent)
    cursor.execute("DELETE FROM dim_seasonality")

    # Insert seed data
    cursor.executemany(
        """
        INSERT INTO dim_seasonality (month, product_type, multiplier, notes)
        VALUES (?, ?, ?, ?)
        """,
        SEASONALITY_DATA
    )

    rows_inserted = cursor.rowcount
    conn.commit()
    conn.close()

    return len(SEASONALITY_DATA)


def verify_seasonality(db_path: str) -> dict:
    """
    Verify dim_seasonality data.

    Returns:
        Dict with verification results
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count by product type
    cursor.execute("""
        SELECT product_type, COUNT(*), AVG(multiplier)
        FROM dim_seasonality
        GROUP BY product_type
    """)

    results = {}
    for row in cursor.fetchall():
        product_type, count, avg_mult = row
        results[product_type] = {
            'count': count,
            'avg_multiplier': round(avg_mult, 2)
        }

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description='Seed dim_seasonality table')
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve path relative to project root
    db_path = Path(args.db)
    if not db_path.is_absolute():
        project_root = Path(__file__).parent.parent
        db_path = project_root / db_path

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"Seeding dim_seasonality in {db_path}...")

    rows = seed_seasonality(str(db_path))
    print(f"Inserted {rows} seasonality records")

    # Verify
    results = verify_seasonality(str(db_path))
    print("\nVerification:")
    for product_type, data in results.items():
        print(f"  {product_type}: {data['count']} months, avg multiplier = {data['avg_multiplier']}")

    # Validate CL has 12 months
    if results.get('CL', {}).get('count', 0) != 12:
        print("ERROR: CL should have exactly 12 months")
        return 1

    print("\nSeed complete.")
    return 0


if __name__ == '__main__':
    exit(main())
