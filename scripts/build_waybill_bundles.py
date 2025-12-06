#!/usr/bin/env python3
"""
Build grouped waybill PDFs for shipment.

Phase 9.5 TASK-116: CLI to generate grouped waybill PDFs.

Usage:
    # From Excel + ZIP
    python scripts/build_waybill_bundles.py \
        --orders data_raw/ActiveOrders_2025-12-06.xlsx \
        --waybills data_raw/waybills_2025-12-06.zip \
        --output-dir exports/2025-12-06/waybills/

    # From database (orders already ingested)
    python scripts/build_waybill_bundles.py \
        --from-db \
        --date 2025-12-06 \
        --waybills data_raw/waybills.zip \
        --output-dir exports/2025-12-06/waybills/

    # From waybills directory (already extracted)
    python scripts/build_waybill_bundles.py \
        --orders data_raw/ActiveOrders.xlsx \
        --waybills-dir data_raw/waybills/ \
        --output-dir exports/waybills/

Output Structure:
    exports/2025-12-06/waybills/
    ├── NORMAL_singles/
    │   └── PP1___L___LINE52_BLACK.pdf
    ├── SPECIAL_multi_line/
    │   └── PP1___ORDER123456_2items.pdf
    ├── SPECIAL_multi_qty/
    │   └── LINE52_BLACK___qnt5.pdf
    ├── manifest.csv
    ├── missing_orders.csv
    └── build_log.csv
"""
import argparse
import csv
import logging
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db  # noqa: E402
from core.parsers.kaspi_export_parser import (  # noqa: E402
    parse_active_orders,
    filter_for_shipment,
)
from core.waybill.pdf_grouper import (  # noqa: E402
    WaybillGroup,
    extract_waybills_from_zip,
    extract_waybills_from_dir,
    group_orders_for_shipment,
    build_grouped_output,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_orders_from_db(
    target_date: date,
    store_code: str = None,
    status: str = 'READY'
) -> list[dict]:
    """
    Load orders from fact_orders_kaspi.

    Args:
        target_date: Filter by planned_shipment_date
        store_code: Optional store filter
        status: Internal status filter (default: READY)

    Returns:
        List of order dicts
    """
    query = """
        SELECT
            order_id,
            store_code,
            channel_code,
            kaspi_offer_name,
            sku_key,
            sku_id,
            my_size,
            quantity,
            unit_price_kzt,
            created_at,
            planned_shipment_date,
            kaspi_status,
            internal_status
        FROM fact_orders_kaspi
        WHERE internal_status = ?
          AND planned_shipment_date <= ?
    """
    params = [status, target_date.isoformat()]

    if store_code:
        query += " AND store_code = ?"
        params.append(store_code)

    orders = []
    with get_db() as conn:
        cursor = conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description]

        for row in cursor:
            order = dict(zip(columns, row))
            orders.append(order)

    logger.info(f"Loaded {len(orders)} orders from database")
    return orders


def write_manifest(groups: list[WaybillGroup], output_path: Path):
    """Write manifest CSV of all processed groups."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'group_type', 'store_code', 'product_name', 'size',
            'quantity', 'order_count', 'order_ids', 'output_file'
        ])

        for group in groups:
            writer.writerow([
                group.group_type,
                group.store_code,
                group.kaspi_name_core,
                group.my_size,
                group.total_quantity,
                len(group.order_ids),
                ';'.join(group.order_ids),
                group.output_filename,
            ])


def write_missing_orders(missing_ids: list[str], output_path: Path):
    """Write CSV of orders with missing waybills."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['order_id', 'status'])

        for oid in missing_ids:
            writer.writerow([oid, 'MISSING_WAYBILL'])


def write_build_log(stats: dict, output_path: Path, duration_sec: float):
    """Write build log CSV."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['metric', 'value'])
        writer.writerow(['build_timestamp', datetime.now().isoformat()])
        writer.writerow(['duration_seconds', f"{duration_sec:.2f}"])
        writer.writerow(['normal_bundles', stats.get('normal', 0)])
        writer.writerow(['multi_line_bundles', stats.get('multi_line', 0)])
        writer.writerow(['multi_qty_bundles', stats.get('multi_qty', 0)])
        writer.writerow(['errors', stats.get('errors', 0)])
        writer.writerow(['missing_waybills', stats.get('missing', 0)])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build grouped waybill PDFs for shipment"
    )

    # Input sources
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--orders",
        type=str,
        help="Path to ActiveOrders Excel file"
    )
    input_group.add_argument(
        "--from-db",
        action="store_true",
        help="Load orders from fact_orders_kaspi database"
    )

    # Waybill sources
    waybill_group = parser.add_mutually_exclusive_group(required=True)
    waybill_group.add_argument(
        "--waybills",
        type=str,
        help="Path to waybills ZIP file"
    )
    waybill_group.add_argument(
        "--waybills-dir",
        type=str,
        help="Path to directory containing waybill PDFs"
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for grouped PDFs"
    )

    # Filters
    parser.add_argument(
        "--date",
        type=str,
        help="Target date for filtering (YYYY-MM-DD). Default: today"
    )
    parser.add_argument(
        "--store",
        type=str,
        help="Filter by store code"
    )
    parser.add_argument(
        "--ready-only",
        action="store_true",
        default=True,
        help="Only include orders ready for shipment (default: True)"
    )

    # Options
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Don't merge multi-qty/multi-line PDFs (copy individually)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating files"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse target date
    target_date = date.today()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            sys.exit(1)

    logger.info("=" * 60)
    logger.info("Waybill Bundle Builder")
    logger.info("=" * 60)
    logger.info(f"Target date: {target_date}")

    start_time = datetime.now()

    # Load orders
    if args.from_db:
        logger.info("\nLoading orders from database...")
        orders = load_orders_from_db(
            target_date=target_date,
            store_code=args.store,
            status='READY' if args.ready_only else None
        )
    else:
        logger.info(f"\nParsing orders from: {args.orders}")
        orders_path = Path(args.orders).expanduser()
        if not orders_path.exists():
            logger.error(f"Orders file not found: {orders_path}")
            sys.exit(1)

        result = parse_active_orders(orders_path)
        orders = result.orders

        if args.ready_only:
            orders = filter_for_shipment(orders, target_date=target_date)
            logger.info(f"Filtered to {len(orders)} ready orders")

        if args.store:
            orders = [o for o in orders if o.get('store_code') == args.store]
            logger.info(f"Filtered to store {args.store}: {len(orders)} orders")

    if not orders:
        logger.warning("No orders to process")
        sys.exit(0)

    logger.info(f"Orders to process: {len(orders)}")

    # Load waybills
    if args.waybills:
        waybills_path = Path(args.waybills).expanduser()
        if not waybills_path.exists():
            logger.error(f"Waybills ZIP not found: {waybills_path}")
            sys.exit(1)

        # Create temp directory for extraction
        temp_dir = Path(tempfile.mkdtemp(prefix="waybills_"))
        logger.info(f"Extracting waybills from ZIP...")

        try:
            waybill_map = extract_waybills_from_zip(waybills_path, temp_dir)
        except Exception as e:
            logger.error(f"Failed to extract waybills: {e}")
            sys.exit(1)
    else:
        waybills_dir = Path(args.waybills_dir).expanduser()
        if not waybills_dir.exists():
            logger.error(f"Waybills directory not found: {waybills_dir}")
            sys.exit(1)

        logger.info(f"Loading waybills from directory...")
        waybill_map = extract_waybills_from_dir(waybills_dir)
        temp_dir = None  # No cleanup needed

    logger.info(f"Waybills available: {len(waybill_map)}")

    # Group orders
    logger.info("\nGrouping orders for shipment...")
    groups, missing_ids = group_orders_for_shipment(orders, waybill_map)

    logger.info(f"  Groups created: {len(groups)}")
    logger.info(f"  Missing waybills: {len(missing_ids)}")

    # Count by type
    by_type = {}
    for g in groups:
        by_type[g.group_type] = by_type.get(g.group_type, 0) + 1

    for gtype, count in sorted(by_type.items()):
        logger.info(f"    {gtype}: {count}")

    # Dry run mode
    if args.dry_run:
        logger.info("\n[DRY RUN] Would create:")
        for group in groups[:10]:
            logger.info(f"  {group.group_type}: {group.output_filename}")
        if len(groups) > 10:
            logger.info(f"  ... and {len(groups) - 10} more")
        if missing_ids:
            logger.info(f"\nMissing waybills for: {missing_ids[:5]}")
        sys.exit(0)

    # Build output
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\nBuilding output in: {output_dir}")

    stats = build_grouped_output(
        groups,
        output_dir,
        merge_multi=not args.no_merge
    )
    stats['missing'] = len(missing_ids)

    # Write reports
    write_manifest(groups, output_dir / "manifest.csv")
    logger.info("  - manifest.csv written")

    if missing_ids:
        write_missing_orders(missing_ids, output_dir / "missing_orders.csv")
        logger.info("  - missing_orders.csv written")

    duration = (datetime.now() - start_time).total_seconds()
    write_build_log(stats, output_dir / "build_log.csv", duration)
    logger.info("  - build_log.csv written")

    # Cleanup temp directory
    if temp_dir and temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir)

    # Report results
    logger.info("\n" + "=" * 60)
    logger.info("BUILD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"  NORMAL singles: {stats.get('normal', 0)}")
    logger.info(f"  MULTI_LINE bundles: {stats.get('multi_line', 0)}")
    logger.info(f"  MULTI_QTY bundles: {stats.get('multi_qty', 0)}")
    logger.info(f"  Errors: {stats.get('errors', 0)}")
    logger.info(f"  Missing waybills: {stats.get('missing', 0)}")
    logger.info(f"  Duration: {duration:.2f}s")

    if stats.get('errors', 0) > 0:
        logger.warning("Some bundles had errors. Check logs above.")
        sys.exit(1)

    if missing_ids:
        logger.warning(
            f"{len(missing_ids)} orders missing waybills. "
            f"See missing_orders.csv for details."
        )


if __name__ == "__main__":
    main()
