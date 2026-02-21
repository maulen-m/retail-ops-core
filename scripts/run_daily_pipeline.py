#!/usr/bin/env python3
"""
Daily Pipeline Orchestrator: Run complete daily inventory workflow.

This script orchestrates the full daily pipeline:
1. Ingest inventory snapshot (from Excel)
2. Ingest active orders (from Kaspi Excel)
3. Transform to fact_sales with economics
4. Build daily aggregates
5. Compute SKU metrics
6. Export reports (po_suggestions.csv, inventory_snapshot.csv)
7. Send Telegram alerts for REORDER SKUs

Usage:
    python scripts/run_daily_pipeline.py                              # Full pipeline
    python scripts/run_daily_pipeline.py --inventory excel/stock.xlsx # Specify inventory file
    python scripts/run_daily_pipeline.py --skip-ingest                # Just recalculate
    python scripts/run_daily_pipeline.py --no-alerts                  # Skip Telegram
    python scripts/run_daily_pipeline.py --dry-run                    # Simulate only
"""

import argparse
import glob
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from core.db import get_db


def step_ingest_inventory(
    inventory_file: Optional[str],
    date: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 1: Ingest inventory snapshot."""
    from scripts.ingest_inventory_snapshot import ingest_inventory

    if inventory_file is None:
        # Single-truth default: anchored stock snapshot
        anchor_file = "config/anchors/STOCK_SNAPSHOT_LATEST.xlsx"
        if os.path.exists(anchor_file):
            inventory_file = anchor_file
        else:
            # Legacy fallback (deprecated)
            pattern = "excel/Current_stock_*.xlsx"
            files = sorted(glob.glob(pattern), reverse=True)
            if not files:
                return {"skipped": True, "reason": "No inventory file found"}
            inventory_file = files[0]

    if not os.path.exists(inventory_file):
        return {"skipped": True, "reason": f"File not found: {inventory_file}"}

    result = ingest_inventory(
        filepath=inventory_file,
        snapshot_date=date,
        dry_run=dry_run,
        verbose=verbose,
    )
    return result


def step_ingest_orders(
    orders_file: Optional[str],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 2: Ingest active orders."""
    # Import here to avoid circular imports
    try:
        from scripts.ingest_active_orders import process_file
    except ImportError:
        return {"skipped": True, "reason": "ingest_active_orders not available"}

    if orders_file is None:
        # Find latest orders file
        pattern = "data_raw/ActiveOrders_*.xlsx"
        files = sorted(glob.glob(pattern), reverse=True)
        if not files:
            return {"skipped": True, "reason": "No orders file found"}
        orders_file = files[0]

    if not os.path.exists(orders_file):
        return {"skipped": True, "reason": f"File not found: {orders_file}"}

    result = process_file(orders_file, dry_run=dry_run, verbose=verbose)
    return result


def step_ingest_kaspi_exports(
    scan_dir: Optional[str],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 2b: Ingest Kaspi exports to fact_orders_kaspi (Phase 9.5)."""
    from core.parsers.kaspi_export_parser import parse_active_orders, filter_for_shipment
    from scripts.ingest_kaspi_export import ingest_orders, find_active_orders_files

    # Determine scan directory
    if scan_dir is None:
        scan_dir = "data_raw"

    scan_path = Path(scan_dir)
    if not scan_path.exists():
        return {"skipped": True, "reason": f"Scan directory not found: {scan_dir}"}

    # Find ActiveOrders files
    files = find_active_orders_files(scan_path)
    if not files:
        return {"skipped": True, "reason": "No ActiveOrders*.xlsx files found"}

    # Process only the most recent file to avoid duplicates
    latest_file = files[0]

    try:
        result = parse_active_orders(latest_file)

        if verbose:
            print(f"      Parsed {result.parsed_rows}/{result.total_rows} rows from {latest_file.name}")

        if dry_run:
            return {
                "file": latest_file.name,
                "parsed": result.parsed_rows,
                "dry_run": True,
            }

        # Ingest into database
        with get_db() as conn:
            stats = ingest_orders(result.orders, conn)

        return {
            "file": latest_file.name,
            "parsed": result.parsed_rows,
            "inserted": stats.get("inserted", 0),
            "updated": stats.get("updated", 0),
            "errors": stats.get("errors", 0),
        }

    except Exception as e:
        return {"error": str(e)}


def step_transform_sales(dry_run: bool, verbose: bool) -> dict:
    """Step 3: Transform fact_sales_raw to fact_sales."""
    try:
        from scripts.import_legacy_sales import process_sales
    except ImportError:
        return {"skipped": True, "reason": "import_legacy_sales not available"}

    result = process_sales(dry_run=dry_run, verbose=verbose)
    return result


def step_build_aggregates(date: str, dry_run: bool, verbose: bool) -> dict:
    """Step 4: Build daily aggregates."""
    try:
        from scripts.build_daily_aggregates import build_all_aggregates
    except ImportError:
        return {"skipped": True, "reason": "build_daily_aggregates not available"}

    result = build_all_aggregates(
        from_date=None,  # Rebuild all
        to_date=None,
        dry_run=dry_run,
        verbose=verbose,
    )
    return result


def step_compute_metrics(dry_run: bool, verbose: bool) -> dict:
    """Step 5: Compute SKU metrics."""
    from scripts.run_sku_metrics import run_metrics

    result = run_metrics(
        days=30,
        csv_path=None,
        dry_run=dry_run,
        verbose=verbose,
    )
    return result


def step_export_reports(date: str, dry_run: bool, verbose: bool) -> dict:
    """Step 6: Export reports."""
    from scripts.export_po_suggestions import generate_po_suggestions, export_to_csv

    output_dir = f"exports/{date}"
    results = {}

    with get_db() as conn:
        # PO suggestions
        po_records = generate_po_suggestions(conn, reorder_only=False, verbose=verbose)
        if not dry_run and po_records:
            po_path = f"{output_dir}/po_suggestions.csv"
            count = export_to_csv(po_records, po_path)
            results["po_suggestions"] = count
        else:
            results["po_suggestions"] = len(po_records)

        # Inventory snapshot export
        cursor = conn.execute(
            """
            SELECT sku_key, my_size, current_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
            ORDER BY sku_key, my_size
            """,
            (date,)
        )
        inv_records = [
            {"sku_key": r[0], "my_size": r[1], "current_stock": r[2]}
            for r in cursor.fetchall()
        ]

        if not dry_run and inv_records:
            import csv
            inv_path = f"{output_dir}/inventory_snapshot.csv"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            with open(inv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["sku_key", "my_size", "current_stock"])
                writer.writeheader()
                writer.writerows(inv_records)
            results["inventory_snapshot"] = len(inv_records)
        else:
            results["inventory_snapshot"] = len(inv_records)

    return results


def step_send_alerts(dry_run: bool, verbose: bool) -> dict:
    """Step 7: Send Telegram alerts."""
    from core.alerts.telegram import send_reorder_alerts

    with get_db() as conn:
        result = send_reorder_alerts(
            conn,
            dry_run=dry_run,
            cooldown_hours=24,
            force=False,
        )
    return result


def step_build_capital_snapshot(
    date: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 5b: Build capital allocation snapshot (TASK-083)."""
    from scripts.build_capital_snapshot import build_snapshot
    from datetime import date as date_type

    if dry_run:
        return {"skipped": True, "reason": "Dry run mode"}

    try:
        snapshot_date = date_type.fromisoformat(date)
        build_snapshot(snapshot_date)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


def step_build_channel_metrics(
    date: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 5c: Build channel metrics (TASK-103)."""
    from core.calc.channel_metrics import calc_channel_metrics_for_date, save_channel_metrics
    from datetime import date as date_type

    if dry_run:
        return {"skipped": True, "reason": "Dry run mode"}

    try:
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "db" / "app.db"
        metric_date = date_type.fromisoformat(date)

        metrics = calc_channel_metrics_for_date(db_path, metric_date)

        if metrics:
            saved = save_channel_metrics(db_path, metrics)
            return {"success": True, "metrics_saved": saved, "sku_count": len(metrics)}
        else:
            return {"success": True, "metrics_saved": 0, "sku_count": 0}

    except Exception as e:
        return {"error": str(e)}


def step_sync_kaspi_orders(
    store_code: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step: Sync Kaspi orders via API (Phase 9.5 - TASK-142)."""
    try:
        from core.sync.order_sync_engine import OrderSyncEngine

        engine = OrderSyncEngine()

        if store_code:
            # Single store sync
            result = engine.sync_store(
                store_code=store_code,
                dry_run=dry_run,
            )
            return {
                "success": result.success,
                "orders_fetched": result.orders_fetched,
                "orders_inserted": result.orders_inserted,
                "orders_updated": result.orders_updated,
                "status_changes": len(result.status_changes),
                "errors": result.errors,
            }
        else:
            # All stores (disabled by default, only UNIVERSAL for testing)
            result = engine.sync_store(
                store_code='UNIVERSAL',
                dry_run=dry_run,
            )
            return {
                "success": result.success,
                "orders_fetched": result.orders_fetched,
                "orders_inserted": result.orders_inserted,
                "orders_updated": result.orders_updated,
                "status_changes": len(result.status_changes),
            }

    except Exception as e:
        return {"error": str(e), "skipped": True}


def step_assign_sizes(
    store_code: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step: Auto-assign sizes to pending orders (Phase 9.5 - TASK-142)."""
    try:
        from core.db import get_db
        from core.calc.size_probability import determine_size
        from pathlib import Path

        db_path = Path(__file__).parent.parent / "db" / "app.db"

        with get_db(db_path) as conn:
            # Get orders needing size assignment
            query = """
                SELECT
                    id, order_id, kaspi_offer_name, sku_key,
                    customer_height_cm, customer_weight_kg
                FROM fact_orders_kaspi
                WHERE assigned_size IS NULL
            """
            params = []
            if store_code:
                query += " AND store_code = ?"
                params.append(store_code)

            rows = conn.execute(query, params).fetchall()

            if not rows:
                return {"success": True, "orders_processed": 0, "note": "No orders need sizing"}

            stats = {"total": len(rows), "assigned": 0, "by_source": {}, "by_confidence": {}}

            for row in rows:
                # Get product type
                product_type = 'CL'
                if row['sku_key']:
                    parts = row['sku_key'].split('_')
                    if parts:
                        product_type = parts[0]

                result = determine_size(
                    order={
                        'kaspi_offer_name': row['kaspi_offer_name'],
                        'sku_key': row['sku_key'],
                        'product_type': product_type,
                    },
                    customer_height=row['customer_height_cm'],
                    customer_weight=row['customer_weight_kg'],
                    db_path=db_path,
                )

                stats['by_source'][result.source] = stats['by_source'].get(result.source, 0) + 1
                stats['by_confidence'][result.confidence] = stats['by_confidence'].get(result.confidence, 0) + 1

                if not dry_run:
                    conn.execute(
                        """
                        UPDATE fact_orders_kaspi
                        SET assigned_size = ?, size_source = ?, size_confidence = ?
                        WHERE id = ?
                        """,
                        (result.size, result.source, result.confidence, row['id'])
                    )
                    stats['assigned'] += 1

            return {
                "success": True,
                "orders_processed": stats['total'],
                "assigned": stats['assigned'],
                "by_source": stats['by_source'],
                "by_confidence": stats['by_confidence'],
            }

    except Exception as e:
        return {"error": str(e), "skipped": True}


def step_download_waybills(
    store_code: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step: Download waybills for orders with waybill URLs (Phase 9.5 - TASK-129)."""
    try:
        from core.waybill.waybill_downloader import WaybillDownloader
        from pathlib import Path

        db_path = Path(__file__).parent.parent / "db" / "app.db"
        output_dir = Path(__file__).parent.parent / "exports" / "waybills"

        downloader = WaybillDownloader(
            store_code=store_code or 'UNIVERSAL',
            db_path=db_path,
            output_dir=output_dir,
        )

        if dry_run:
            # Just count pending
            stats = downloader.get_download_stats()
            return {
                "dry_run": True,
                "pending": stats.get('pending', 0),
                "downloaded": stats.get('downloaded', 0),
            }

        result = downloader.download_pending(limit=50)

        return {
            "success": True,
            "downloaded": result.successful,
            "failed": result.failed,
            "total": result.total,
        }

    except Exception as e:
        return {"error": str(e), "skipped": True}


def step_send_order_alerts(
    store_code: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step: Send order alerts for new orders and ready shipments (Phase 9.5 - TASK-129)."""
    try:
        from core.alerts.order_alerts import send_all_order_alerts
        from pathlib import Path

        db_path = Path(__file__).parent.parent / "db" / "app.db"

        with get_db(db_path) as conn:
            result = send_all_order_alerts(
                conn,
                store_code=store_code or 'UNIVERSAL',
                dry_run=dry_run,
            )

        return {
            "sent": result.get('sent_count', 0),
            "suppressed": result.get('suppressed_count', 0),
            "results": result.get('results', {}),
        }

    except Exception as e:
        return {"error": str(e), "skipped": True}


def run_pipeline(
    date: Optional[str] = None,
    inventory_file: Optional[str] = None,
    orders_file: Optional[str] = None,
    skip_ingest: bool = False,
    no_alerts: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Run the complete daily pipeline.

    Args:
        date: Date for processing (default: today)
        inventory_file: Path to inventory Excel file
        orders_file: Path to orders Excel file
        skip_ingest: Skip ingestion steps (1-4)
        no_alerts: Skip Telegram alerts
        dry_run: Simulate without saving
        verbose: Print progress

    Returns:
        Dict with results for each step
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    start_time = time.time()
    results = {
        "date": date,
        "dry_run": dry_run,
        "steps": {},
    }

    steps = [
        ("ingest_inventory", lambda: step_ingest_inventory(inventory_file, date, dry_run, verbose)),
        ("ingest_orders", lambda: step_ingest_orders(orders_file, dry_run, verbose)),
        ("ingest_kaspi_exports", lambda: step_ingest_kaspi_exports(None, dry_run, verbose)),
        ("sync_kaspi_orders", lambda: step_sync_kaspi_orders('UNIVERSAL', dry_run, verbose)),
        ("assign_sizes", lambda: step_assign_sizes('UNIVERSAL', dry_run, verbose)),
        ("download_waybills", lambda: step_download_waybills('UNIVERSAL', dry_run, verbose)),
        ("transform_sales", lambda: step_transform_sales(dry_run, verbose)),
        ("build_aggregates", lambda: step_build_aggregates(date, dry_run, verbose)),
        ("compute_metrics", lambda: step_compute_metrics(dry_run, verbose)),
        ("build_capital_snapshot", lambda: step_build_capital_snapshot(date, dry_run, verbose)),
        ("build_channel_metrics", lambda: step_build_channel_metrics(date, dry_run, verbose)),
        ("export_reports", lambda: step_export_reports(date, dry_run, verbose)),
        ("send_alerts", lambda: step_send_alerts(dry_run, verbose)),
        ("send_order_alerts", lambda: step_send_order_alerts('UNIVERSAL', dry_run, verbose)),
    ]

    # Skip ingestion steps if requested
    if skip_ingest:
        steps = steps[8:]  # Start from compute_metrics (skip ingest, sync, sizes, waybills, transform, aggregates)

    # Skip alerts if requested
    if no_alerts:
        steps = [s for s in steps if s[0] not in ("send_alerts", "send_order_alerts")]

    for i, (name, step_func) in enumerate(steps, 1):
        if verbose:
            print(f"\n[{i}/{len(steps)}] {name.replace('_', ' ').title()}...")

        try:
            result = step_func()
            results["steps"][name] = result

            if verbose and result:
                if result.get("skipped"):
                    print(f"      Skipped: {result.get('reason', 'unknown')}")
                elif name == "send_alerts":
                    print(f"      Sent: {result.get('sent', 0)}, Suppressed: {result.get('suppressed', 0)}")
                elif name == "export_reports":
                    print(f"      PO suggestions: {result.get('po_suggestions', 0)}")
                    print(f"      Inventory snapshot: {result.get('inventory_snapshot', 0)}")
                elif name == "build_channel_metrics":
                    print(f"      Channel metrics saved: {result.get('metrics_saved', 0)}")
                elif name == "ingest_kaspi_exports":
                    if result.get("dry_run"):
                        print(f"      [DRY RUN] Would ingest {result.get('parsed', 0)} orders")
                    else:
                        print(f"      Inserted: {result.get('inserted', 0)}, Updated: {result.get('updated', 0)}")
                elif name == "sync_kaspi_orders":
                    print(f"      Fetched: {result.get('orders_fetched', 0)}, Inserted: {result.get('orders_inserted', 0)}, Updated: {result.get('orders_updated', 0)}")
                elif name == "assign_sizes":
                    print(f"      Processed: {result.get('orders_processed', 0)}, Assigned: {result.get('assigned', 0)}")
                    if result.get('by_confidence'):
                        conf = result['by_confidence']
                        print(f"      Confidence: HIGH={conf.get('HIGH', 0)}, MEDIUM={conf.get('MEDIUM', 0)}, LOW={conf.get('LOW', 0)}")
                elif name == "download_waybills":
                    if result.get('dry_run'):
                        print(f"      [DRY RUN] Pending: {result.get('pending', 0)}, Downloaded: {result.get('downloaded', 0)}")
                    else:
                        print(f"      Downloaded: {result.get('downloaded', 0)}, Failed: {result.get('failed', 0)}")
                elif name == "send_order_alerts":
                    print(f"      Sent: {result.get('sent', 0)}, Suppressed: {result.get('suppressed', 0)}")
                elif "sku_count" in result:
                    print(f"      SKUs processed: {result.get('sku_count', 0)}")

        except Exception as e:
            results["steps"][name] = {"error": str(e)}
            if verbose:
                print(f"      ERROR: {e}")

    # Calculate duration
    duration = time.time() - start_time
    results["duration_seconds"] = round(duration, 2)
    results["success"] = not any(
        r.get("error") for r in results["steps"].values()
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run the complete daily inventory pipeline"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to process (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--inventory",
        type=str,
        default=None,
        help="Path to inventory Excel file",
    )
    parser.add_argument(
        "--orders",
        type=str,
        default=None,
        help="Path to orders Excel file",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip ingestion steps (1-4), just recalculate",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Skip Telegram alerting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without saving changes",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    date = args.date or datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"Daily Pipeline - {date}")
    print("=" * 60)

    if args.dry_run:
        print("MODE: Dry Run (no changes will be saved)")
    if args.skip_ingest:
        print("MODE: Skip Ingestion (recalculate only)")
    if args.no_alerts:
        print("MODE: No Alerts")

    result = run_pipeline(
        date=date,
        inventory_file=args.inventory,
        orders_file=args.orders,
        skip_ingest=args.skip_ingest,
        no_alerts=args.no_alerts,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 60)
    print("Pipeline Summary")
    print("-" * 60)

    for step_name, step_result in result["steps"].items():
        status = "ERROR" if step_result.get("error") else "OK"
        if step_result.get("skipped"):
            status = "SKIP"
        print(f"  {step_name}: {status}")

    print("-" * 60)
    print(f"Duration: {result['duration_seconds']}s")
    print(f"Success: {result['success']}")
    print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
