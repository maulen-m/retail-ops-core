#!/usr/bin/env python3
"""
Multi-Channel Pilot Runner - Part 7C

Minimal viable multi-channel execution pilot with:
- Config-driven pilot SKU list with channel weights
- Core recommender integration with channel weighting
- Pilot KPI export (revenue/profit proxy)

Usage:
    # Check pilot status
    python scripts/run_multichannel_pilot.py --status

    # Dry-run pilot recommendations
    python scripts/run_multichannel_pilot.py --dry-run

    # Generate pilot recommendations
    python scripts/run_multichannel_pilot.py

    # Export pilot KPIs
    python scripts/run_multichannel_pilot.py --export-kpi

    # Initialize pilot config
    python scripts/run_multichannel_pilot.py --init-config
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "pilot_skus.json"
EXPORTS_DIR = PROJECT_ROOT / "exports"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PilotSKU:
    """Pilot SKU with channel weights."""
    sku_key: str
    kaspi_weight: float = 0.7   # % of replenishment for Kaspi
    wb_weight: float = 0.3      # % of replenishment for WB
    active: bool = True
    notes: str = ""


@dataclass
class ChannelRecommendation:
    """Channel-specific replenishment recommendation."""
    sku_key: str
    channel: str  # KASPI, WB
    recommended_qty: int = 0
    demand_daily: float = 0.0
    current_stock: int = 0
    inbound_stock: int = 0
    rop: int = 0
    status: str = "OK"  # REORDER, WAIT, OK
    unit_cost_kzt: float = 0.0
    total_value_kzt: float = 0.0
    roic_pct: float = 0.0


@dataclass
class PilotKPI:
    """Pilot performance KPIs."""
    sku_key: str
    channel: str
    period_start: str
    period_end: str
    units_sold: int = 0
    revenue_kzt: float = 0.0
    cogs_kzt: float = 0.0
    gross_profit_kzt: float = 0.0
    profit_margin_pct: float = 0.0
    avg_stock: float = 0.0
    turns_annualized: float = 0.0
    days_oos: int = 0


@dataclass
class PilotReport:
    """Complete pilot report."""
    generated_at: str
    pilot_sku_count: int
    recommendations: list = field(default_factory=list)
    kpis: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# =============================================================================
# PILOT CONFIGURATION
# =============================================================================

def get_default_pilot_config() -> dict:
    """Get default pilot configuration."""
    return {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "max_pilot_skus": 20,
        "default_kaspi_weight": 0.7,
        "default_wb_weight": 0.3,
        "pilot_skus": []
    }


def load_pilot_config(config_path: Path = None) -> dict:
    """
    Load pilot SKU configuration from JSON file or database.

    Priority:
    1. JSON config file (config/pilot_skus.json)
    2. dim_pilot_skus table in database
    3. Empty default config
    """
    if config_path is None:
        config_path = CONFIG_PATH

    # Try JSON file first
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass

    # Try database table
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row

            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_pilot_skus'"
            ).fetchall()

            if tables:
                rows = conn.execute("""
                    SELECT sku_key, kaspi_weight, wb_weight, active_flag, notes
                    FROM dim_pilot_skus
                    WHERE active_flag = 1
                """).fetchall()

                config = get_default_pilot_config()
                config["pilot_skus"] = [
                    {
                        "sku_key": row["sku_key"],
                        "kaspi_weight": row["kaspi_weight"],
                        "wb_weight": row["wb_weight"],
                        "active": True,
                        "notes": row["notes"] or ""
                    }
                    for row in rows
                ]
                conn.close()
                return config

            conn.close()
    except Exception:
        pass

    return get_default_pilot_config()


def save_pilot_config(config: dict, config_path: Path = None) -> bool:
    """Save pilot configuration to JSON file."""
    if config_path is None:
        config_path = CONFIG_PATH

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config["updated_at"] = datetime.now().isoformat()

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception:
        return False


def init_pilot_config(db_path: Path = None) -> bool:
    """
    Initialize pilot SKU config table in database.

    Creates dim_pilot_skus table if not exists.
    """
    if db_path is None:
        db_path = DB_PATH

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_pilot_skus (
                sku_key TEXT PRIMARY KEY,
                kaspi_weight REAL DEFAULT 0.7,
                wb_weight REAL DEFAULT 0.3,
                active_flag INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_pilot_skus(config: dict = None) -> list[PilotSKU]:
    """Get list of active pilot SKUs from config."""
    if config is None:
        config = load_pilot_config()

    return [
        PilotSKU(
            sku_key=sku["sku_key"],
            kaspi_weight=sku.get("kaspi_weight", 0.7),
            wb_weight=sku.get("wb_weight", 0.3),
            active=sku.get("active", True),
            notes=sku.get("notes", "")
        )
        for sku in config.get("pilot_skus", [])
        if sku.get("active", True)
    ]


# =============================================================================
# CHANNEL-WEIGHTED RECOMMENDATIONS
# =============================================================================

def get_sku_base_recommendation(
    db_path: Path,
    sku_key: str,
) -> Optional[dict]:
    """
    Get base recommendation for a SKU from the core recommender.

    Returns the total recommended qty and related metrics.
    """
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Get latest recommendation from fact_sku_metrics or demand estimates
        row = conn.execute("""
            SELECT
                s.sku_key,
                COALESCE(de.d_final, m.d30, 0) as demand_daily,
                COALESCE(m.current_stock, 0) as current_stock,
                COALESCE(m.inbound_stock, 0) as inbound_stock,
                COALESCE(m.rop, 0) as rop,
                COALESCE(m.suggested_order, 0) as recommended_qty,
                COALESCE(m.status, 'OK') as status,
                COALESCE(s.cogs_kzt, s.base_cost_cny * 75, 0) as unit_cost_kzt,
                COALESCE(m.roic_pct, 0) as roic_pct
            FROM dim_sku s
            LEFT JOIN fact_sku_metrics m ON s.sku_key = m.sku_key
            LEFT JOIN fact_demand_estimates de ON s.sku_key = de.sku_key
            WHERE s.sku_key = ?
        """, (sku_key,)).fetchone()

        conn.close()

        if row:
            return dict(row)
        return None

    except Exception:
        return None


def generate_channel_recommendations(
    db_path: Path,
    pilot_skus: list[PilotSKU],
) -> list[ChannelRecommendation]:
    """
    Generate channel-weighted recommendations for pilot SKUs.

    Applies channel weights to split total recommendation between channels.
    """
    recommendations = []

    for pilot in pilot_skus:
        base = get_sku_base_recommendation(db_path, pilot.sku_key)
        if not base:
            continue

        total_qty = base.get("recommended_qty", 0)

        # Calculate channel splits
        kaspi_qty = int(round(total_qty * pilot.kaspi_weight))
        wb_qty = int(round(total_qty * pilot.wb_weight))

        # Ensure we don't lose units due to rounding
        if kaspi_qty + wb_qty < total_qty:
            # Add remainder to larger channel
            if pilot.kaspi_weight >= pilot.wb_weight:
                kaspi_qty += total_qty - kaspi_qty - wb_qty
            else:
                wb_qty += total_qty - kaspi_qty - wb_qty

        # Create Kaspi recommendation
        if kaspi_qty > 0 or pilot.kaspi_weight > 0:
            recommendations.append(ChannelRecommendation(
                sku_key=pilot.sku_key,
                channel="KASPI",
                recommended_qty=kaspi_qty,
                demand_daily=base.get("demand_daily", 0) * pilot.kaspi_weight,
                current_stock=base.get("current_stock", 0),  # Total for now
                inbound_stock=base.get("inbound_stock", 0),
                rop=int(base.get("rop", 0) * pilot.kaspi_weight),
                status=base.get("status", "OK") if kaspi_qty > 0 else "OK",
                unit_cost_kzt=base.get("unit_cost_kzt", 0),
                total_value_kzt=kaspi_qty * base.get("unit_cost_kzt", 0),
                roic_pct=base.get("roic_pct", 0),
            ))

        # Create WB recommendation
        if wb_qty > 0 or pilot.wb_weight > 0:
            recommendations.append(ChannelRecommendation(
                sku_key=pilot.sku_key,
                channel="WB",
                recommended_qty=wb_qty,
                demand_daily=base.get("demand_daily", 0) * pilot.wb_weight,
                current_stock=0,  # WB stock tracked separately
                inbound_stock=0,
                rop=int(base.get("rop", 0) * pilot.wb_weight),
                status=base.get("status", "OK") if wb_qty > 0 else "OK",
                unit_cost_kzt=base.get("unit_cost_kzt", 0),
                total_value_kzt=wb_qty * base.get("unit_cost_kzt", 0),
                roic_pct=base.get("roic_pct", 0),
            ))

    return recommendations


# =============================================================================
# PILOT KPI CALCULATION
# =============================================================================

def calculate_pilot_kpis(
    db_path: Path,
    pilot_skus: list[PilotSKU],
    period_days: int = 7,
) -> list[PilotKPI]:
    """
    Calculate KPIs for pilot SKUs over a period.

    Metrics:
    - Revenue, COGS, Gross Profit, Margin
    - Inventory turns (annualized)
    - Days OOS
    """
    if not db_path.exists():
        return []

    kpis = []
    today = date.today()
    period_start = today - timedelta(days=period_days)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        for pilot in pilot_skus:
            # Get Kaspi sales data
            kaspi_data = conn.execute("""
                SELECT
                    COALESCE(SUM(quantity), 0) as units_sold,
                    COALESCE(SUM(quantity * COALESCE(seller_price, 0)), 0) as revenue
                FROM fact_sales_daily fsd
                WHERE fsd.sku_key = ?
                  AND fsd.sale_date >= ?
                  AND fsd.channel = 'KASPI'
            """, (pilot.sku_key, period_start.isoformat())).fetchone()

            # Get WB sales data
            wb_data = conn.execute("""
                SELECT
                    COALESCE(SUM(quantity), 0) as units_sold,
                    COALESCE(SUM(quantity * COALESCE(seller_price, 0)), 0) as revenue
                FROM fact_sales_daily fsd
                WHERE fsd.sku_key = ?
                  AND fsd.sale_date >= ?
                  AND fsd.channel = 'WB'
            """, (pilot.sku_key, period_start.isoformat())).fetchone()

            # Get COGS
            cogs_row = conn.execute("""
                SELECT COALESCE(cogs_kzt, base_cost_cny * 75, 0) as unit_cogs
                FROM dim_sku WHERE sku_key = ?
            """, (pilot.sku_key,)).fetchone()
            unit_cogs = cogs_row["unit_cogs"] if cogs_row else 0

            # Get avg stock and OOS days
            stock_data = conn.execute("""
                SELECT
                    AVG(current_stock) as avg_stock,
                    SUM(CASE WHEN current_stock = 0 THEN 1 ELSE 0 END) as days_oos
                FROM fact_inventory_snapshot_size
                WHERE sku_key = ?
                  AND snapshot_date >= ?
            """, (pilot.sku_key, period_start.isoformat())).fetchone()

            avg_stock = stock_data["avg_stock"] if stock_data and stock_data["avg_stock"] else 0
            days_oos = stock_data["days_oos"] if stock_data else 0

            # Calculate Kaspi KPI
            kaspi_units = kaspi_data["units_sold"] if kaspi_data else 0
            kaspi_revenue = kaspi_data["revenue"] if kaspi_data else 0
            kaspi_cogs = kaspi_units * unit_cogs
            kaspi_profit = kaspi_revenue - kaspi_cogs
            kaspi_margin = (kaspi_profit / kaspi_revenue * 100) if kaspi_revenue > 0 else 0

            # Annualized turns (52 weeks)
            kaspi_turns = 0
            if avg_stock > 0 and kaspi_cogs > 0:
                weekly_cogs = kaspi_cogs / (period_days / 7)
                kaspi_turns = (weekly_cogs / (avg_stock * unit_cogs)) * 52

            kpis.append(PilotKPI(
                sku_key=pilot.sku_key,
                channel="KASPI",
                period_start=period_start.isoformat(),
                period_end=today.isoformat(),
                units_sold=kaspi_units,
                revenue_kzt=kaspi_revenue,
                cogs_kzt=kaspi_cogs,
                gross_profit_kzt=kaspi_profit,
                profit_margin_pct=kaspi_margin,
                avg_stock=avg_stock * pilot.kaspi_weight,
                turns_annualized=kaspi_turns,
                days_oos=days_oos,
            ))

            # Calculate WB KPI
            wb_units = wb_data["units_sold"] if wb_data else 0
            wb_revenue = wb_data["revenue"] if wb_data else 0
            wb_cogs = wb_units * unit_cogs
            wb_profit = wb_revenue - wb_cogs
            wb_margin = (wb_profit / wb_revenue * 100) if wb_revenue > 0 else 0

            wb_turns = 0
            if avg_stock > 0 and wb_cogs > 0:
                weekly_cogs = wb_cogs / (period_days / 7)
                wb_turns = (weekly_cogs / (avg_stock * unit_cogs)) * 52

            kpis.append(PilotKPI(
                sku_key=pilot.sku_key,
                channel="WB",
                period_start=period_start.isoformat(),
                period_end=today.isoformat(),
                units_sold=wb_units,
                revenue_kzt=wb_revenue,
                cogs_kzt=wb_cogs,
                gross_profit_kzt=wb_profit,
                profit_margin_pct=wb_margin,
                avg_stock=avg_stock * pilot.wb_weight,
                turns_annualized=wb_turns,
                days_oos=0,  # WB OOS tracked separately
            ))

        conn.close()

    except Exception:
        pass

    return kpis


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

def export_pilot_recommendations(
    recommendations: list[ChannelRecommendation],
    output_path: Path = None,
) -> Optional[Path]:
    """Export pilot recommendations to CSV."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / f"pilot_recommendations_{date.today().isoformat()}.csv"

    try:
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "sku_key", "channel", "recommended_qty", "demand_daily",
                "current_stock", "rop", "status", "unit_cost_kzt",
                "total_value_kzt", "roic_pct"
            ])

            for rec in recommendations:
                writer.writerow([
                    rec.sku_key, rec.channel, rec.recommended_qty,
                    f"{rec.demand_daily:.2f}", rec.current_stock, rec.rop,
                    rec.status, f"{rec.unit_cost_kzt:.0f}",
                    f"{rec.total_value_kzt:.0f}", f"{rec.roic_pct:.1f}"
                ])

        return output_path
    except Exception:
        return None


def export_pilot_kpis(
    kpis: list[PilotKPI],
    output_path: Path = None,
) -> Optional[Path]:
    """Export pilot KPIs to CSV."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / f"pilot_kpis_{date.today().isoformat()}.csv"

    try:
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "sku_key", "channel", "period_start", "period_end",
                "units_sold", "revenue_kzt", "cogs_kzt", "gross_profit_kzt",
                "profit_margin_pct", "avg_stock", "turns_annualized", "days_oos"
            ])

            for kpi in kpis:
                writer.writerow([
                    kpi.sku_key, kpi.channel, kpi.period_start, kpi.period_end,
                    kpi.units_sold, f"{kpi.revenue_kzt:.0f}", f"{kpi.cogs_kzt:.0f}",
                    f"{kpi.gross_profit_kzt:.0f}", f"{kpi.profit_margin_pct:.1f}",
                    f"{kpi.avg_stock:.1f}", f"{kpi.turns_annualized:.1f}", kpi.days_oos
                ])

        return output_path
    except Exception:
        return None


def generate_pilot_summary(
    recommendations: list[ChannelRecommendation],
    kpis: list[PilotKPI],
) -> dict:
    """Generate summary statistics for the pilot."""
    summary = {
        "total_skus": len(set(r.sku_key for r in recommendations)),
        "kaspi_recommendations": len([r for r in recommendations if r.channel == "KASPI"]),
        "wb_recommendations": len([r for r in recommendations if r.channel == "WB"]),
        "total_recommended_qty": sum(r.recommended_qty for r in recommendations),
        "total_recommended_value_kzt": sum(r.total_value_kzt for r in recommendations),
        "kaspi_total_revenue": sum(k.revenue_kzt for k in kpis if k.channel == "KASPI"),
        "wb_total_revenue": sum(k.revenue_kzt for k in kpis if k.channel == "WB"),
        "kaspi_total_profit": sum(k.gross_profit_kzt for k in kpis if k.channel == "KASPI"),
        "wb_total_profit": sum(k.gross_profit_kzt for k in kpis if k.channel == "WB"),
        "reorder_count": len([r for r in recommendations if r.status == "REORDER"]),
    }

    # Calculate channel comparison
    total_revenue = summary["kaspi_total_revenue"] + summary["wb_total_revenue"]
    if total_revenue > 0:
        summary["kaspi_revenue_pct"] = (summary["kaspi_total_revenue"] / total_revenue) * 100
        summary["wb_revenue_pct"] = (summary["wb_total_revenue"] / total_revenue) * 100
    else:
        summary["kaspi_revenue_pct"] = 0
        summary["wb_revenue_pct"] = 0

    return summary


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Multi-Channel Pilot Runner (Part 7C)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check pilot status
    python scripts/run_multichannel_pilot.py --status

    # Dry-run recommendations
    python scripts/run_multichannel_pilot.py --dry-run

    # Generate and export recommendations
    python scripts/run_multichannel_pilot.py

    # Export KPIs for last 7 days
    python scripts/run_multichannel_pilot.py --export-kpi --days 7

    # Initialize config table
    python scripts/run_multichannel_pilot.py --init-config
        """
    )

    parser.add_argument("--status", action="store_true", help="Show pilot status only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    parser.add_argument("--export-kpi", action="store_true", help="Export KPIs")
    parser.add_argument("--init-config", action="store_true", help="Initialize config table")
    parser.add_argument("--days", type=int, default=7, help="KPI period in days")
    parser.add_argument("--db", type=str, help="Database path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    # Initialize config mode
    if args.init_config:
        print("Initializing pilot configuration...")

        if init_pilot_config(db_path):
            print("  Created dim_pilot_skus table")

        config = load_pilot_config()
        if not config.get("pilot_skus"):
            # Create example config
            config["pilot_skus"] = [
                {
                    "sku_key": "EXAMPLE_SKU_1",
                    "kaspi_weight": 0.7,
                    "wb_weight": 0.3,
                    "active": False,
                    "notes": "Example - set active=true and update sku_key"
                }
            ]
            save_pilot_config(config)
            print(f"  Created example config: {CONFIG_PATH}")
            print("\nEdit config/pilot_skus.json to add pilot SKUs")

        return 0

    # Load pilot configuration
    config = load_pilot_config()
    pilot_skus = get_pilot_skus(config)

    print("=" * 60)
    print("MULTI-CHANNEL PILOT (Part 7C)")
    print("=" * 60)
    print(f"Config: {CONFIG_PATH if CONFIG_PATH.exists() else 'database'}")
    print(f"Pilot SKUs: {len(pilot_skus)}")
    print(f"Max allowed: {config.get('max_pilot_skus', 20)}")
    print()

    if args.status:
        if pilot_skus:
            print("Active Pilot SKUs:")
            for p in pilot_skus:
                print(f"  {p.sku_key}: Kaspi {p.kaspi_weight*100:.0f}% / WB {p.wb_weight*100:.0f}%")
        else:
            print("No active pilot SKUs configured")
            print("\nTo add pilot SKUs:")
            print("  1. Run: python scripts/run_multichannel_pilot.py --init-config")
            print("  2. Edit: config/pilot_skus.json")
        return 0

    if not pilot_skus:
        print("No active pilot SKUs. Run --init-config to set up.")
        return 1

    # Generate recommendations
    print("Generating channel-weighted recommendations...")
    recommendations = generate_channel_recommendations(db_path, pilot_skus)

    if recommendations:
        print(f"\nRecommendations: {len(recommendations)}")

        kaspi_recs = [r for r in recommendations if r.channel == "KASPI"]
        wb_recs = [r for r in recommendations if r.channel == "WB"]

        print(f"  KASPI: {len(kaspi_recs)} SKUs, {sum(r.recommended_qty for r in kaspi_recs)} units")
        print(f"  WB: {len(wb_recs)} SKUs, {sum(r.recommended_qty for r in wb_recs)} units")

        if args.verbose:
            print("\nDetails:")
            for rec in recommendations:
                print(f"  {rec.sku_key} [{rec.channel}]: {rec.recommended_qty} units ({rec.status})")

    # Calculate KPIs
    print(f"\nCalculating KPIs (last {args.days} days)...")
    kpis = calculate_pilot_kpis(db_path, pilot_skus, args.days)

    if kpis:
        summary = generate_pilot_summary(recommendations, kpis)

        print(f"\nPilot Summary:")
        print(f"  Total Revenue: {summary['kaspi_total_revenue'] + summary['wb_total_revenue']:,.0f} KZT")
        print(f"    KASPI: {summary['kaspi_total_revenue']:,.0f} KZT ({summary['kaspi_revenue_pct']:.1f}%)")
        print(f"    WB: {summary['wb_total_revenue']:,.0f} KZT ({summary['wb_revenue_pct']:.1f}%)")
        print(f"  Total Profit: {summary['kaspi_total_profit'] + summary['wb_total_profit']:,.0f} KZT")

    # Export if not dry-run
    if not args.dry_run:
        print("\nExporting...")

        rec_path = export_pilot_recommendations(recommendations)
        if rec_path:
            print(f"  Recommendations: {rec_path}")

        if args.export_kpi or kpis:
            kpi_path = export_pilot_kpis(kpis)
            if kpi_path:
                print(f"  KPIs: {kpi_path}")

    else:
        print("\n[DRY-RUN] No files written")

    return 0


if __name__ == "__main__":
    sys.exit(main())
