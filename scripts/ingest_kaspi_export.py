#!/usr/bin/env python3
"""
Ingest Kaspi ActiveOrders Excel exports into fact_orders_kaspi.

Phase 9.5 TASK-113: CLI to ingest ActiveOrders exports for order tracking.

Usage:
    # Single file
    python scripts/ingest_kaspi_export.py data_raw/ActiveOrders_2025-12-06.xlsx

    # Directory scan (all ActiveOrders*.xlsx)
    python scripts/ingest_kaspi_export.py --scan-dir ~/Downloads

    # With date filter
    python scripts/ingest_kaspi_export.py --scan-dir ~/Downloads --target-date 2025-12-06

    # Dry run
    python scripts/ingest_kaspi_export.py data_raw/ActiveOrders.xlsx --dry-run

    # Auto-create missing SKUs
    python scripts/ingest_kaspi_export.py data_raw/ActiveOrders.xlsx --auto-create-sku

Features:
    - Parses ActiveOrders Excel files (Russian column headers)
    - UPSERT on (order_id, sku_id, store_code) for idempotency
    - Handles multi-line orders correctly
    - Optional filtering for shipment-ready orders only
    - Auto-creates missing SKUs in dim_sku_size (with warning)
"""
import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, init_db  # noqa: E402
from core.parsers.kaspi_export_parser import (  # noqa: E402
    parse_active_orders,
    filter_for_shipment,
    get_dedup_key,
    ParseResult,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def ensure_db_ready():
    """Ensure database exists and schema is initialized."""
    db_path = Path(__file__).parent.parent / "db" / "app.db"
    if not db_path.exists():
        logger.info("Database not found, initializing...")
        init_db()


def find_active_orders_files(scan_dir: Path) -> list[Path]:
    """
    Find all ActiveOrders*.xlsx files in directory.

    Args:
        scan_dir: Directory to scan

    Returns:
        List of matching file paths, sorted by modification time (newest first)
    """
    if not scan_dir.exists():
        logger.warning(f"Scan directory not found: {scan_dir}")
        return []

    files = list(scan_dir.glob("ActiveOrders*.xlsx"))

    # Filter out temp files (Excel creates ~$ActiveOrders*.xlsx)
    files = [f for f in files if not f.name.startswith("~$")]

    # Sort by modification time (newest first)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return files


def ingest_orders(
    orders: list[dict],
    conn,
    auto_create_sku: bool = False,
) -> dict:
    """
    Ingest parsed orders into fact_orders_kaspi.

    Args:
        orders: List of parsed order dicts from kaspi_export_parser
        conn: Database connection
        auto_create_sku: If True, auto-create missing dim_sku_size entries

    Returns:
        dict with counts: inserted, updated, skipped, errors
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    missing_skus = set()
    created_skus = set()

    # First pass: auto-create missing SKUs if requested
    if auto_create_sku:
        for order in orders:
            sku_id = order.get("sku_id")
            sku_key = order.get("sku_key")

            if sku_id and sku_key and sku_id not in created_skus:
                cursor = conn.execute(
                    "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
                    (sku_id,)
                )
                if not cursor.fetchone():
                    try:
                        _auto_create_sku(conn, order)
                        created_skus.add(sku_id)
                    except Exception as e:
                        logger.warning(f"Failed to auto-create SKU {sku_id}: {e}")

        if created_skus:
            logger.info(f"Auto-created {len(created_skus)} new SKUs")

    # Second pass: ingest orders
    for order in orders:
        try:
            # Use sku_id for dedup, fallback to kaspi_offer_name if sku_id not extracted
            dedup_sku = order.get("sku_id") or order.get("kaspi_offer_name")

            # Check if order already exists
            cursor = conn.execute("""
                SELECT id, internal_status FROM fact_orders_kaspi
                WHERE order_id = ?
                  AND (sku_id = ? OR (sku_id IS NULL AND kaspi_offer_name = ?))
                  AND store_code = ?
            """, (
                order["order_id"],
                order.get("sku_id"),
                order.get("kaspi_offer_name"),
                order["store_code"]
            ))

            existing = cursor.fetchone()

            if existing:
                # Update existing record (but preserve certain fields)
                conn.execute("""
                    UPDATE fact_orders_kaspi SET
                        kaspi_offer_name = COALESCE(?, kaspi_offer_name),
                        sku_key = COALESCE(?, sku_key),
                        sku_id = COALESCE(?, sku_id),
                        my_size = COALESCE(?, my_size),
                        quantity = ?,
                        unit_price_kzt = ?,
                        created_at = COALESCE(?, created_at),
                        planned_shipment_date = ?,
                        kaspi_status = ?,
                        internal_status = ?,
                        source = ?,
                        source_file = ?
                    WHERE id = ?
                """, (
                    order.get("kaspi_offer_name"),
                    order.get("sku_key"),
                    order.get("sku_id"),
                    order.get("my_size"),
                    order.get("quantity", 1),
                    order.get("unit_price_kzt"),
                    order.get("created_at"),
                    order.get("planned_shipment_date"),
                    order.get("kaspi_status"),
                    order.get("internal_status", "NEW"),
                    order.get("source", "EXCEL_EXPORT"),
                    order.get("source_file"),
                    existing["id"],
                ))
                stats["updated"] += 1
            else:
                # Track missing SKUs for warning
                if order.get("sku_id"):
                    cursor = conn.execute(
                        "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
                        (order["sku_id"],)
                    )
                    if not cursor.fetchone():
                        missing_skus.add(order["sku_id"])

                # Insert new order
                conn.execute("""
                    INSERT INTO fact_orders_kaspi (
                        order_id, store_code, channel_code,
                        kaspi_offer_name, sku_key, sku_id, my_size,
                        quantity, unit_price_kzt,
                        created_at, planned_shipment_date,
                        kaspi_status, internal_status,
                        source, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order["order_id"],
                    order["store_code"],
                    order.get("channel_code", "KSP"),
                    order.get("kaspi_offer_name"),
                    order.get("sku_key"),
                    order.get("sku_id"),
                    order.get("my_size"),
                    order.get("quantity", 1),
                    order.get("unit_price_kzt"),
                    order.get("created_at"),
                    order.get("planned_shipment_date"),
                    order.get("kaspi_status"),
                    order.get("internal_status", "NEW"),
                    order.get("source", "EXCEL_EXPORT"),
                    order.get("source_file"),
                ))
                stats["inserted"] += 1

        except Exception as e:
            logger.error(f"Error ingesting order {order.get('order_id')}: {e}")
            stats["errors"] += 1

    # Warn about missing SKUs
    if missing_skus:
        logger.warning(
            f"Found {len(missing_skus)} orders with unknown sku_id. "
            f"Use --auto-create-sku to auto-create, or add to dim_sku_size."
        )
        if len(missing_skus) <= 10:
            for sku in sorted(missing_skus):
                logger.warning(f"  - {sku}")

    return stats


def _auto_create_sku(conn, order: dict) -> bool:
    """
    Auto-create missing SKU in dim_sku and dim_sku_size.

    Returns True if SKU was created or already exists.
    """
    sku_key = order.get("sku_key")
    sku_id = order.get("sku_id")
    my_size = order.get("my_size")

    if not sku_key or not sku_id:
        return False

    # Check if sku_key exists in dim_sku, create if not
    cursor = conn.execute(
        "SELECT 1 FROM dim_sku WHERE sku_key = ?",
        (sku_key,)
    )
    if not cursor.fetchone():
        # Extract model and color from sku_key
        parts = sku_key.split("_")
        product_type = parts[0] if len(parts) > 0 else "CL"
        model = parts[3] if len(parts) > 3 else "UNKNOWN"
        color = parts[4] if len(parts) > 4 else None
        gender = parts[2] if len(parts) > 2 else "MEN"

        conn.execute("""
            INSERT INTO dim_sku (
                sku_key, model, color, product_type,
                base_cost_cny, weight_kg, category, gender
            ) VALUES (?, ?, ?, ?, 0, 0, NULL, ?)
        """, (sku_key, model, color, product_type, gender))
        logger.info(f"Auto-created dim_sku: {sku_key}")

    # Check if sku_id exists in dim_sku_size
    cursor = conn.execute(
        "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
        (sku_id,)
    )
    if not cursor.fetchone():
        conn.execute("""
            INSERT INTO dim_sku_size (sku_id, sku_key, my_size)
            VALUES (?, ?, ?)
        """, (sku_id, sku_key, my_size))
        logger.info(f"Auto-created dim_sku_size: {sku_id}")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest Kaspi ActiveOrders Excel into fact_orders_kaspi"
    )
    parser.add_argument(
        "file",
        type=str,
        nargs="?",
        help="Path to ActiveOrders Excel file"
    )
    parser.add_argument(
        "--scan-dir",
        type=str,
        help="Directory to scan for ActiveOrders*.xlsx files"
    )
    parser.add_argument(
        "--target-date",
        type=str,
        help="Filter for orders with planned_date <= this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--ready-only",
        action="store_true",
        help="Only ingest orders ready for shipment (status=READY)"
    )
    parser.add_argument(
        "--auto-create-sku",
        action="store_true",
        help="Auto-create missing SKUs in dim_sku_size"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse file but don't insert into database"
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

    # Determine files to process
    files_to_process = []

    if args.scan_dir:
        scan_path = Path(args.scan_dir).expanduser()
        files_to_process = find_active_orders_files(scan_path)
        if not files_to_process:
            logger.error(f"No ActiveOrders*.xlsx files found in {scan_path}")
            sys.exit(1)
        logger.info(f"Found {len(files_to_process)} file(s) to process")
    elif args.file:
        file_path = Path(args.file).expanduser()
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
        files_to_process = [file_path]
    else:
        parser.print_help()
        sys.exit(1)

    # Parse target date if provided
    target_date: Optional[date] = None
    if args.target_date:
        try:
            target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.target_date}. Use YYYY-MM-DD")
            sys.exit(1)

    logger.info("=" * 60)
    logger.info("Kaspi Export Ingestion")
    logger.info("=" * 60)

    # Ensure database is ready
    ensure_db_ready()

    total_stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
    total_orders = 0

    for file_path in files_to_process:
        logger.info(f"\nProcessing: {file_path.name}")

        # Parse the file
        try:
            result: ParseResult = parse_active_orders(file_path)
            logger.info(f"  Parsed: {result.parsed_rows}/{result.total_rows} rows")

            if result.errors:
                for err in result.errors[:3]:
                    logger.warning(f"  Parse error: {err}")
        except ValueError as e:
            logger.error(f"  Parse error: {e}")
            continue
        except Exception as e:
            logger.error(f"  Unexpected error: {e}")
            continue

        orders = result.orders

        # Apply filters
        if args.ready_only or target_date:
            orders = filter_for_shipment(
                orders,
                target_date=target_date or date.today()
            )
            logger.info(f"  Ready for shipment: {len(orders)}")

        if not orders:
            logger.info("  No orders to ingest")
            continue

        total_orders += len(orders)

        # Dry run mode
        if args.dry_run:
            logger.info(f"  [DRY RUN] Would ingest {len(orders)} orders")
            if orders:
                logger.debug("  Sample order:")
                for k, v in list(orders[0].items())[:8]:
                    logger.debug(f"    {k}: {v}")
            continue

        # Ingest into database
        with get_db() as conn:
            stats = ingest_orders(orders, conn, args.auto_create_sku)

        logger.info(f"  Inserted: {stats['inserted']}, Updated: {stats['updated']}, Errors: {stats['errors']}")

        # Accumulate stats
        for key in total_stats:
            total_stats[key] += stats[key]

    # Report results
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Files processed: {len(files_to_process)}")
    logger.info(f"Total orders: {total_orders}")

    if not args.dry_run:
        logger.info(f"  Inserted: {total_stats['inserted']}")
        logger.info(f"  Updated:  {total_stats['updated']}")
        logger.info(f"  Errors:   {total_stats['errors']}")

        logger.info(
            f"INGEST_REPORT total={total_orders} inserted={total_stats['inserted']} "
            f"updated={total_stats['updated']} errors={total_stats['errors']}"
        )

        if total_stats["errors"] > 0:
            logger.warning("Some records failed to ingest. Check logs above.")
            sys.exit(1)

    logger.info("\nDone!")


if __name__ == "__main__":
    main()
