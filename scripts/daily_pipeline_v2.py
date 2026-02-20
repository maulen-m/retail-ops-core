#!/usr/bin/env python3
"""
TASK-186: Daily Pipeline V2 (Phase 10)

Stock ledger-integrated daily pipeline for inventory management.

This pipeline uses the event-sourced stock ledger for inventory tracking,
the new sales_fact_v2 table for sales, and integrates with PO tracking.

Steps:
1. Ingest sales from Excel to sales_fact_v2 + stock_ledger (SALE events)
2. Rebuild stock snapshot from ledger
3. Recalculate PO ETAs for active POs
4. Compute SKU metrics using ledger-based stock
5. Export reports (stock_balance.csv, po_status.csv)
6. Send alerts for low stock and overdue POs

Usage:
    python scripts/daily_pipeline_v2.py                     # Full pipeline
    python scripts/daily_pipeline_v2.py --sales-file x.xlsx # Specify sales file
    python scripts/daily_pipeline_v2.py --skip-sales        # Skip sales ingest
    python scripts/daily_pipeline_v2.py --no-alerts         # Skip alerts
    python scripts/daily_pipeline_v2.py --dry-run           # Simulate only
"""

import argparse
import glob
import os
import sys
import time
from datetime import date, datetime
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

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import (
    get_stock_balances_all,
    get_event_summary,
    rebuild_snapshot_from_ledger,
)
from core.ingest.sales_ingest import ingest_sales
from core.po.eta import recalc_all_etas, get_eta_status, calc_days_until_arrival


def step_ingest_sales(
    sales_file: Optional[str],
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 1: Ingest sales from Excel to sales_fact_v2 and stock_ledger."""
    if sales_file is None:
        # Find latest sales file
        patterns = [
            "excel/SALES_*.xlsx",
            "excel/sales_*.xlsx",
            "data_raw/SALES_*.xlsx",
        ]
        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))
        files = sorted(files, reverse=True)

        if not files:
            return {"skipped": True, "reason": "No sales file found"}
        sales_file = files[0]

    if not os.path.exists(sales_file):
        return {"skipped": True, "reason": f"File not found: {sales_file}"}

    if dry_run:
        return {
            "dry_run": True,
            "file": Path(sales_file).name,
        }

    try:
        result = ingest_sales(
            xlsx_path=sales_file,
            apply_to_ledger=True,
            db_path=DEFAULT_DB_PATH,
        )
        return {
            "file": Path(sales_file).name,
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "returns": result["returns_processed"],
            "ledger_events": result["ledger_events"],
            "unmapped_count": len(result["unmapped"]),
            "errors": len(result["errors"]),
        }
    except Exception as e:
        return {"error": str(e)}


def step_rebuild_snapshot(
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 2: Rebuild stock snapshot from ledger events."""
    if dry_run:
        # Just report current balances
        balances = get_stock_balances_all(db_path=DEFAULT_DB_PATH)
        return {
            "dry_run": True,
            "sku_count": len(balances),
            "total_stock": sum(balances.values()),
        }

    try:
        result = rebuild_snapshot_from_ledger(db_path=DEFAULT_DB_PATH)
        return {
            "sku_count": result["sku_count"],
            "total_stock": result["total_stock"],
        }
    except Exception as e:
        return {"error": str(e)}


def step_recalc_etas(
    delay_days: int,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 3: Recalculate ETAs for active POs."""
    if dry_run:
        return {"dry_run": True}

    try:
        updated = recalc_all_etas(delay_days=delay_days, db_path=DEFAULT_DB_PATH)
        return {"pos_updated": updated}
    except Exception as e:
        return {"error": str(e)}


def step_compute_metrics(
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 4: Compute SKU metrics using ledger-based stock."""
    try:
        # Import here to avoid circular imports
        from scripts.run_sku_metrics import run_metrics

        result = run_metrics(
            days=30,
            csv_path=None,
            dry_run=dry_run,
            verbose=verbose,
        )
        return result
    except ImportError:
        return {"skipped": True, "reason": "run_sku_metrics not available"}
    except Exception as e:
        return {"error": str(e)}


def step_export_reports(
    run_date: str,
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 5: Export reports."""
    import csv

    output_dir = Path(f"exports/{run_date}")
    results = {}

    if dry_run:
        results["dry_run"] = True
        return results

    output_dir.mkdir(parents=True, exist_ok=True)

    # Export stock balance report
    try:
        balances = get_stock_balances_all(db_path=DEFAULT_DB_PATH)
        stock_path = output_dir / "stock_balance.csv"

        with open(stock_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sku_id", "balance"])
            for sku_id, balance in sorted(balances.items()):
                writer.writerow([sku_id, balance])

        results["stock_balance"] = len(balances)
    except Exception as e:
        results["stock_balance_error"] = str(e)

    # Export PO status report
    try:
        with get_db(DEFAULT_DB_PATH) as conn:
            rows = conn.execute("""
                SELECT
                    po_id, supplier_code, status,
                    message_date, ship_date_cargo,
                    ast_arrival_nom, ast_arrival_real,
                    (SELECT SUM(order_qty) FROM po_line WHERE po_line.po_id = po_header.po_id) as total_qty,
                    (SELECT SUM(received_qty) FROM po_line WHERE po_line.po_id = po_header.po_id) as received_qty
                FROM po_header
                WHERE status NOT IN ('CLOSED', 'CANCELLED')
                ORDER BY ast_arrival_nom
            """).fetchall()

        po_path = output_dir / "po_status.csv"
        with open(po_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "po_id", "supplier", "status", "message_date",
                "ship_cargo", "eta_ast", "arrived_ast",
                "ordered_qty", "received_qty", "days_until_arrival"
            ])
            for row in rows:
                eta = row["ast_arrival_nom"]
                days_until = ""
                if eta:
                    try:
                        eta_date = datetime.strptime(eta[:10], "%Y-%m-%d").date()
                        days_until = calc_days_until_arrival(eta_date)
                    except (ValueError, TypeError):
                        pass

                writer.writerow([
                    row["po_id"],
                    row["supplier_code"],
                    row["status"],
                    row["message_date"] or "",
                    row["ship_date_cargo"] or "",
                    row["ast_arrival_nom"] or "",
                    row["ast_arrival_real"] or "",
                    row["total_qty"] or 0,
                    row["received_qty"] or 0,
                    days_until,
                ])

        results["po_status"] = len(rows)
    except Exception as e:
        results["po_status_error"] = str(e)

    # Export event summary
    try:
        summary = get_event_summary(db_path=DEFAULT_DB_PATH)
        summary_path = output_dir / "ledger_summary.csv"

        with open(summary_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["event_type", "count", "qty_total"])
            for event_type, data in sorted(summary.items()):
                writer.writerow([event_type, data["count"], data["qty_total"]])

        results["ledger_summary"] = len(summary)
    except Exception as e:
        results["ledger_summary_error"] = str(e)

    return results


def step_send_alerts(
    dry_run: bool,
    verbose: bool,
) -> dict:
    """Step 6: Send alerts for low stock and overdue POs."""
    results = {"low_stock": 0, "overdue_pos": 0}

    if dry_run:
        results["dry_run"] = True
        return results

    # Check for low stock SKUs
    try:
        balances = get_stock_balances_all(db_path=DEFAULT_DB_PATH)
        low_stock_skus = [sku for sku, bal in balances.items() if 0 < bal <= 5]
        results["low_stock"] = len(low_stock_skus)
    except Exception as e:
        results["low_stock_error"] = str(e)

    # Check for overdue POs
    try:
        with get_db(DEFAULT_DB_PATH) as conn:
            rows = conn.execute("""
                SELECT po_id, ast_arrival_nom
                FROM po_header
                WHERE status NOT IN ('CLOSED', 'CANCELLED', 'RECEIVED', 'ARRIVED_AST')
                  AND ast_arrival_nom IS NOT NULL
            """).fetchall()

        overdue = []
        for row in rows:
            try:
                eta = datetime.strptime(row["ast_arrival_nom"][:10], "%Y-%m-%d").date()
                if get_eta_status(eta) == "OVERDUE":
                    overdue.append(row["po_id"])
            except (ValueError, TypeError):
                pass

        results["overdue_pos"] = len(overdue)
        if overdue and verbose:
            print(f"      Overdue POs: {', '.join(overdue)}")

    except Exception as e:
        results["overdue_error"] = str(e)

    # Send Telegram alerts if available
    try:
        from core.alerts.telegram import send_message

        if results["low_stock"] > 0 or results["overdue_pos"] > 0:
            message = f"Daily Pipeline Alert:\n"
            if results["low_stock"] > 0:
                message += f"- {results['low_stock']} SKUs with low stock (<=5)\n"
            if results["overdue_pos"] > 0:
                message += f"- {results['overdue_pos']} POs overdue\n"

            if not dry_run:
                send_message(message)
                results["telegram_sent"] = True
    except ImportError:
        results["telegram"] = "not configured"
    except Exception as e:
        results["telegram_error"] = str(e)

    return results


def run_pipeline_v2(
    run_date: Optional[str] = None,
    sales_file: Optional[str] = None,
    skip_sales: bool = False,
    no_alerts: bool = False,
    delay_days: int = 0,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Run the stock ledger-integrated daily pipeline.

    Args:
        run_date: Date for reports (default: today)
        sales_file: Path to sales Excel file
        skip_sales: Skip sales ingestion
        no_alerts: Skip alerts
        delay_days: Additional delay days for ETA calculation
        dry_run: Simulate without saving
        verbose: Print progress

    Returns:
        Dict with results for each step
    """
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")

    start_time = time.time()
    results = {
        "date": run_date,
        "dry_run": dry_run,
        "steps": {},
    }

    steps = []

    # Step 1: Ingest sales
    if not skip_sales:
        steps.append(("ingest_sales", lambda: step_ingest_sales(sales_file, dry_run, verbose)))

    # Step 2: Rebuild snapshot
    steps.append(("rebuild_snapshot", lambda: step_rebuild_snapshot(dry_run, verbose)))

    # Step 3: Recalculate ETAs
    steps.append(("recalc_etas", lambda: step_recalc_etas(delay_days, dry_run, verbose)))

    # Step 4: Compute metrics
    steps.append(("compute_metrics", lambda: step_compute_metrics(dry_run, verbose)))

    # Step 5: Export reports
    steps.append(("export_reports", lambda: step_export_reports(run_date, dry_run, verbose)))

    # Step 6: Send alerts
    if not no_alerts:
        steps.append(("send_alerts", lambda: step_send_alerts(dry_run, verbose)))

    for i, (name, step_func) in enumerate(steps, 1):
        if verbose:
            print(f"\n[{i}/{len(steps)}] {name.replace('_', ' ').title()}...")

        try:
            result = step_func()
            results["steps"][name] = result

            if verbose and result:
                if result.get("skipped"):
                    print(f"      Skipped: {result.get('reason', 'unknown')}")
                elif result.get("dry_run"):
                    print(f"      [DRY RUN]")
                elif result.get("error"):
                    print(f"      ERROR: {result.get('error')}")
                else:
                    # Print step-specific info
                    if name == "ingest_sales":
                        print(f"      File: {result.get('file', '-')}")
                        print(f"      Inserted: {result.get('inserted', 0)}, Skipped: {result.get('skipped', 0)}")
                        print(f"      Ledger events: {result.get('ledger_events', 0)}")
                    elif name == "rebuild_snapshot":
                        print(f"      SKUs: {result.get('sku_count', 0)}, Total stock: {result.get('total_stock', 0)}")
                    elif name == "recalc_etas":
                        print(f"      POs updated: {result.get('pos_updated', 0)}")
                    elif name == "export_reports":
                        print(f"      Stock balance: {result.get('stock_balance', 0)} SKUs")
                        print(f"      PO status: {result.get('po_status', 0)} POs")
                    elif name == "send_alerts":
                        print(f"      Low stock SKUs: {result.get('low_stock', 0)}")
                        print(f"      Overdue POs: {result.get('overdue_pos', 0)}")

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
        description="Daily Pipeline V2 - Stock Ledger Integrated"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date for reports (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--sales-file",
        type=str,
        default=None,
        help="Path to sales Excel file",
    )
    parser.add_argument(
        "--skip-sales",
        action="store_true",
        help="Skip sales ingestion step",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Skip alerting step",
    )
    parser.add_argument(
        "--delay-days",
        type=int,
        default=0,
        help="Additional delay days for ETA calculation",
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

    run_date = args.date or datetime.now().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"Daily Pipeline V2 (Stock Ledger) - {run_date}")
    print("=" * 60)

    if args.dry_run:
        print("MODE: Dry Run (no changes will be saved)")
    if args.skip_sales:
        print("MODE: Skip Sales Ingestion")
    if args.no_alerts:
        print("MODE: No Alerts")

    result = run_pipeline_v2(
        run_date=run_date,
        sales_file=args.sales_file,
        skip_sales=args.skip_sales,
        no_alerts=args.no_alerts,
        delay_days=args.delay_days,
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
        if step_result.get("dry_run"):
            status = "DRY"
        print(f"  {step_name}: {status}")

    print("-" * 60)
    print(f"Duration: {result['duration_seconds']}s")
    print(f"Success: {result['success']}")
    print("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
