"""
Ingest Kaspi ActiveOrders Excel files into fact_sales_raw.

CLI: python scripts/ingest_active_orders.py <excel_file> [--store STORE_CODE]

Features:
- Parses ActiveOrders Excel files (Russian column headers)
- UPSERT on (order_id, sku_id, store_code) for idempotency
- Logs ingested count, skipped duplicates, errors
- Auto-creates missing SKUs in dim_sku_size (with warning)
"""
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, init_db  # noqa: E402
from core.parsers.kaspi_parser import parse_active_orders  # noqa: E402

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


def ingest_records(
    records: list[dict],
    conn,
    auto_create_sku: bool = False,
) -> dict:
    """
    Ingest parsed records into fact_sales_raw.

    Args:
        records: List of parsed records from kaspi_parser
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
        for record in records:
            sku_id = record.get("sku_id")
            sku_key = record.get("sku_key")

            if sku_id and sku_key and sku_id not in created_skus:
                cursor = conn.execute(
                    "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
                    (sku_id,)
                )
                if not cursor.fetchone():
                    try:
                        _auto_create_sku(conn, record)
                        created_skus.add(sku_id)
                    except Exception as e:
                        logger.warning(f"Failed to auto-create SKU {sku_id}: {e}")

        if created_skus:
            logger.info(f"Auto-created {len(created_skus)} new SKUs")

    # Second pass: ingest records
    for record in records:
        try:
            # Check if record exists
            cursor = conn.execute("""
                SELECT id FROM fact_sales_raw
                WHERE order_id = ? AND sku_id = ? AND store_code = ?
            """, (record["order_id"], record["sku_id"], record["store_code"]))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                conn.execute("""
                    UPDATE fact_sales_raw SET
                        order_date = ?,
                        kaspi_offer = ?,
                        kaspi_article = ?,
                        quantity = ?,
                        sell_price_kzt = ?,
                        delivery_fee_seller = ?,
                        delivery_fee_buyer = ?,
                        order_status = ?,
                        channel = ?,
                        source_file = ?,
                        ingested_at = datetime('now')
                    WHERE id = ?
                """, (
                    record["order_date"],
                    record["kaspi_offer"],
                    record["kaspi_article"],
                    record["quantity"],
                    record["sell_price_kzt"],
                    record["delivery_fee_seller"],
                    record["delivery_fee_buyer"],
                    record["order_status"],
                    record["channel"],
                    record["source_file"],
                    existing["id"],
                ))
                stats["updated"] += 1
            else:
                # Track missing SKUs for warning
                if record["sku_id"]:
                    cursor = conn.execute(
                        "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
                        (record["sku_id"],)
                    )
                    if not cursor.fetchone():
                        missing_skus.add(record["sku_id"])

                # Insert new record
                conn.execute("""
                    INSERT INTO fact_sales_raw (
                        order_id, store_code, order_date, kaspi_offer,
                        kaspi_article, sku_id, quantity, sell_price_kzt,
                        delivery_fee_seller, delivery_fee_buyer, order_status,
                        channel, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["order_id"],
                    record["store_code"],
                    record["order_date"],
                    record["kaspi_offer"],
                    record["kaspi_article"],
                    record["sku_id"],
                    record["quantity"],
                    record["sell_price_kzt"],
                    record["delivery_fee_seller"],
                    record["delivery_fee_buyer"],
                    record["order_status"],
                    record["channel"],
                    record["source_file"],
                ))
                stats["inserted"] += 1

        except Exception as e:
            logger.error(f"Error ingesting order {record.get('order_id')}: {e}")
            stats["errors"] += 1

    # Warn about missing SKUs
    if missing_skus:
        logger.warning(
            f"Found {len(missing_skus)} orders with unknown sku_id. "
            f"These need to be added to dim_sku_size."
        )
        if len(missing_skus) <= 10:
            for sku in sorted(missing_skus):
                logger.warning(f"  - {sku}")

    return stats


def _auto_create_sku(conn, record: dict) -> bool:
    """
    Auto-create missing SKU in dim_sku and dim_sku_size.

    Returns True if SKU was created or already exists.
    """
    sku_key = record.get("sku_key")
    sku_id = record.get("sku_id")
    my_size = record.get("my_size")
    product_type = record.get("product_type") or "CL"

    if not sku_key or not sku_id:
        return False

    # Check if sku_key exists, create if not
    cursor = conn.execute(
        "SELECT 1 FROM dim_sku WHERE sku_key = ?",
        (sku_key,)
    )
    if not cursor.fetchone():
        # Extract model and color from sku_key
        parts = sku_key.split("_")
        model = parts[3] if len(parts) > 3 else "UNKNOWN"
        color = parts[4] if len(parts) > 4 else None

        conn.execute("""
            INSERT INTO dim_sku (
                sku_key, model, color, product_type,
                base_cost_cny, weight_kg, category, gender
            ) VALUES (?, ?, ?, ?, 0, 0, NULL, 'MEN')
        """, (sku_key, model, color, product_type))
        logger.info(f"Auto-created dim_sku: {sku_key}")

    # Check if sku_id exists in dim_sku_size
    cursor = conn.execute(
        "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
        (sku_id,)
    )
    if not cursor.fetchone():
        # Create dim_sku_size
        conn.execute("""
            INSERT INTO dim_sku_size (sku_id, sku_key, my_size)
            VALUES (?, ?, ?)
        """, (sku_id, sku_key, my_size))
        logger.info(f"Auto-created dim_sku_size: {sku_id}")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest Kaspi ActiveOrders Excel into fact_sales_raw"
    )
    parser.add_argument(
        "file",
        type=str,
        help="Path to ActiveOrders Excel file"
    )
    parser.add_argument(
        "--store",
        type=str,
        default="UNIVERSAL",
        help="Store code (default: UNIVERSAL)"
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
        "--skip-validation",
        action="store_true",
        help="Skip column validation (for non-standard files)"
    )

    args = parser.parse_args()

    # Validate file exists
    file_path = Path(args.file)
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        sys.exit(1)

    logger.info(f"=== Ingest ActiveOrders ===")
    logger.info(f"File: {file_path.name}")
    logger.info(f"Store: {args.store}")

    # Ensure database is ready
    ensure_db_ready()

    # Parse the file
    logger.info("Parsing Excel file...")
    try:
        records = parse_active_orders(
            file_path,
            args.store,
            validate=not args.skip_validation
        )
        logger.info(f"Parsed {len(records)} records")
    except ValueError as e:
        logger.error(f"Parse error: {e}")
        sys.exit(1)

    if not records:
        logger.warning("No records to ingest")
        sys.exit(0)

    # Dry run mode
    if args.dry_run:
        logger.info("Dry run mode - no database changes")
        logger.info(f"Would ingest {len(records)} records")
        # Show sample
        if records:
            logger.info("Sample record:")
            for k, v in list(records[0].items())[:8]:
                logger.info(f"  {k}: {v}")
        sys.exit(0)

    # Ingest into database
    logger.info("Ingesting into database...")
    with get_db() as conn:
        stats = ingest_records(records, conn, args.auto_create_sku)

    # Report results
    logger.info("=== Results ===")
    logger.info(f"  Inserted: {stats['inserted']}")
    logger.info(f"  Updated:  {stats['updated']}")
    logger.info(f"  Errors:   {stats['errors']}")

    if stats["errors"] > 0:
        logger.warning("Some records failed to ingest. Check logs above.")
        sys.exit(1)

    logger.info("✅ Ingestion complete!")


if __name__ == "__main__":
    main()
