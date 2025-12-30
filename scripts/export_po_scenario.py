#!/usr/bin/env python3
"""
Export PO-4/5/6 scenario recalculation with blackout analysis.

Produces exports/po_4_5_6_recalc.csv showing:
- message_date, prep_days, ship_date_cargo, ETA
- total qty, total weight, key SKUs and size splits
- blackout warnings where applied

Usage:
    python scripts/export_po_scenario.py
    python scripts/export_po_scenario.py --all-pos       # Include PO-7 through PO-10
    python scripts/export_po_scenario.py --output FILE   # Custom output path
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.po.blackout import BlackoutManager, adjust_po_dates, CNY_2026

# Paths
DASHBOARD_JSON = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "exports" / "po_4_5_6_recalc.csv"


def parse_date(date_str: str) -> Optional[date]:
    """Parse YYYY-MM-DD date string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_po_dates(
    message_date: date,
    prep_days: int,
    lead_time_L: int,
    blackout_manager: BlackoutManager
) -> dict:
    """
    Calculate PO shipping and arrival dates with blackout adjustment.

    Args:
        message_date: Date PO message is sent to supplier
        prep_days: Days for supplier to prepare goods
        lead_time_L: Transit time in days
        blackout_manager: Blackout period manager

    Returns:
        Dict with calculated dates and warnings
    """
    # Calculate raw dates
    ship_date_raw = message_date + timedelta(days=prep_days)
    est_arrival_raw = ship_date_raw + timedelta(days=lead_time_L)

    # Apply blackout adjustments (affects supplier-side dates only)
    result = adjust_po_dates(
        po_date=message_date,
        ship_date=ship_date_raw,
        est_arrival=est_arrival_raw,
        blackout_manager=blackout_manager
    )

    return {
        "message_date": message_date,
        "prep_days": prep_days,
        "ship_date_raw": ship_date_raw,
        "ship_date_adjusted": result["ship_date"],
        "eta_raw": est_arrival_raw,
        "eta_adjusted": result["est_arrival"],
        "blackout_adjusted": result["blackout_adjusted"],
        "warnings": result["warnings"],
        "lead_time_L": lead_time_L,
    }


def export_po_scenarios(
    dashboard_path: Path = DASHBOARD_JSON,
    output_path: Path = DEFAULT_OUTPUT,
    include_all_pos: bool = False,
    verbose: bool = False
) -> dict:
    """
    Export PO scenarios to CSV.

    Args:
        dashboard_path: Path to dashboard JSON
        output_path: Output CSV path
        include_all_pos: If True, include PO-7 through PO-10
        verbose: Print progress

    Returns:
        Summary dict with stats
    """
    # Load dashboard data
    if not dashboard_path.exists():
        raise FileNotFoundError(f"Dashboard JSON not found: {dashboard_path}")

    with open(dashboard_path) as f:
        data = json.load(f)

    pos_data = data.get("pos", {})
    if not pos_data:
        raise ValueError("No PO data found in dashboard JSON")

    # Select which POs to include
    if include_all_pos:
        po_names = sorted(pos_data.keys())
    else:
        po_names = ["PO-4", "PO-5", "PO-6"]

    # Filter to only existing POs
    po_names = [name for name in po_names if name in pos_data]

    if verbose:
        print(f"Processing POs: {', '.join(po_names)}")

    blackout_manager = BlackoutManager([CNY_2026])

    # Prepare CSV rows
    rows = []

    # Summary row for each PO
    summary_rows = []

    for po_name in po_names:
        po = pos_data[po_name]

        # Parse dates and params
        message_date = parse_date(po.get("po_message_date", ""))
        if not message_date:
            if verbose:
                print(f"  Skipping {po_name}: no message_date")
            continue

        prep_days = po.get("prep_days_clothes", 10)
        lead_time_L = po.get("lead_time_L", 21)

        # Calculate dates with blackout
        dates = calculate_po_dates(
            message_date=message_date,
            prep_days=prep_days,
            lead_time_L=lead_time_L,
            blackout_manager=blackout_manager
        )

        # Get summary stats
        summary = po.get("summary", {})
        total_units = summary.get("total_units", 0)
        total_weight = summary.get("total_weight_kg", 0)
        skus_with_orders = summary.get("skus_with_orders", 0)

        # Build summary row
        summary_row = {
            "po_name": po_name,
            "message_date": dates["message_date"].isoformat(),
            "prep_days": dates["prep_days"],
            "ship_date_raw": dates["ship_date_raw"].isoformat(),
            "ship_date_adjusted": dates["ship_date_adjusted"].isoformat(),
            "eta_raw": dates["eta_raw"].isoformat(),
            "eta_adjusted": dates["eta_adjusted"].isoformat(),
            "blackout_adjusted": dates["blackout_adjusted"],
            "total_units": total_units,
            "total_weight_kg": round(total_weight, 1),
            "skus_with_orders": skus_with_orders,
            "blackout_warning": "; ".join(dates["warnings"]) if dates["warnings"] else "",
        }
        summary_rows.append(summary_row)

        if verbose:
            status = "BLACKOUT ADJUSTED" if dates["blackout_adjusted"] else "OK"
            print(f"  {po_name}: msg={dates['message_date']} → "
                  f"ship={dates['ship_date_adjusted']} → "
                  f"ETA={dates['eta_adjusted']} [{status}]")

        # Get top SKUs by order quantity
        sku_level = po.get("sku_level", [])
        top_skus = sorted(
            [s for s in sku_level if s.get("po_qty_total", 0) > 0],
            key=lambda x: x.get("po_qty_total", 0),
            reverse=True
        )[:5]  # Top 5 SKUs

        for sku in top_skus:
            sku_key = sku.get("sku_key", "")
            po_qty = sku.get("po_qty_total", 0)
            size_orders = sku.get("size_orders", {})

            # Format size split
            if size_orders:
                size_split = ", ".join(
                    f"{size}:{qty}" for size, qty in sorted(size_orders.items())
                    if qty > 0
                )
            else:
                size_split = ""

            row = {
                "po_name": po_name,
                "message_date": dates["message_date"].isoformat(),
                "prep_days": dates["prep_days"],
                "ship_date_adjusted": dates["ship_date_adjusted"].isoformat(),
                "eta_adjusted": dates["eta_adjusted"].isoformat(),
                "blackout_adjusted": dates["blackout_adjusted"],
                "sku_key": sku_key,
                "order_qty": po_qty,
                "size_split": size_split,
                "blackout_warning": "; ".join(dates["warnings"]) if dates["warnings"] else "",
            }
            rows.append(row)

    # Write summary CSV
    summary_output = output_path.parent / f"{output_path.stem}_summary.csv"

    with open(summary_output, "w", newline="") as f:
        if summary_rows:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            writer.writeheader()
            writer.writerows(summary_rows)

    if verbose:
        print(f"\nSummary written to: {summary_output}")

    # Write detailed CSV
    with open(output_path, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    if verbose:
        print(f"Details written to: {output_path}")

    # Count blackout warnings
    blackout_pos = [r for r in summary_rows if r["blackout_adjusted"]]

    return {
        "total_pos": len(po_names),
        "summary_rows": len(summary_rows),
        "detail_rows": len(rows),
        "blackout_affected_pos": len(blackout_pos),
        "output_path": str(output_path),
        "summary_path": str(summary_output),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export PO-4/5/6 scenario recalculation with blackout analysis"
    )
    parser.add_argument("--all-pos", action="store_true",
                        help="Include PO-7 through PO-10")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help=f"Output CSV path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print progress")
    args = parser.parse_args()

    print("=" * 60)
    print("PO SCENARIO EXPORT")
    print("=" * 60)

    try:
        result = export_po_scenarios(
            output_path=args.output,
            include_all_pos=args.all_pos,
            verbose=True
        )

        print("\n" + "-" * 60)
        print("SUMMARY")
        print("-" * 60)
        print(f"POs processed: {result['total_pos']}")
        print(f"Summary rows: {result['summary_rows']}")
        print(f"Detail rows: {result['detail_rows']}")
        print(f"Blackout-affected POs: {result['blackout_affected_pos']}")
        print(f"\nOutput files:")
        print(f"  Summary: {result['summary_path']}")
        print(f"  Details: {result['output_path']}")

        if result['blackout_affected_pos'] > 0:
            print(f"\nWARNING: {result['blackout_affected_pos']} PO(s) affected by CNY blackout!")
            print("Review the blackout_warning column for details.")

        sys.exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
