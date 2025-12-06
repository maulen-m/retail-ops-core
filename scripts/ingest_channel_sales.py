#!/usr/bin/env python3
"""
Unified channel sales ingestion for Phase 8.

Handles both Kaspi and WB sales imports with channel-aware processing.

Usage:
    python scripts/ingest_channel_sales.py --channel KSP path/to/kaspi_sales.xlsx
    python scripts/ingest_channel_sales.py --channel WB path/to/wb_sales.xlsx
    python scripts/ingest_channel_sales.py --channel WB --store wb_fbo path/to/wb_sales.xlsx

Features:
- Parses channel-specific Excel formats
- UPSERT on (order_id, kaspi_offer_name, sku_id, store_code) for idempotency
- Calculates channel-specific economics (Kaspi vs WB)
- Logs ingested counts, errors, and skipped records
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.kaspi_parser import parse_active_orders  # noqa: E402
from core.parsers.wb_parser import parse_wb_sales, validate_wb_record  # noqa: E402
from core.calc.economics import calc_net_rev, calc_cogs, calc_profit  # noqa: E402
from core.calc.wb_economics import calc_wb_full_economics  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def get_channel_config(conn: sqlite3.Connection, channel_code: str) -> dict:
    """Get channel configuration from dim_channel."""
    cursor = conn.execute("""
        SELECT
            commission_pct,
            vat_pct,
            logistics_fee_rub,
            fx_rate_to_kzt,
            payment_delay_days
        FROM dim_channel
        WHERE channel_code = ?
    """, (channel_code,))

    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Channel {channel_code} not configured. Run migrate_010.py first.")

    return {
        "commission_pct": row[0],
        "vat_pct": row[1],
        "logistics_fee_rub": row[2],
        "fx_rate_to_kzt": row[3],
        "payment_delay_days": row[4],
    }


def get_cogs_lookup(conn: sqlite3.Connection) -> dict:
    """Get COGS lookup from dim_sku."""
    cursor = conn.execute("SELECT sku_key, cogs_kzt FROM dim_sku WHERE cogs_kzt > 0")
    return dict(cursor.fetchall())


def ingest_kaspi_sales(file_path: Path, store_code: str = "kaspi_main") -> dict:
    """
    Ingest Kaspi sales file.

    This delegates to the existing Kaspi ingestion logic for compatibility.
    """
    # Import here to avoid circular import
    from scripts.ingest_active_orders import ingest_file
    return ingest_file(str(file_path), store_code)


def ingest_wb_sales(file_path: Path, store_code: str = "wb_fbo") -> dict:
    """
    Ingest WB sales file.

    Returns:
        Summary dict with counts
    """
    conn = sqlite3.connect(DB_PATH)

    # Get channel config
    config = get_channel_config(conn, "WB")
    fx_rate = config["fx_rate_to_kzt"]
    logistics_fee = config["logistics_fee_rub"]
    commission_pct = config["commission_pct"]
    vat_pct = config["vat_pct"]

    # Get COGS lookup
    cogs_lookup = get_cogs_lookup(conn)

    # Parse file
    try:
        records = parse_wb_sales(file_path, store_code)
    except ValueError as e:
        logger.error(f"Parse error: {e}")
        conn.close()
        return {
            "file": file_path.name,
            "channel": "WB",
            "total_parsed": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [str(e)],
        }

    logger.info(f"Parsed {len(records)} records from {file_path.name}")

    inserted = 0
    updated = 0
    skipped = 0
    errors = []

    for record in records:
        # Validate record
        valid, error = validate_wb_record(record)
        if not valid:
            errors.append(f"{record.get('order_id')}: {error}")
            skipped += 1
            continue

        # Get COGS
        cogs_kzt = cogs_lookup.get(record["sku_key"], 0)
        if cogs_kzt == 0:
            errors.append(f"{record['sku_key']}: Missing COGS in dim_sku")
            skipped += 1
            continue

        # Calculate economics
        if record["is_return"]:
            # Returns have negative economics
            net_rev_kzt = 0
            profit_kzt = -cogs_kzt  # Return = lose COGS until item resold
            sell_price_kzt = 0
            qty = -1
        else:
            econ = calc_wb_full_economics(
                seller_price_rub=record["seller_price_rub"],
                cogs_kzt=cogs_kzt,
                fx_rub_kzt=fx_rate,
                logistics_fee_rub=logistics_fee,
                commission_pct=commission_pct,
                tax_pct=vat_pct,
            )
            net_rev_kzt = econ.final_revenue_kzt
            profit_kzt = econ.profit_kzt
            sell_price_kzt = record["seller_price_rub"] * fx_rate
            qty = 1

        # Upsert to fact_sales
        try:
            cursor = conn.execute("""
                SELECT id FROM fact_sales
                WHERE order_id = ?
                  AND kaspi_offer_name = ?
                  AND sku_id = ?
                  AND store_code = ?
            """, (
                record["order_id"],
                record["product_name"],
                record["sku_id"],
                store_code,
            ))

            existing = cursor.fetchone()

            if existing:
                # Update
                conn.execute("""
                    UPDATE fact_sales SET
                        net_rev_kzt = ?,
                        cogs_kzt = ?,
                        profit_kzt = ?,
                        quantity = ?,
                        channel_code = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    net_rev_kzt,
                    cogs_kzt,
                    profit_kzt,
                    qty,
                    "WB",
                    datetime.now().isoformat(),
                    existing[0],
                ))
                updated += 1
            else:
                # Insert
                conn.execute("""
                    INSERT INTO fact_sales (
                        order_id, order_date, channel_code, store_code,
                        sku_key, sku_id, my_size,
                        kaspi_offer_name, quantity,
                        sell_price_kzt, net_rev_kzt, cogs_kzt, profit_kzt,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record["order_id"],
                    record["sale_date"] or record["order_date"],
                    "WB",
                    store_code,
                    record["sku_key"],
                    record["sku_id"],
                    record["my_size"],
                    record["product_name"],  # Use product_name as kaspi_offer_name
                    qty,
                    sell_price_kzt,
                    net_rev_kzt,
                    cogs_kzt,
                    profit_kzt,
                    datetime.now().isoformat(),
                ))
                inserted += 1

        except sqlite3.IntegrityError as e:
            errors.append(f"{record['order_id']}: {str(e)}")
            skipped += 1

    conn.commit()
    conn.close()

    return {
        "file": file_path.name,
        "channel": "WB",
        "total_parsed": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:10],  # First 10 errors only
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest channel sales data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Ingest Kaspi sales
    python scripts/ingest_channel_sales.py --channel KSP data_raw/ActiveOrders.xlsx

    # Ingest WB sales
    python scripts/ingest_channel_sales.py --channel WB data_raw/wb_sales.xlsx

    # Ingest WB with specific store
    python scripts/ingest_channel_sales.py --channel WB --store wb_fbo data_raw/wb.xlsx
        """,
    )
    parser.add_argument("file", type=Path, help="Sales file to import")
    parser.add_argument(
        "--channel",
        type=str,
        choices=["KSP", "WB"],
        required=True,
        help="Channel code (KSP=Kaspi, WB=Wildberries)",
    )
    parser.add_argument(
        "--store",
        type=str,
        default=None,
        help="Store code (default: kaspi_main or wb_fbo)",
    )

    args = parser.parse_args()

    if not args.file.exists():
        logger.error(f"File not found: {args.file}")
        sys.exit(1)

    # Set default store
    store = args.store or ("kaspi_main" if args.channel == "KSP" else "wb_fbo")

    print()
    print("=" * 60)
    print(f"CHANNEL SALES INGESTION — {args.channel}")
    print("=" * 60)
    print(f"File:    {args.file}")
    print(f"Store:   {store}")
    print(f"Channel: {args.channel}")

    if args.channel == "KSP":
        result = ingest_kaspi_sales(args.file, store)
    else:
        result = ingest_wb_sales(args.file, store)

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Parsed:   {result.get('total_parsed', 'N/A')}")
    print(f"Inserted: {result.get('inserted', 0)}")
    print(f"Updated:  {result.get('updated', 0)}")
    print(f"Skipped:  {result.get('skipped', 0)}")

    if result.get("errors"):
        print(f"\nFirst {len(result['errors'])} errors:")
        for err in result["errors"]:
            print(f"  - {err}")

    print()


if __name__ == "__main__":
    main()
