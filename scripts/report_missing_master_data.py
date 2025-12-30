#!/usr/bin/env python3
"""
Missing Master Data Report - Part 6

Reports SKUs with missing critical master data that blocks autonomous ordering.
Prioritizes by proposed spend impact.

Missing data types:
- Weight (weight_kg)
- Cost (base_cost_cny, cogs_kzt)
- Price (kaspi_price_kzt)
- Supplier mapping (supplier_code)

Usage:
    # Generate report
    python scripts/report_missing_master_data.py

    # Include in Telegram digest
    python scripts/report_missing_master_data.py --telegram

    # Filter by missing field
    python scripts/report_missing_master_data.py --field weight

Output:
    exports/missing_master_data_YYYY-MM-DD.csv
"""

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.tracking.run_tracker import RunTracker
from core.alerts.error_alerts import send_error_alert, send_success_alert

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"


@dataclass
class MissingDataSKU:
    """SKU with missing master data."""
    sku_key: str
    sku_id: str
    product_name: str
    missing_fields: list  # ['weight', 'cost', 'price', 'supplier']
    proposed_spend_kzt: float
    daily_demand: float
    blocked_reason: str


@dataclass
class MissingDataReport:
    """Complete missing data report."""
    report_date: str
    total_skus_checked: int = 0
    skus_with_missing_data: int = 0
    total_blocked_spend_kzt: float = 0
    # By field
    missing_weight: int = 0
    missing_cost: int = 0
    missing_price: int = 0
    missing_supplier: int = 0
    # Details
    sku_details: list = field(default_factory=list)


def get_missing_master_data(
    db_path: Path,
    field_filter: Optional[str] = None,
) -> MissingDataReport:
    """
    Identify SKUs with missing master data.

    Args:
        db_path: Path to database
        field_filter: Optional filter for specific field (weight, cost, price, supplier)

    Returns:
        MissingDataReport with details
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    report = MissingDataReport(report_date=date.today().isoformat())

    # Get all active SKUs with their data
    rows = conn.execute("""
        SELECT
            s.sku_key,
            s.sku_id,
            s.model as product_name,
            s.weight_kg,
            s.base_cost_cny,
            COALESCE(s.cogs_kzt, 0) as cogs_kzt,
            COALESCE(s.kaspi_price_kzt, 0) as kaspi_price_kzt,
            s.supplier_code,
            COALESCE(de.d_final, m.d30, 0) as daily_demand
        FROM dim_sku s
        LEFT JOIN fact_demand_estimates de ON s.sku_key = de.sku_key
        LEFT JOIN fact_sku_metrics m ON s.sku_key = m.sku_key
        WHERE s.active_flag = 1
    """).fetchall()

    report.total_skus_checked = len(rows)

    for row in rows:
        missing = []

        # Check weight
        if not row['weight_kg'] or row['weight_kg'] <= 0:
            missing.append('weight')
            report.missing_weight += 1

        # Check cost
        if (not row['base_cost_cny'] or row['base_cost_cny'] <= 0) and (not row['cogs_kzt'] or row['cogs_kzt'] <= 0):
            missing.append('cost')
            report.missing_cost += 1

        # Check price
        if not row['kaspi_price_kzt'] or row['kaspi_price_kzt'] <= 0:
            missing.append('price')
            report.missing_price += 1

        # Check supplier
        if not row['supplier_code']:
            missing.append('supplier')
            report.missing_supplier += 1

        # Apply field filter if specified
        if field_filter and field_filter not in missing:
            continue

        if missing:
            # Estimate proposed spend based on daily demand and inventory params
            daily_demand = row['daily_demand'] or 0
            cogs = row['cogs_kzt'] or 0

            # Estimate: 30 days of demand * unit cost
            proposed_spend = daily_demand * 30 * cogs

            report.sku_details.append(MissingDataSKU(
                sku_key=row['sku_key'],
                sku_id=row['sku_id'] or row['sku_key'],
                product_name=row['product_name'] or row['sku_key'],
                missing_fields=missing,
                proposed_spend_kzt=proposed_spend,
                daily_demand=daily_demand,
                blocked_reason=f"Missing: {', '.join(missing)}",
            ))

    conn.close()

    # Sort by proposed spend descending
    report.sku_details.sort(key=lambda x: x.proposed_spend_kzt, reverse=True)

    report.skus_with_missing_data = len(report.sku_details)
    report.total_blocked_spend_kzt = sum(s.proposed_spend_kzt for s in report.sku_details)

    return report


def write_report_csv(report: MissingDataReport, output_dir: Path) -> Path:
    """Write missing data report to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"missing_master_data_{report.report_date}.csv"

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(["MISSING MASTER DATA REPORT"])
        writer.writerow(["Generated", report.report_date])
        writer.writerow([])

        # Summary
        writer.writerow(["SUMMARY"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total SKUs Checked", report.total_skus_checked])
        writer.writerow(["SKUs with Missing Data", report.skus_with_missing_data])
        writer.writerow(["Total Blocked Spend (KZT)", f"{report.total_blocked_spend_kzt:,.0f}"])
        writer.writerow([])

        writer.writerow(["MISSING BY FIELD"])
        writer.writerow(["Missing Weight", report.missing_weight])
        writer.writerow(["Missing Cost", report.missing_cost])
        writer.writerow(["Missing Price", report.missing_price])
        writer.writerow(["Missing Supplier", report.missing_supplier])
        writer.writerow([])

        # Details (sorted by spend impact)
        writer.writerow(["SKU DETAILS (by spend impact)"])
        writer.writerow([
            "sku_key", "sku_id", "product_name", "missing_fields",
            "proposed_spend_kzt", "daily_demand", "blocked_reason"
        ])
        for sku in report.sku_details:
            writer.writerow([
                sku.sku_key,
                sku.sku_id,
                sku.product_name,
                "; ".join(sku.missing_fields),
                f"{sku.proposed_spend_kzt:,.0f}",
                f"{sku.daily_demand:.2f}",
                sku.blocked_reason,
            ])

    return output_path


def format_telegram_summary(report: MissingDataReport, top_n: int = 5) -> str:
    """Format missing data summary for Telegram."""
    msg = f"""<b>Missing Master Data Report</b>
<b>Date:</b> {report.report_date}

<b>Summary:</b>
  • SKUs Checked: {report.total_skus_checked}
  • SKUs with Missing Data: {report.skus_with_missing_data}
  • Blocked Spend: {report.total_blocked_spend_kzt:,.0f} KZT

<b>Missing by Field:</b>
  • Weight: {report.missing_weight}
  • Cost: {report.missing_cost}
  • Price: {report.missing_price}
  • Supplier: {report.missing_supplier}"""

    if report.sku_details:
        msg += f"\n\n<b>Top {min(top_n, len(report.sku_details))} Blockers by Spend Impact:</b>"
        for sku in report.sku_details[:top_n]:
            msg += f"\n  • {sku.sku_key}: {sku.proposed_spend_kzt:,.0f} KZT ({', '.join(sku.missing_fields)})"

    return msg


def get_top_missing_data_blockers(
    db_path: Path = None,
    limit: int = 5,
) -> list[dict]:
    """
    Get top missing data blockers for Telegram digest integration.

    Returns:
        List of dicts with sku_key, blocked_spend_kzt, missing_fields
    """
    if db_path is None:
        db_path = DB_PATH

    report = get_missing_master_data(db_path)

    return [
        {
            "sku_key": sku.sku_key,
            "blocked_spend_kzt": sku.proposed_spend_kzt,
            "missing_fields": sku.missing_fields,
        }
        for sku in report.sku_details[:limit]
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Missing Master Data Report (Part 6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", type=str, help="Database path")
    parser.add_argument("--field", type=str, choices=['weight', 'cost', 'price', 'supplier'],
                        help="Filter by missing field")
    parser.add_argument("--telegram", action="store_true", help="Send summary to Telegram")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    print("=" * 60)
    print("MISSING MASTER DATA REPORT")
    print("=" * 60)
    print(f"Database: {db_path}")
    if args.field:
        print(f"Field Filter: {args.field}")
    print()

    with RunTracker("MISSING_DATA_REPORT", db_path) as tracker:
        try:
            tracker.start_step("analyze_master_data")
            report = get_missing_master_data(db_path, args.field)
            tracker.complete_step()

            tracker.start_step("write_csv")
            output_path = write_report_csv(report, EXPORTS_DIR)
            tracker.add_output_file(str(output_path))
            tracker.complete_step()

            # Print summary
            print(f"Summary:")
            print(f"  Total SKUs Checked: {report.total_skus_checked}")
            print(f"  SKUs with Missing Data: {report.skus_with_missing_data}")
            print(f"  Blocked Spend: {report.total_blocked_spend_kzt:,.0f} KZT")
            print()

            print(f"Missing by Field:")
            print(f"  Weight: {report.missing_weight}")
            print(f"  Cost: {report.missing_cost}")
            print(f"  Price: {report.missing_price}")
            print(f"  Supplier: {report.missing_supplier}")
            print()

            if args.verbose and report.sku_details:
                print("Top 10 Blockers by Spend Impact:")
                for sku in report.sku_details[:10]:
                    print(f"  {sku.sku_key}: {sku.proposed_spend_kzt:,.0f} KZT - {sku.blocked_reason}")
                print()

            print(f"Output: {output_path}")

            if args.telegram:
                tracker.start_step("send_telegram")
                msg = format_telegram_summary(report)
                if report.skus_with_missing_data > 0:
                    send_error_alert(
                        error_message=f"{report.skus_with_missing_data} SKUs with missing master data",
                        script_name="report_missing_master_data",
                        context=msg,
                    )
                else:
                    send_success_alert(msg, "missing_master_data")
                tracker.complete_step()
                print("Telegram summary sent")

            tracker.set_metrics(
                skus_processed=report.total_skus_checked,
                guardrails_blocked=report.skus_with_missing_data,
            )

        except Exception as e:
            print(f"ERROR: {e}")
            tracker.fail_step(str(e))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
