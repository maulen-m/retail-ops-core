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
        # Find latest inventory file
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
        ("transform_sales", lambda: step_transform_sales(dry_run, verbose)),
        ("build_aggregates", lambda: step_build_aggregates(date, dry_run, verbose)),
        ("compute_metrics", lambda: step_compute_metrics(dry_run, verbose)),
        ("build_capital_snapshot", lambda: step_build_capital_snapshot(date, dry_run, verbose)),
        ("export_reports", lambda: step_export_reports(date, dry_run, verbose)),
        ("send_alerts", lambda: step_send_alerts(dry_run, verbose)),
    ]

    # Skip ingestion steps if requested
    if skip_ingest:
        steps = steps[4:]  # Start from compute_metrics

    # Skip alerts if requested
    if no_alerts:
        steps = [s for s in steps if s[0] != "send_alerts"]

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
