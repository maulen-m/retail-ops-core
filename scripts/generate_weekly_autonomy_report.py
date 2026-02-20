#!/usr/bin/env python3
"""
Weekly Autonomy KPI Report - Part 6

Generates weekly KPI metrics for the autonomous inventory/PO system.
No Excel dependency - uses database only.

Metrics:
- Top SKUs: demand vs actual sales (forecast bias)
- OOS days and estimated lost sales proxy
- Inventory turns proxy
- Blocked spend by reason over the week

Usage:
    # Generate report for last 7 days
    python scripts/generate_weekly_autonomy_report.py

    # Generate report for specific date range
    python scripts/generate_weekly_autonomy_report.py --start 2025-12-16 --end 2025-12-22

    # Send summary to Telegram
    python scripts/generate_weekly_autonomy_report.py --telegram

Output:
    exports/weekly_autonomy_report_YYYY-MM-DD.csv
"""

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.tracking.run_tracker import RunTracker
from core.alerts.error_alerts import send_success_alert

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"


@dataclass
class SKUBias:
    """Forecast bias for a single SKU."""
    sku_key: str
    forecast_demand: float  # D_final or d30
    actual_sales: float
    bias_pct: float  # (forecast - actual) / actual * 100
    bias_direction: str  # OVER, UNDER, ACCURATE


@dataclass
class OOSMetric:
    """Out-of-stock metrics for a single SKU."""
    sku_key: str
    oos_days: int
    avg_daily_demand: float
    estimated_lost_sales: float  # oos_days * avg_daily_demand
    estimated_lost_revenue_kzt: float


@dataclass
class InventoryTurn:
    """Inventory turn proxy for a single SKU."""
    sku_key: str
    avg_stock: float
    total_sales: float
    turns_annualized: float  # (total_sales / avg_stock) * 52


@dataclass
class BlockedSpend:
    """Blocked spend summary by reason."""
    reason: str
    count: int
    total_value_kzt: float


@dataclass
class WeeklyReport:
    """Complete weekly report."""
    report_date: str
    start_date: str
    end_date: str
    # Summary
    total_skus_analyzed: int = 0
    total_sales_kzt: float = 0
    total_oos_days: int = 0
    total_lost_sales_units: float = 0
    total_blocked_spend_kzt: float = 0
    avg_forecast_bias_pct: float = 0
    avg_inventory_turns: float = 0
    # Details
    top_sku_biases: list = field(default_factory=list)
    oos_metrics: list = field(default_factory=list)
    inventory_turns: list = field(default_factory=list)
    blocked_spend_by_reason: list = field(default_factory=list)


def get_forecast_bias(
    db_path: Path,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> list[SKUBias]:
    """
    Calculate forecast bias: demand estimate vs actual sales.

    Bias = (forecast - actual) / actual * 100
    Positive = over-forecast, Negative = under-forecast
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get actual sales per SKU for the period
    actual_sales = {}
    rows = conn.execute("""
        SELECT sku_key, SUM(quantity) as total_qty
        FROM fact_sales_daily
        WHERE sale_date BETWEEN ? AND ?
        GROUP BY sku_key
        HAVING total_qty > 0
    """, (start_date, end_date)).fetchall()

    for row in rows:
        actual_sales[row['sku_key']] = row['total_qty']

    # Get forecast demand (d_final or d30)
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1

    forecasts = {}
    rows = conn.execute("""
        SELECT
            s.sku_key,
            COALESCE(de.d_final, m.d30, 0) as daily_demand
        FROM dim_sku s
        LEFT JOIN fact_demand_estimates de ON s.sku_key = de.sku_key
        LEFT JOIN fact_sku_metrics m ON s.sku_key = m.sku_key
        WHERE s.active_flag = 1
    """).fetchall()

    for row in rows:
        if row['daily_demand'] and row['daily_demand'] > 0:
            forecasts[row['sku_key']] = row['daily_demand'] * days

    conn.close()

    # Calculate bias
    biases = []
    for sku_key, forecast in forecasts.items():
        actual = actual_sales.get(sku_key, 0)
        if actual > 0:
            bias_pct = (forecast - actual) / actual * 100
            direction = "OVER" if bias_pct > 10 else ("UNDER" if bias_pct < -10 else "ACCURATE")
            biases.append(SKUBias(
                sku_key=sku_key,
                forecast_demand=forecast,
                actual_sales=actual,
                bias_pct=bias_pct,
                bias_direction=direction,
            ))

    # Sort by absolute bias descending
    biases.sort(key=lambda x: abs(x.bias_pct), reverse=True)

    return biases[:limit]


def get_oos_metrics(
    db_path: Path,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> list[OOSMetric]:
    """
    Calculate OOS days and estimated lost sales.

    OOS day = any day where stock = 0 for that SKU.
    Lost sales = OOS days * average daily demand.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get daily snapshots with stock = 0
    oos_by_sku = {}
    rows = conn.execute("""
        SELECT sku_key, COUNT(*) as oos_days
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date BETWEEN ? AND ?
          AND current_stock = 0
        GROUP BY sku_key
    """, (start_date, end_date)).fetchall()

    for row in rows:
        oos_by_sku[row['sku_key']] = row['oos_days']

    # Get demand and price for lost revenue calculation
    sku_data = {}
    rows = conn.execute("""
        SELECT
            s.sku_key,
            COALESCE(de.d_final, m.d30, 0) as daily_demand,
            COALESCE(s.kaspi_price_kzt, 0) as price_kzt
        FROM dim_sku s
        LEFT JOIN fact_demand_estimates de ON s.sku_key = de.sku_key
        LEFT JOIN fact_sku_metrics m ON s.sku_key = m.sku_key
        WHERE s.active_flag = 1
    """).fetchall()

    for row in rows:
        sku_data[row['sku_key']] = {
            'demand': row['daily_demand'] or 0,
            'price': row['price_kzt'] or 0,
        }

    conn.close()

    # Build metrics
    metrics = []
    for sku_key, oos_days in oos_by_sku.items():
        data = sku_data.get(sku_key, {'demand': 0, 'price': 0})
        demand = data['demand']
        price = data['price']
        lost_sales = oos_days * demand
        lost_revenue = lost_sales * price

        metrics.append(OOSMetric(
            sku_key=sku_key,
            oos_days=oos_days,
            avg_daily_demand=demand,
            estimated_lost_sales=lost_sales,
            estimated_lost_revenue_kzt=lost_revenue,
        ))

    # Sort by lost revenue descending
    metrics.sort(key=lambda x: x.estimated_lost_revenue_kzt, reverse=True)

    return metrics[:limit]


def get_inventory_turns(
    db_path: Path,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> list[InventoryTurn]:
    """
    Calculate inventory turns proxy.

    Turns = (Period sales / Avg inventory) * 52 (annualized)
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get average stock per SKU
    avg_stock = {}
    rows = conn.execute("""
        SELECT sku_key, AVG(current_stock) as avg_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date BETWEEN ? AND ?
        GROUP BY sku_key
        HAVING avg_stock > 0
    """, (start_date, end_date)).fetchall()

    for row in rows:
        avg_stock[row['sku_key']] = row['avg_stock']

    # Get total sales per SKU
    sales = {}
    rows = conn.execute("""
        SELECT sku_key, SUM(quantity) as total_qty
        FROM fact_sales_daily
        WHERE sale_date BETWEEN ? AND ?
        GROUP BY sku_key
    """, (start_date, end_date)).fetchall()

    for row in rows:
        sales[row['sku_key']] = row['total_qty']

    conn.close()

    # Calculate turns
    days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1
    weeks_factor = 52 / (days / 7)

    turns = []
    for sku_key, avg in avg_stock.items():
        total_sales = sales.get(sku_key, 0)
        if avg > 0 and total_sales > 0:
            period_turns = total_sales / avg
            annualized = period_turns * weeks_factor

            turns.append(InventoryTurn(
                sku_key=sku_key,
                avg_stock=avg,
                total_sales=total_sales,
                turns_annualized=annualized,
            ))

    # Sort by turns descending
    turns.sort(key=lambda x: x.turns_annualized, reverse=True)

    return turns[:limit]


def get_blocked_spend_by_reason(
    db_path: Path,
    start_date: str,
    end_date: str,
) -> list[BlockedSpend]:
    """
    Get blocked spend by reason from shadow scorecards.

    Parses scorecard CSVs to aggregate blocked spend reasons.
    """
    blocked = {
        "ROIC": {"count": 0, "value": 0},
        "CONCENTRATION": {"count": 0, "value": 0},
        "BUDGET": {"count": 0, "value": 0},
        "MISSING_DATA": {"count": 0, "value": 0},
    }

    # Check fact_run_steps for scorecard outputs
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT output_file
        FROM fact_run_steps
        WHERE step_name LIKE '%scorecard%'
          AND output_file IS NOT NULL
          AND started_at BETWEEN ? AND ?
    """, (start_date, end_date + " 23:59:59")).fetchall()

    conn.close()

    # Parse each scorecard
    for row in rows:
        scorecard_path = Path(row['output_file'])
        if scorecard_path.exists():
            try:
                with open(scorecard_path, 'r') as f:
                    reader = csv.reader(f)
                    for csv_row in reader:
                        if len(csv_row) >= 3:
                            label = csv_row[0].strip()
                            if "Blocked by ROIC" in label:
                                blocked["ROIC"]["count"] += int(csv_row[1]) if csv_row[1] else 0
                                blocked["ROIC"]["value"] += float(csv_row[2].replace(",", "")) if csv_row[2] else 0
                            elif "Blocked by Concentration" in label:
                                blocked["CONCENTRATION"]["count"] += int(csv_row[1]) if csv_row[1] else 0
                                blocked["CONCENTRATION"]["value"] += float(csv_row[2].replace(",", "")) if csv_row[2] else 0
                            elif "Blocked by Budget" in label:
                                blocked["BUDGET"]["count"] += int(csv_row[1]) if csv_row[1] else 0
                                blocked["BUDGET"]["value"] += float(csv_row[2].replace(",", "")) if csv_row[2] else 0
                            elif "Blocked by Missing" in label:
                                blocked["MISSING_DATA"]["count"] += int(csv_row[1]) if csv_row[1] else 0
                                blocked["MISSING_DATA"]["value"] += float(csv_row[2].replace(",", "")) if csv_row[2] else 0
            except Exception:
                pass

    return [
        BlockedSpend(reason=reason, count=data["count"], total_value_kzt=data["value"])
        for reason, data in blocked.items()
        if data["count"] > 0 or data["value"] > 0
    ]


def generate_weekly_report(
    db_path: Path,
    start_date: str,
    end_date: str,
) -> WeeklyReport:
    """Generate complete weekly autonomy report."""
    report = WeeklyReport(
        report_date=date.today().isoformat(),
        start_date=start_date,
        end_date=end_date,
    )

    # Get metrics
    report.top_sku_biases = get_forecast_bias(db_path, start_date, end_date)
    report.oos_metrics = get_oos_metrics(db_path, start_date, end_date)
    report.inventory_turns = get_inventory_turns(db_path, start_date, end_date)
    report.blocked_spend_by_reason = get_blocked_spend_by_reason(db_path, start_date, end_date)

    # Calculate summary
    report.total_skus_analyzed = len(set(
        [b.sku_key for b in report.top_sku_biases] +
        [o.sku_key for o in report.oos_metrics] +
        [t.sku_key for t in report.inventory_turns]
    ))

    report.total_oos_days = sum(o.oos_days for o in report.oos_metrics)
    report.total_lost_sales_units = sum(o.estimated_lost_sales for o in report.oos_metrics)
    report.total_blocked_spend_kzt = sum(b.total_value_kzt for b in report.blocked_spend_by_reason)

    if report.top_sku_biases:
        report.avg_forecast_bias_pct = sum(b.bias_pct for b in report.top_sku_biases) / len(report.top_sku_biases)

    if report.inventory_turns:
        report.avg_inventory_turns = sum(t.turns_annualized for t in report.inventory_turns) / len(report.inventory_turns)

    # Get total sales
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("""
        SELECT COALESCE(SUM(quantity * unit_price), 0)
        FROM fact_sales
        WHERE order_date BETWEEN ? AND ?
    """, (start_date, end_date)).fetchone()
    report.total_sales_kzt = row[0] if row else 0
    conn.close()

    return report


def write_report_csv(report: WeeklyReport, output_dir: Path) -> Path:
    """Write weekly report to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"weekly_autonomy_report_{report.report_date}.csv"

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(["WEEKLY AUTONOMY KPI REPORT"])
        writer.writerow(["Generated", report.report_date])
        writer.writerow(["Period", f"{report.start_date} to {report.end_date}"])
        writer.writerow([])

        # Summary
        writer.writerow(["SUMMARY"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["SKUs Analyzed", report.total_skus_analyzed])
        writer.writerow(["Total Sales (KZT)", f"{report.total_sales_kzt:,.0f}"])
        writer.writerow(["Total OOS Days", report.total_oos_days])
        writer.writerow(["Est. Lost Sales (units)", f"{report.total_lost_sales_units:,.1f}"])
        writer.writerow(["Total Blocked Spend (KZT)", f"{report.total_blocked_spend_kzt:,.0f}"])
        writer.writerow(["Avg Forecast Bias %", f"{report.avg_forecast_bias_pct:+.1f}%"])
        writer.writerow(["Avg Inventory Turns (annualized)", f"{report.avg_inventory_turns:.1f}"])
        writer.writerow([])

        # Forecast Bias
        writer.writerow(["TOP SKUs BY FORECAST BIAS"])
        writer.writerow(["sku_key", "forecast", "actual", "bias_pct", "direction"])
        for b in report.top_sku_biases[:10]:
            writer.writerow([
                b.sku_key,
                f"{b.forecast_demand:.1f}",
                f"{b.actual_sales:.1f}",
                f"{b.bias_pct:+.1f}%",
                b.bias_direction,
            ])
        writer.writerow([])

        # OOS Metrics
        writer.writerow(["TOP SKUs BY LOST SALES"])
        writer.writerow(["sku_key", "oos_days", "avg_demand", "lost_sales", "lost_revenue_kzt"])
        for o in report.oos_metrics[:10]:
            writer.writerow([
                o.sku_key,
                o.oos_days,
                f"{o.avg_daily_demand:.2f}",
                f"{o.estimated_lost_sales:.1f}",
                f"{o.estimated_lost_revenue_kzt:,.0f}",
            ])
        writer.writerow([])

        # Inventory Turns
        writer.writerow(["TOP SKUs BY INVENTORY TURNS"])
        writer.writerow(["sku_key", "avg_stock", "total_sales", "turns_annualized"])
        for t in report.inventory_turns[:10]:
            writer.writerow([
                t.sku_key,
                f"{t.avg_stock:.1f}",
                f"{t.total_sales:.1f}",
                f"{t.turns_annualized:.1f}",
            ])
        writer.writerow([])

        # Blocked Spend
        writer.writerow(["BLOCKED SPEND BY REASON"])
        writer.writerow(["reason", "count", "total_value_kzt"])
        for b in report.blocked_spend_by_reason:
            writer.writerow([
                b.reason,
                b.count,
                f"{b.total_value_kzt:,.0f}",
            ])

    return output_path


def format_telegram_summary(report: WeeklyReport) -> str:
    """Format report summary for Telegram."""
    msg = f"""<b>Weekly Autonomy KPI Report</b>
<b>Period:</b> {report.start_date} to {report.end_date}

<b>Summary:</b>
  • SKUs Analyzed: {report.total_skus_analyzed}
  • Total Sales: {report.total_sales_kzt:,.0f} KZT
  • Avg Forecast Bias: {report.avg_forecast_bias_pct:+.1f}%
  • Avg Inventory Turns: {report.avg_inventory_turns:.1f}x

<b>Lost Sales Risk:</b>
  • Total OOS Days: {report.total_oos_days}
  • Est. Lost Sales: {report.total_lost_sales_units:,.0f} units

<b>Blocked Spend:</b>
  • Total: {report.total_blocked_spend_kzt:,.0f} KZT"""

    if report.blocked_spend_by_reason:
        for b in report.blocked_spend_by_reason:
            msg += f"\n  • {b.reason}: {b.total_value_kzt:,.0f} KZT"

    if report.top_sku_biases:
        msg += "\n\n<b>Top Forecast Issues:</b>"
        for b in report.top_sku_biases[:5]:
            msg += f"\n  • {b.sku_key}: {b.bias_pct:+.0f}% ({b.bias_direction})"

    return msg


def main():
    parser = argparse.ArgumentParser(
        description="Weekly Autonomy KPI Report (Part 6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--db", type=str, help="Database path")
    parser.add_argument("--telegram", action="store_true", help="Send summary to Telegram")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    # Default to last 7 days
    if args.end:
        end_date = args.end
    else:
        end_date = date.today().isoformat()

    if args.start:
        start_date = args.start
    else:
        start_date = (date.today() - timedelta(days=6)).isoformat()

    print("=" * 60)
    print("WEEKLY AUTONOMY KPI REPORT")
    print("=" * 60)
    print(f"Period: {start_date} to {end_date}")
    print(f"Database: {db_path}")
    print()

    with RunTracker("WEEKLY_REPORT", db_path) as tracker:
        try:
            tracker.start_step("generate_report")
            report = generate_weekly_report(db_path, start_date, end_date)
            tracker.complete_step()

            tracker.start_step("write_csv")
            output_path = write_report_csv(report, EXPORTS_DIR)
            tracker.add_output_file(str(output_path))
            tracker.complete_step()

            # Print summary
            print(f"Summary:")
            print(f"  SKUs Analyzed: {report.total_skus_analyzed}")
            print(f"  Total Sales: {report.total_sales_kzt:,.0f} KZT")
            print(f"  Avg Forecast Bias: {report.avg_forecast_bias_pct:+.1f}%")
            print(f"  Avg Inventory Turns: {report.avg_inventory_turns:.1f}x")
            print()
            print(f"  Total OOS Days: {report.total_oos_days}")
            print(f"  Est. Lost Sales: {report.total_lost_sales_units:,.0f} units")
            print(f"  Total Blocked Spend: {report.total_blocked_spend_kzt:,.0f} KZT")
            print()

            if args.verbose:
                print("Top 5 Forecast Bias Issues:")
                for b in report.top_sku_biases[:5]:
                    print(f"  {b.sku_key}: {b.bias_pct:+.1f}% ({b.bias_direction})")
                print()

                print("Top 5 OOS Impact:")
                for o in report.oos_metrics[:5]:
                    print(f"  {o.sku_key}: {o.oos_days} days, {o.estimated_lost_sales:.0f} units lost")
                print()

            print(f"Output: {output_path}")

            if args.telegram:
                tracker.start_step("send_telegram")
                msg = format_telegram_summary(report)
                send_success_alert(msg, "weekly_autonomy_report")
                tracker.complete_step()
                print("Telegram summary sent")

        except Exception as e:
            print(f"ERROR: {e}")
            tracker.fail_step(str(e))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
