#!/usr/bin/env python3
"""
Assign Sizes CLI (Phase 9.5 - TASK-139).

Assigns sizes to pending Kaspi orders using the 4-tier cascade.

Usage:
    # Assign sizes using auto cascade
    python scripts/assign_sizes.py --auto

    # Assign for specific store
    python scripts/assign_sizes.py --auto --store UNIVERSAL

    # Export orders needing manual size entry
    python scripts/assign_sizes.py --export-pending

    # Show pending orders without sizes
    python scripts/assign_sizes.py --status

    # Dry run (show what would be assigned)
    python scripts/assign_sizes.py --auto --dry-run
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db
from core.calc.size_probability import determine_size, get_coverage_stats


DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
EXPORT_DIR = Path(__file__).parent.parent / "exports"


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
    )


def get_orders_needing_size(
    store_code: str = None,
    include_low_confidence: bool = True,
) -> list[dict]:
    """Get orders without assigned sizes."""
    with get_db(DB_PATH) as conn:
        query = """
            SELECT
                id, order_id, store_code, kaspi_offer_name, sku_key, sku_id,
                my_size, assigned_size, size_source, size_confidence,
                customer_height_cm, customer_weight_kg,
                internal_status, planned_shipment_date
            FROM fact_orders_kaspi
            WHERE assigned_size IS NULL
        """
        params = []

        if store_code:
            query += " AND store_code = ?"
            params.append(store_code)

        query += " ORDER BY planned_shipment_date ASC"

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_orders_with_low_confidence(store_code: str = None) -> list[dict]:
    """Get orders with low confidence sizes."""
    with get_db(DB_PATH) as conn:
        query = """
            SELECT
                id, order_id, store_code, kaspi_offer_name, sku_key,
                my_size, assigned_size, size_source, size_confidence,
                customer_height_cm, customer_weight_kg,
                internal_status, planned_shipment_date
            FROM fact_orders_kaspi
            WHERE size_confidence = 'LOW'
        """
        params = []

        if store_code:
            query += " AND store_code = ?"
            params.append(store_code)

        query += " ORDER BY planned_shipment_date ASC"

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def assign_size_to_order(
    conn,
    order_id: int,
    size: str,
    source: str,
    confidence: str,
):
    """Update order with assigned size."""
    conn.execute(
        """
        UPDATE fact_orders_kaspi
        SET assigned_size = ?,
            size_source = ?,
            size_confidence = ?
        WHERE id = ?
        """,
        (size, source, confidence, order_id)
    )


def auto_assign_sizes(
    store_code: str = None,
    dry_run: bool = False,
) -> dict:
    """
    Auto-assign sizes using cascade.

    Returns:
        Dict with counts by source and confidence
    """
    orders = get_orders_needing_size(store_code)
    logging.info(f"Found {len(orders)} orders needing size assignment")

    stats = {
        'total': len(orders),
        'assigned': 0,
        'by_source': {},
        'by_confidence': {},
    }

    if not orders:
        return stats

    with get_db(DB_PATH) as conn:
        for order in orders:
            # Get product type from sku_key
            product_type = 'CL'
            if order.get('sku_key'):
                parts = order['sku_key'].split('_')
                if parts:
                    product_type = parts[0]

            # Determine size using cascade
            result = determine_size(
                order={
                    'kaspi_offer_name': order.get('kaspi_offer_name'),
                    'sku_key': order.get('sku_key'),
                    'product_type': product_type,
                },
                customer_height=order.get('customer_height_cm'),
                customer_weight=order.get('customer_weight_kg'),
            )

            # Track stats
            stats['assigned'] += 1
            stats['by_source'][result.source] = stats['by_source'].get(result.source, 0) + 1
            stats['by_confidence'][result.confidence] = stats['by_confidence'].get(result.confidence, 0) + 1

            if not dry_run:
                assign_size_to_order(
                    conn,
                    order['id'],
                    result.size,
                    result.source,
                    result.confidence,
                )

            logging.debug(
                f"Order {order['order_id']}: {result.size} "
                f"({result.source}, {result.confidence})"
            )

    return stats


def export_pending_for_manual(
    store_code: str = None,
    output_path: Path = None,
) -> Path:
    """Export orders needing manual size entry."""
    if output_path is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORT_DIR / f"pending_sizes_{date_str}.csv"

    # Get orders without size or with low confidence
    orders_no_size = get_orders_needing_size(store_code)
    orders_low_conf = get_orders_with_low_confidence(store_code)

    # Combine and dedupe
    order_ids = set()
    orders = []
    for order in orders_no_size + orders_low_conf:
        if order['order_id'] not in order_ids:
            order_ids.add(order['order_id'])
            orders.append(order)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'order_id', 'store_code', 'kaspi_offer_name',
            'current_size', 'assigned_size', 'size_source', 'confidence',
            'customer_height_cm', 'customer_weight_kg',
            'planned_date', 'notes'
        ])

        for order in orders:
            writer.writerow([
                order['order_id'],
                order['store_code'],
                order.get('kaspi_offer_name', ''),
                order.get('my_size', ''),
                order.get('assigned_size', ''),
                order.get('size_source', ''),
                order.get('size_confidence', ''),
                order.get('customer_height_cm', ''),
                order.get('customer_weight_kg', ''),
                order.get('planned_shipment_date', ''),
                '',  # Notes for manual entry
            ])

    return output_path


def print_status(store_code: str = None):
    """Print size assignment status."""
    with get_db(DB_PATH) as conn:
        # Count by assignment status
        query = """
            SELECT
                CASE
                    WHEN assigned_size IS NULL THEN 'NO_SIZE'
                    ELSE 'HAS_SIZE'
                END as status,
                COUNT(*) as cnt
            FROM fact_orders_kaspi
        """
        params = []
        if store_code:
            query += " WHERE store_code = ?"
            params.append(store_code)
        query += " GROUP BY status"

        rows = conn.execute(query, params).fetchall()
        status_counts = {row['status']: row['cnt'] for row in rows}

        # Count by source
        query = """
            SELECT size_source, COUNT(*) as cnt
            FROM fact_orders_kaspi
            WHERE size_source IS NOT NULL
        """
        if store_code:
            query += " AND store_code = ?"
        query += " GROUP BY size_source"

        rows = conn.execute(query, params).fetchall()
        source_counts = {row['size_source']: row['cnt'] for row in rows}

        # Count by confidence
        query = """
            SELECT size_confidence, COUNT(*) as cnt
            FROM fact_orders_kaspi
            WHERE size_confidence IS NOT NULL
        """
        if store_code:
            query += " AND store_code = ?"
        query += " GROUP BY size_confidence"

        rows = conn.execute(query, params).fetchall()
        confidence_counts = {row['size_confidence']: row['cnt'] for row in rows}

    print(f"\n{'=' * 60}")
    print("SIZE ASSIGNMENT STATUS")
    print(f"{'=' * 60}")
    if store_code:
        print(f"Store: {store_code}")

    print(f"\nAssignment Status:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

    total = sum(status_counts.values())
    has_size = status_counts.get('HAS_SIZE', 0)
    print(f"  Coverage: {has_size}/{total} ({has_size/total*100:.1f}%)" if total > 0 else "  No orders")

    if source_counts:
        print(f"\nBy Source:")
        for source, count in sorted(source_counts.items()):
            print(f"  {source}: {count}")

    if confidence_counts:
        print(f"\nBy Confidence:")
        for conf, count in sorted(confidence_counts.items()):
            print(f"  {conf}: {count}")

    # Size probability coverage
    print("\nSize Probability Coverage:")
    stats = get_coverage_stats()
    print(f"  Offers: {stats['covered_offers']}/{stats['total_offers']} ({stats['offer_coverage']:.1%})")
    print(f"  Styles: {stats['covered_styles']}/{stats['total_styles']} ({stats['style_coverage']:.1%})")


def main():
    parser = argparse.ArgumentParser(
        description="Assign sizes to Kaspi orders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--auto',
        action='store_true',
        help='Auto-assign sizes using cascade',
    )
    mode_group.add_argument(
        '--export-pending',
        action='store_true',
        help='Export orders needing manual size entry',
    )
    mode_group.add_argument(
        '--status',
        action='store_true',
        help='Show size assignment status',
    )

    # Filters
    parser.add_argument(
        '--store',
        type=str,
        help='Filter by store code',
    )

    # Options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be assigned without saving',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output',
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    store_code = args.store.upper() if args.store else None

    print(f"\n{'=' * 60}")
    print("SIZE ASSIGNMENT")
    print(f"{'=' * 60}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.status:
        print_status(store_code)
        return 0

    if args.export_pending:
        output_path = export_pending_for_manual(store_code)
        print(f"\nExported pending sizes to: {output_path}")
        return 0

    if args.auto:
        print(f"Mode: AUTO ASSIGN")
        print(f"Store: {store_code or 'ALL'}")
        print(f"Dry run: {args.dry_run}")

        stats = auto_assign_sizes(store_code, dry_run=args.dry_run)

        print(f"\nResults:")
        print(f"  Total orders: {stats['total']}")
        print(f"  Assigned: {stats['assigned']}")

        if stats['by_source']:
            print(f"\n  By Source:")
            for source, count in sorted(stats['by_source'].items()):
                print(f"    {source}: {count}")

        if stats['by_confidence']:
            print(f"\n  By Confidence:")
            for conf, count in sorted(stats['by_confidence'].items()):
                print(f"    {conf}: {count}")

        if not args.dry_run:
            print("\nSizes assigned and saved to database.")
        else:
            print("\n(Dry run - no changes saved)")

        return 0

    # No mode specified
    parser.print_help()
    print("\nExample:")
    print("  python scripts/assign_sizes.py --auto --store UNIVERSAL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
