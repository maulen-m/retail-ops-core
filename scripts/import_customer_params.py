#!/usr/bin/env python3
"""
Import Customer Parameters CLI (Phase 9.5 - TASK-140).

Imports customer height/weight from CSV batch entry and recalculates sizes.

CSV Format:
    order_id,customer_height_cm,customer_weight_kg,notes

Usage:
    # Import from CSV
    python scripts/import_customer_params.py customer_params.csv

    # Import and recalculate sizes
    python scripts/import_customer_params.py customer_params.csv --recalc

    # Generate template CSV
    python scripts/import_customer_params.py --template

    # Dry run (validate without saving)
    python scripts/import_customer_params.py customer_params.csv --dry-run
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
from core.calc.size_probability import calc_size_from_params, determine_size


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


def generate_template(output_path: Path = None) -> Path:
    """Generate template CSV for customer params entry."""
    if output_path is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORT_DIR / f"customer_params_template_{date_str}.csv"

    # Get orders without customer params
    with get_db(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                order_id, store_code, kaspi_offer_name,
                my_size, assigned_size, size_source, size_confidence,
                customer_height_cm, customer_weight_kg,
                planned_shipment_date
            FROM fact_orders_kaspi
            WHERE customer_height_cm IS NULL
               OR customer_weight_kg IS NULL
            ORDER BY planned_shipment_date ASC
            """
        ).fetchall()

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow([
            'order_id',
            'customer_height_cm',
            'customer_weight_kg',
            'notes',
            '# store_code (info)',
            '# kaspi_offer_name (info)',
            '# current_size (info)',
            '# planned_date (info)',
        ])

        # Rows
        for row in rows:
            writer.writerow([
                row['order_id'],
                row['customer_height_cm'] or '',
                row['customer_weight_kg'] or '',
                '',  # Notes
                row['store_code'],
                row['kaspi_offer_name'][:50] if row['kaspi_offer_name'] else '',
                row['my_size'] or row['assigned_size'] or '',
                row['planned_shipment_date'] or '',
            ])

    return output_path


def parse_csv(filepath: Path) -> list[dict]:
    """Parse customer params CSV file."""
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    entries = []
    errors = []

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
            order_id = row.get('order_id', '').strip()
            height_str = row.get('customer_height_cm', '').strip()
            weight_str = row.get('customer_weight_kg', '').strip()

            if not order_id:
                continue  # Skip empty rows

            # Validate height
            height = None
            if height_str:
                try:
                    height = int(float(height_str))
                    if height < 100 or height > 220:
                        errors.append(f"Row {i}: Invalid height {height} for {order_id}")
                        height = None
                except ValueError:
                    errors.append(f"Row {i}: Cannot parse height '{height_str}' for {order_id}")

            # Validate weight
            weight = None
            if weight_str:
                try:
                    weight = int(float(weight_str))
                    if weight < 20 or weight > 200:
                        errors.append(f"Row {i}: Invalid weight {weight} for {order_id}")
                        weight = None
                except ValueError:
                    errors.append(f"Row {i}: Cannot parse weight '{weight_str}' for {order_id}")

            if height or weight:
                entries.append({
                    'order_id': order_id,
                    'customer_height_cm': height,
                    'customer_weight_kg': weight,
                    'notes': row.get('notes', ''),
                })

    if errors:
        logging.warning(f"CSV parsing had {len(errors)} warnings:")
        for err in errors[:10]:
            logging.warning(f"  {err}")
        if len(errors) > 10:
            logging.warning(f"  ... and {len(errors) - 10} more")

    return entries


def import_params(
    entries: list[dict],
    recalculate: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Import customer params to database.

    Args:
        entries: List of dicts with order_id, height, weight
        recalculate: If True, recalculate size from new params
        dry_run: If True, validate only without saving

    Returns:
        Dict with import statistics
    """
    stats = {
        'total': len(entries),
        'found': 0,
        'updated': 0,
        'not_found': 0,
        'sizes_updated': 0,
    }

    if not entries:
        return stats

    with get_db(DB_PATH) as conn:
        for entry in entries:
            order_id = entry['order_id']
            height = entry.get('customer_height_cm')
            weight = entry.get('customer_weight_kg')

            # Check if order exists
            row = conn.execute(
                """
                SELECT id, kaspi_offer_name, sku_key
                FROM fact_orders_kaspi
                WHERE order_id = ?
                """,
                (order_id,)
            ).fetchone()

            if not row:
                logging.warning(f"Order not found: {order_id}")
                stats['not_found'] += 1
                continue

            stats['found'] += 1

            if dry_run:
                logging.info(f"Would update {order_id}: height={height}, weight={weight}")
                stats['updated'] += 1
                continue

            # Update customer params
            conn.execute(
                """
                UPDATE fact_orders_kaspi
                SET customer_height_cm = ?,
                    customer_weight_kg = ?
                WHERE id = ?
                """,
                (height, weight, row['id'])
            )
            stats['updated'] += 1

            # Recalculate size if requested
            if recalculate and height and weight:
                # Get product type
                product_type = 'CL'
                sku_key = row['sku_key']
                if sku_key:
                    parts = sku_key.split('_')
                    if parts:
                        product_type = parts[0]

                # Calculate size
                result = determine_size(
                    order={
                        'kaspi_offer_name': row['kaspi_offer_name'],
                        'sku_key': sku_key,
                        'product_type': product_type,
                    },
                    customer_height=height,
                    customer_weight=weight,
                )

                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET assigned_size = ?,
                        size_source = ?,
                        size_confidence = ?
                    WHERE id = ?
                    """,
                    (result.size, result.source, result.confidence, row['id'])
                )
                stats['sizes_updated'] += 1

                logging.debug(
                    f"Order {order_id}: size={result.size} ({result.source})"
                )

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Import customer height/weight parameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input file
    parser.add_argument(
        'csvfile',
        nargs='?',
        type=Path,
        help='CSV file with customer parameters',
    )

    # Mode
    parser.add_argument(
        '--template',
        action='store_true',
        help='Generate template CSV for data entry',
    )

    # Options
    parser.add_argument(
        '--recalc',
        action='store_true',
        help='Recalculate sizes after importing params',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate without saving to database',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output',
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    print(f"\n{'=' * 60}")
    print("CUSTOMER PARAMS IMPORT")
    print(f"{'=' * 60}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.template:
        output_path = generate_template()
        print(f"\nTemplate generated: {output_path}")

        # Count orders needing params
        with get_db(DB_PATH) as conn:
            count = conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_orders_kaspi
                WHERE customer_height_cm IS NULL
                   OR customer_weight_kg IS NULL
                """
            ).fetchone()[0]

        print(f"Orders needing params: {count}")
        print("\nInstructions:")
        print("  1. Fill in customer_height_cm and customer_weight_kg")
        print("  2. Import with: python scripts/import_customer_params.py <file.csv> --recalc")
        return 0

    if not args.csvfile:
        parser.print_help()
        print("\nExample:")
        print("  python scripts/import_customer_params.py --template")
        print("  python scripts/import_customer_params.py params.csv --recalc")
        return 1

    print(f"Input: {args.csvfile}")
    print(f"Recalculate sizes: {args.recalc}")
    print(f"Dry run: {args.dry_run}")

    # Parse CSV
    try:
        entries = parse_csv(args.csvfile)
        print(f"\nParsed {len(entries)} entries from CSV")
    except Exception as e:
        logging.error(f"Error parsing CSV: {e}")
        return 1

    if not entries:
        print("No valid entries to import")
        return 0

    # Import
    stats = import_params(
        entries,
        recalculate=args.recalc,
        dry_run=args.dry_run,
    )

    print(f"\n{'=' * 60}")
    print("IMPORT RESULTS")
    print(f"{'=' * 60}")
    print(f"Total entries: {stats['total']}")
    print(f"Orders found: {stats['found']}")
    print(f"Orders updated: {stats['updated']}")
    print(f"Orders not found: {stats['not_found']}")
    if args.recalc:
        print(f"Sizes recalculated: {stats['sizes_updated']}")

    if args.dry_run:
        print("\n(Dry run - no changes saved)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
