#!/usr/bin/env python3
"""
Generate PO dashboard data for webapp.
Outputs JSON with SKU-level and size-level PO recommendations.

Uses DemandEstimator for OOS-aware demand calculation with anchor data blending.
ROIC shown for info (not filtered). All active SKUs included.
Data cutoff: Yesterday in Asia/Almaty timezone.
"""

import sqlite3
import os
import json
import statistics
import csv
from datetime import date, timedelta
from pathlib import Path
from math import ceil
from dataclasses import dataclass, asdict
from typing import Optional, Any
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db.queries import (
    get_size_current_stock,
    get_size_inbound,
    get_sku_age_days,
    get_cutoff_date_almaty
)
from core.config.inventory_params import get_params
from core.config.business_params import get_demand_overrides
from core.calc.demand_estimator import DemandEstimator, ConfidenceLevel, OOSType
from core.calc.stock_timeline import StockTimelineBuilder
from core.calc.economics import calc_cogs, calc_net_rev, calc_delivery_fee
from core.po.blackout import adjust_po_dates, CNY_2026

# Constants
DB_PATH = PROJECT_ROOT / "db" / "app.db"
ANCHOR_FILE = PROJECT_ROOT / "excel" / "D_size_mix_reference.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DIAGNOSTICS_PATH = PROJECT_ROOT / "exports" / "demand_diagnostics.csv"
STOCK_DIAGNOSTICS_PATH = PROJECT_ROOT / "exports" / "stock_rebuild_diagnostics.csv"
SUPPLIER_EXPORT_PATH = PROJECT_ROOT / "exports" / "po_supplier_export"
SUPPLIER_SUMMARY_PATH = PROJECT_ROOT / "exports" / "po_supplier_summary"
ROIC_THRESHOLD = 0.15  # 15% - for display only, not filtering

# Valid size codes (filter out messy data like 'CB', '0', 'DRIVE', 'NAN')
VALID_SIZES = {'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', 'XS',
               '26', '28', '30', '32', '34', '36', '38', '40', '42',
               'ONE_SIZE', 'ONESIZE', 'OS'}

# PO-5 prep-days override (supplier will finish faster pre-holiday)
PO5_PREP_DAYS_OVERRIDE = 18

# Size-mix proxy mapping for SKUs that need demand distribution by size
SIZE_MIX_PROXY = {
    "CL_NEW-CLO_MEN_TAICI_BLACK": "CL_NEW-CLO_MEN_TAICI_WHITE",
}


def get_stock_snapshot_date() -> str:
    """Get the latest stock snapshot date from database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    result = conn.execute(
        "SELECT MAX(snapshot_date) as latest FROM fact_inventory_snapshot_size"
    ).fetchone()
    conn.close()

    if result and result['latest']:
        return result['latest']
    # Fallback to yesterday
    return (date.today() - timedelta(days=1)).isoformat()


# Use proper cutoff date (yesterday Asia/Almaty)
CUTOFF_DATE = get_cutoff_date_almaty()
DATA_CUTOFF = CUTOFF_DATE.isoformat()

# Stock snapshot date (lazy; avoid DB access at import time)
STOCK_DATE = (date.today() - timedelta(days=1)).isoformat()
TODAY = date.fromisoformat(STOCK_DATE)  # Use stock date as "today" for calculations


@dataclass
class SizePOLine:
    """Size-level PO recommendation."""
    sku_key: str
    sku_id: str
    size: str
    stock: int
    inbound: int  # Snapshot inbound (from DB)
    active_inbound: int  # POs arriving BETWEEN msg_date AND arr_date
    inbound_total: int  # All POs arriving before arr_date (from TODAY)
    days_until_arrival: int  # Lead time from msg_date to arr_date
    consumption_until_arrival: float  # D × L (msg_date to arr_date only)
    pre_arrival: int  # Projected stock at arrival date
    d_size: float  # Daily demand for this size
    t_post_days: float  # Target coverage days post-arrival
    target: float  # Target stock post-arrival
    rop_size: float
    deficit_size: int
    order_qty: int
    weight_kg: float
    prep_days: int
    po_send_date: str
    po_message_date: str
    est_arr_date: str  # Estimated arrival date
    pre_arr_doc: float  # Days of coverage before arrival
    post_arr_doc: float  # Days of coverage after order arrives
    roic_pct: float
    notes: str


@dataclass
class SkuPOLine:
    """SKU-level PO summary."""
    sku_key: str
    sku_name: str
    stock: int
    inbound: int  # Snapshot inbound (from DB)
    active_inbound: int  # POs arriving BETWEEN msg_date AND arr_date
    inbound_total: int  # All POs arriving before arr_date (from TODAY)
    days_until_arrival: int  # Lead time from msg_date to arr_date
    consumption_until_arrival: float  # D × L (msg_date to arr_date only)
    pre_arrival: int  # Projected stock at arrival date
    d_sku: float  # Blended demand (d_final)
    t_post_days: float  # Target coverage days post-arrival
    target: float  # Target stock post-arrival
    rop_total: float
    deficit_total: int
    po_qty_total: int
    size_orders: dict[str, int]
    po_weight_kg: float
    prep_days: int
    po_send_date: str
    po_message_date: str
    est_arr_date: str  # Estimated arrival date
    pre_arr_doc: float  # Days of coverage before arrival
    post_arr_doc: float  # Days of coverage after order arrives
    monthly_profit: float  # unit_profit × d_sku × 30
    k_avg: float  # D×(L+R/2)×COGS + SS×COGS
    roic_pct: float
    profit_margin_pct: float  # (unit_profit / unit_cogs) × 100
    roic_below_threshold: bool  # True if ROIC < 15% (display warning)
    d_anchor: float  # Anchor demand
    d_data: float  # Data-driven demand
    d_model: float  # Availability-adjusted model demand (stock-first)
    anchor_weight: float  # Blend weight (0-1)
    availability_score: float  # Average availability (0-1)
    confidence: str  # HIGH, MEDIUM, LOW, ANCHOR_ONLY
    oos_type: str  # NONE, EXTENDED, INTERMITTENT, PARTIAL
    partial_oos_sizes: str  # Comma-separated list of OOS sizes
    notes: str


def calc_prep_days(po_weight_kg: float, product_type: str) -> int:
    """Clothes: CEILING(1.3 x (weight_kg / 100), 1). Electronics: 1."""
    if product_type and product_type.upper() in ('ELS', 'ELEC', 'ELECTRONICS'):
        return 1
    return max(1, ceil(1.3 * po_weight_kg / 100))


def calc_needed_by_date(current_stock: int, d_sku: float) -> date:
    """When will we run out?"""
    if d_sku <= 0:
        return TODAY + timedelta(days=365)  # No demand = not urgent
    days_of_cover = current_stock / d_sku
    return TODAY + timedelta(days=int(days_of_cover))


def calc_po_dates(needed_by: date, prep_days: int, L: int = 21) -> tuple[date, date]:
    """Calculate PO send and message dates."""
    po_send_date = needed_by - timedelta(days=L)
    po_message_date = po_send_date - timedelta(days=prep_days)
    return po_send_date, po_message_date


def persist_demand_estimates(
    conn: sqlite3.Connection,
    demand_results: list,
    overrides: dict[str, float] | None = None
) -> int:
    """Persist DemandEstimator outputs to fact_demand_estimates."""
    if not demand_results:
        return 0

    rows = []
    for result in demand_results:
        cutoff_date = (
            result.cutoff_date.isoformat()
            if hasattr(result.cutoff_date, "isoformat")
            else str(result.cutoff_date)
        )
        d_anchor = result.d_anchor or 0.0
        d_data = result.d_data or 0.0
        d_final = result.d_final or 0.0
        d_model = getattr(result, "d_model", d_final)
        d_peak = max(d_anchor, d_data, d_final)
        override_value = overrides.get(result.sku_key) if overrides else None
        if override_value is not None:
            d_final_with_override = float(override_value)
            override_applied = 1
        else:
            d_final_with_override = d_final
            override_applied = 0
        sigma_anchor = result.sigma_anchor or 0.0
        sigma_data = result.sigma_data or 0.0
        sigma_final = result.sigma_final or 0.0
        anchor_weight = result.anchor_weight or 0.0
        w = anchor_weight
        calendar_days = result.calendar_days or 0
        good_days = result.good_days or 0
        eligible_days = getattr(result, "eligible_days", good_days)
        oos_days = getattr(result, "oos_days_total", 0)
        unknown_days = getattr(
            result, "unknown_days", max(0, calendar_days - good_days)
        )
        availability_score = getattr(result, "availability_score", result.coverage_pct or 0.0)
        confidence = result.confidence.name if hasattr(result.confidence, "name") else str(result.confidence)
        oos_type = result.oos_type.name if hasattr(result.oos_type, "name") else str(result.oos_type)
        partial_oos_sizes = ",".join(result.partial_oos_sizes) if result.partial_oos_sizes else ""
        estimator_version = "stock_first_v1"

        rows.append(
            (
                result.sku_key,
                cutoff_date,
                d_anchor,
                d_data,
                d_model,
                d_peak,
                d_final,
                d_final_with_override,
                override_applied,
                override_value,
                sigma_anchor,
                sigma_data,
                sigma_final,
                anchor_weight,
                w,
                calendar_days,
                eligible_days,
                good_days,
                oos_days,
                unknown_days,
                availability_score,
                confidence,
                oos_type,
                partial_oos_sizes,
                estimator_version,
            )
        )

    cutoff_date = rows[0][1]
    conn.execute("DELETE FROM fact_demand_estimates WHERE cutoff_date = ?", (cutoff_date,))
    conn.executemany(
        """
        INSERT INTO fact_demand_estimates (
            sku_key, cutoff_date,
            d_anchor, d_data, d_model, d_peak, d_final,
            d_final_with_override, override_applied, override_value,
            sigma_anchor, sigma_data, sigma_final,
            anchor_weight, w, calendar_days, eligible_days, good_days,
            oos_days, unknown_days, availability_score,
            confidence, oos_type, partial_oos_sizes, estimator_version
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def _load_override_windows(
    conn: sqlite3.Connection,
    sku_keys: list[str]
) -> dict[str, dict]:
    if not sku_keys:
        return {}
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_demand_overrides'"
        )
        if not cursor.fetchone():
            return {}
        placeholders = ",".join(["?"] * len(sku_keys))
        rows = conn.execute(
            f"""
            SELECT sku_key, d_override, start_date, end_date
            FROM dim_demand_overrides
            WHERE sku_key IN ({placeholders})
            """,
            sku_keys,
        ).fetchall()
        return {
            row["sku_key"]: {
                "d_override": row["d_override"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
            }
            for row in rows
        }
    except Exception:
        return {}


def export_supplier_po(
    conn: sqlite3.Connection,
    size_lines: list[dict],
    cutoff_date: str,
) -> tuple[Path, Path] | None:
    """Export supplier-ready PO CSV + summary from PO-4 size lines."""
    if not size_lines:
        return None

    sku_keys = sorted({row["sku_key"] for row in size_lines})
    placeholders = ",".join(["?"] * len(sku_keys))
    sku_rows = conn.execute(
        f"""
        SELECT sku_key, base_cost_cny, weight_kg
        FROM dim_sku
        WHERE sku_key IN ({placeholders})
        """,
        sku_keys,
    ).fetchall()
    sku_meta = {
        row["sku_key"]: {
            "base_cost_cny": row["base_cost_cny"],
            "weight_kg": row["weight_kg"],
        }
        for row in sku_rows
    }

    export_rows = []
    total_units = 0
    total_cost = 0.0
    total_weight = 0.0

    for line in size_lines:
        qty = int(line.get("order_qty") or 0)
        if qty <= 0:
            continue
        meta = sku_meta.get(line["sku_key"], {})
        base_cost_cny = meta.get("base_cost_cny") or 0
        weight_per_unit = meta.get("weight_kg") or 0
        unit_cost = (
            calc_cogs(base_cost_cny, weight_per_unit)
            if base_cost_cny and weight_per_unit
            else 0.0
        )
        total_cost_line = unit_cost * qty
        weight_total = line.get("weight_kg") or (weight_per_unit * qty)

        export_rows.append(
            {
                "sku_id": line["sku_id"],
                "sku_key": line["sku_key"],
                "my_size": line["size"],
                "qty": qty,
                "unit_cost_kzt": round(unit_cost, 2),
                "total_cost_kzt": round(total_cost_line, 2),
                "weight_kg": round(weight_total, 2),
            }
        )
        total_units += qty
        total_cost += total_cost_line
        total_weight += weight_total

    if not export_rows:
        return None

    export_path = SUPPLIER_EXPORT_PATH.with_name(
        f"po_supplier_export_{cutoff_date}.csv"
    )
    summary_path = SUPPLIER_SUMMARY_PATH.with_name(
        f"po_supplier_summary_{cutoff_date}.md"
    )

    export_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(export_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sku_id",
                "sku_key",
                "my_size",
                "qty",
                "unit_cost_kzt",
                "total_cost_kzt",
                "weight_kg",
            ],
        )
        writer.writeheader()
        writer.writerows(export_rows)

    spend_by_sku = {}
    for row in export_rows:
        spend_by_sku[row["sku_key"]] = spend_by_sku.get(row["sku_key"], 0) + row["total_cost_kzt"]
    top_skus = sorted(spend_by_sku.items(), key=lambda x: x[1], reverse=True)[:10]

    override_info = _load_override_windows(
        conn,
        ["CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE51_WHITE"],
    )

    override_lines = []
    for sku_key in ["CL_OC_MEN_LINE52_BLACK", "CL_OC_MEN_LINE51_WHITE"]:
        info = override_info.get(sku_key)
        if info:
            override_lines.append(
                f"- {sku_key}: D={info['d_override']} (window {info['start_date']} → {info['end_date']})"
            )
        else:
            override_lines.append(f"- {sku_key}: override not found")

    summary = [
        f"# Supplier PO Summary ({cutoff_date})",
        "",
        f"- Total units: {total_units}",
        f"- Total cost (KZT): {total_cost:,.2f}",
        f"- Total weight (kg): {total_weight:,.2f}",
        "",
        "## Top 10 SKUs by spend",
        *[f"- {sku}: {cost:,.2f} KZT" for sku, cost in top_skus],
        "",
        "## Demand overrides (time-boxed)",
        *override_lines,
    ]

    summary_path.write_text("\n".join(summary))
    return export_path, summary_path


def get_all_active_skus(conn) -> list[dict]:
    """Get all active SKUs with their attributes."""
    cursor = conn.execute("""
        SELECT
            sku_key,
            model,
            color,
            base_cost_cny,
            weight_kg,
            product_type
        FROM dim_sku
        WHERE active_flag = 1
    """)
    return [dict(row) for row in cursor.fetchall()]


def filter_valid_sizes(data: dict) -> dict:
    """Filter to only valid size codes."""
    return {k: v for k, v in data.items() if k.upper() in VALID_SIZES or k in VALID_SIZES}


def get_size_sales_history_with_cutoff(
    conn,
    sku_key: str,
    cutoff_date: str,
    days: int = 90
) -> dict[str, list[int]]:
    """Get daily sales history by size, using cutoff date instead of today."""
    from datetime import datetime, timedelta

    end_date = datetime.fromisoformat(cutoff_date).date()
    start_date = end_date - timedelta(days=days)

    # Get all sizes for this SKU
    sizes_result = conn.execute("""
        SELECT DISTINCT my_size FROM dim_sku_size WHERE sku_key = ?
    """, (sku_key,)).fetchall()
    sizes = [row['my_size'] for row in sizes_result]

    if not sizes:
        return {}

    # Get sales data
    sales_data = conn.execute("""
        SELECT sale_date, my_size, units
        FROM fact_sales_daily_size
        WHERE sku_key = ?
          AND sale_date >= ?
          AND sale_date <= ?
        ORDER BY sale_date
    """, (sku_key, start_date.isoformat(), end_date.isoformat())).fetchall()

    # Build date -> size -> units mapping
    sales_by_date = {}
    for row in sales_data:
        d = row['sale_date']
        if d not in sales_by_date:
            sales_by_date[d] = {}
        sales_by_date[d][row['my_size']] = row['units']

    # Generate complete date list
    date_list = []
    current = start_date
    while current <= end_date:
        date_list.append(current.isoformat())
        current += timedelta(days=1)

    # Build result
    result = {}
    for size in sizes:
        result[size] = []
        for d in date_list:
            units = sales_by_date.get(d, {}).get(size, 0)
            result[size].append(units)

    return result


def calc_d_sku_simple(size_sales_90d: dict[str, int]) -> float:
    """Calculate D_sku from 90-day sales totals."""
    total_sales = sum(size_sales_90d.values())
    return total_sales / 90.0


def calc_roic_manual(
    d_sku: float,
    ss_total: float,
    unit_cogs: float,
    unit_profit: float,
    L: int = 21,
    R: int = 10
) -> float:
    """
    Calculate ROIC manually (bypasses OOS filter issues).

    K_avg = D × (L + R/2) × COGS + SS_total × COGS
    Monthly_ROIC = (Unit_profit × D × 30) / K_avg
    """
    if d_sku <= 0 or unit_cogs <= 0:
        return 0.0

    # Average invested capital
    cycle_stock_value = d_sku * (L + R / 2) * unit_cogs
    safety_stock_value = ss_total * unit_cogs
    k_avg = cycle_stock_value + safety_stock_value

    if k_avg <= 0:
        return 0.0

    # Monthly profit from sales
    monthly_profit = unit_profit * d_sku * 30

    return monthly_profit / k_avg


def calc_economics(
    d_sku: float,
    ss_total: float,
    unit_cogs: float,
    unit_profit: float,
    L: int = 21,
    R: int = 10
) -> tuple[float, float, float, float]:
    """
    Calculate economics metrics for PO dashboard.

    Returns: (monthly_profit, k_avg, roic_pct, profit_margin_pct)
    """
    if unit_cogs <= 0:
        return 0.0, 0.0, 0.0, 0.0

    monthly_profit = unit_profit * d_sku * 30
    k_avg = d_sku * (L + R / 2) * unit_cogs + ss_total * unit_cogs
    roic_pct = (monthly_profit / k_avg * 100) if k_avg > 0 else 0.0
    profit_margin_pct = (unit_profit / unit_cogs) * 100

    return monthly_profit, k_avg, roic_pct, profit_margin_pct


@dataclass
class ManualPODraft:
    """Manual PO calculation result."""
    sku_key: str
    d_sku: float
    ss_total: float
    rop_sku: float
    target: float
    t_post: float  # Target coverage days post-arrival
    current_stock_total: int
    inbound_stock_total: int
    pre_arrival: int
    consumption_until_arrival: float  # D × effective_L
    total_qty: int
    should_order: bool
    roic_monthly: float
    effective_L: int  # Actual lead time including prep days
    # Size allocations: size -> (stock, inbound, d_size, rop, target, order_qty, consumption)
    size_allocations: dict


def calc_po_draft_manual(
    sku_key: str,
    size_sales_90d: dict[str, int],
    size_current: dict[str, int],
    size_inbound: dict[str, int],
    sigma_sku: float,
    unit_cogs: float,
    unit_profit: float,
    weight_per_unit: float,
    product_type: str,
    params,
    d_sku_blended: float = None,  # Blended demand from DemandEstimator
    size_demands: dict[str, float] = None  # Blended per-size demands
) -> ManualPODraft:
    """
    Calculate PO draft with pre-arrival stock projection.

    Formulas (per Master_Inventory_Rules_v6.md):
    - Pre_i = Current_i + Inbound_i - (D_i × effective_L)
    - T_post = R + (SS_total / D_sku)  # Days of coverage post-arrival (NO L!)
    - Target_i = D_i × T_post = D_i × R + SS_i
    - Order_qty_i = max(0, Target_i - Pre_i)

    NOTE: Lead time L is accounted in pre-arrival consumption, NOT in T_post.
    effective_L = L + prep_days
    """
    L = params.L
    R = params.R
    z = params.z
    TV = params.TV
    B = params.B  # Buffer factor (product-type dependent)

    # SKU-level demand (use blended if provided)
    if d_sku_blended is not None and d_sku_blended > 0:
        d_sku = d_sku_blended
    else:
        total_sales = sum(size_sales_90d.values())
        d_sku = total_sales / 90.0

    # Safety stock
    ss_demand = z * sigma_sku * (L ** 0.5)
    ss_floor = d_sku * B
    ss_mix = TV * d_sku * L
    ss_total = ss_demand + ss_floor + ss_mix

    # ROP and Target (per Master_Inventory_Rules_v6.md)
    # T_post = R + (SS/D) = days of coverage post-arrival (NO L in T_post!)
    # Target = D × T_post = D × R + SS
    # NOTE: Lead time L is in pre-arrival consumption, not T_post
    rop_sku = d_sku * L + ss_total
    T_post = R + (ss_total / d_sku) if d_sku > 0 else R
    target = d_sku * T_post  # = R * d_sku + ss_total

    # Stock totals
    current_stock_total = sum(size_current.values())
    inbound_stock_total = sum(size_inbound.values())

    # === FIX #1: Estimate prep days BEFORE calculating order qty ===
    # This avoids chicken-egg: prep depends on qty, qty depends on prep
    rough_order = max(0, target - current_stock_total)
    if product_type.upper() in ('ELS', 'ELEC', 'ELECTRONICS'):
        prep_days = 1
    else:
        weight_estimate = rough_order * weight_per_unit
        prep_days = max(1, ceil(1.3 * weight_estimate / 100))

    # === FIX #2: Use effective lead time (L + prep) for consumption ===
    effective_L = L + prep_days

    # Pre-arrival = Stock + Inbound - Consumption during effective lead time
    consumption_sku = d_sku * effective_L
    pre_arrival = max(0, current_stock_total + inbound_stock_total - consumption_sku)

    # T_post already calculated above (R + SS/D, no L)

    # Size mix allocation
    all_sizes = set(size_sales_90d.keys()) | set(size_current.keys())
    if size_demands:
        all_sizes = all_sizes | set(size_demands.keys())

    size_allocations = {}
    total_qty = 0  # Will be sum of size allocations

    # Total sales for mix calculation (only if not using blended demands)
    total_sales = sum(size_sales_90d.values()) if not size_demands else 0

    for size in all_sizes:
        stock = size_current.get(size, 0)
        inbound = size_inbound.get(size, 0)

        # Size demand: prefer blended size_demands if available
        if size_demands and size in size_demands:
            d_size = size_demands[size]
            # Calculate mix from blended demands
            mix = d_size / d_sku if d_sku > 0 else 0.0
        else:
            # Fallback to sales-based calculation
            sales_90d_size = size_sales_90d.get(size, 0)
            d_size = sales_90d_size / 90.0
            if total_sales > 0:
                raw_mix = sales_90d_size / total_sales
                mix = max(0.03, min(0.40, raw_mix)) if raw_mix > 0 else 0.03
            else:
                mix = 1.0 / max(len(all_sizes), 1)

        # Size-level Target = D_size × T_post
        target_size = d_size * T_post

        # Size-level ROP (for reference)
        rop_size = d_size * L + (mix * ss_total if d_sku > 0 else 0)

        # Pre-arrival projection: stock at arrival date
        # Pre_i = Current_i + Inbound_i - (D_i × L_effective)
        consumption_until_arrival = d_size * effective_L
        pre_arrival_size = max(0, stock + inbound - consumption_until_arrival)

        # Order quantity = gap between target and pre-arrival
        order_qty_size = max(0, int(round(target_size - pre_arrival_size)))

        size_allocations[size] = {
            'stock': stock,
            'inbound': inbound,
            'd_size': round(d_size, 4),
            'mix': round(mix, 4),
            'rop': round(rop_size, 1),
            'target': round(target_size, 1),
            'pre_arrival': int(pre_arrival_size),
            'consumption': round(consumption_until_arrival, 2),  # Consumption until arrival
            't_post': round(T_post, 1),  # Target coverage days
            'order_qty': order_qty_size
        }
        total_qty += order_qty_size

    # Should order?
    should_order = pre_arrival < rop_sku or total_qty > 0

    # ROIC
    roic = calc_roic_manual(d_sku, ss_total, unit_cogs, unit_profit, L, R)

    return ManualPODraft(
        sku_key=sku_key,
        d_sku=d_sku,
        ss_total=ss_total,
        rop_sku=rop_sku,
        target=target,
        t_post=T_post,
        current_stock_total=current_stock_total,
        inbound_stock_total=inbound_stock_total,
        pre_arrival=int(pre_arrival),
        consumption_until_arrival=consumption_sku,
        total_qty=total_qty,
        should_order=should_order,
        roic_monthly=roic,
        effective_L=effective_L,
        size_allocations=size_allocations
    )


def generate_po_data(
    fixture_cases: Optional[list[dict]] = None,
    *,
    fixture_cutoff_date: Optional[str] = None,
    fixture_stock_date: Optional[str] = None,
    fixture_generated_at: Optional[str] = None,
) -> dict:
    """Main function to generate PO dashboard data using DemandEstimator."""

    use_fixture = fixture_cases is not None
    original_context = (CUTOFF_DATE, DATA_CUTOFF, STOCK_DATE, TODAY)

    if use_fixture:
        cutoff_str = fixture_cutoff_date or "2026-01-01"
        stock_str = fixture_stock_date or cutoff_str
        cutoff_dt = date.fromisoformat(cutoff_str)
        today_dt = date.fromisoformat(stock_str)
        globals()["CUTOFF_DATE"] = cutoff_dt
        globals()["DATA_CUTOFF"] = cutoff_dt.isoformat()
        globals()["STOCK_DATE"] = stock_str
        globals()["TODAY"] = today_dt
    else:
        stock_str = get_stock_snapshot_date()
        globals()["STOCK_DATE"] = stock_str
        globals()["TODAY"] = date.fromisoformat(stock_str)

    conn = None
    if not use_fixture:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

    params = get_params()

    demand_lookup: dict[str, Any] = {}
    skipped_skus: list[dict] = []
    overrides: dict[str, float] = {}

    if not use_fixture:
        # Initialize DemandEstimator with DB anchors (stock-first approach)
        print("Initializing DemandEstimator (stock-first, DB anchors)...")
        estimator = DemandEstimator(
            DB_PATH,
            anchor_file=ANCHOR_FILE,  # Fallback if DB empty
            use_db_anchors=True  # Prefer dim_anchor table
        )
        print(f"  Cutoff date: {estimator.cutoff_date}")
        print(f"  Anchor SKUs loaded: {len(estimator.anchor_data)}")

        # Get demand estimates for all SKUs
        print("Estimating demand for all SKUs...")
        demand_results, skipped_skus = estimator.estimate_all(store_codes=["UNIVERSAL"])
        print(f"  Estimated: {len(demand_results)} SKUs")
        print(f"  Skipped: {len(skipped_skus)} SKUs")

        overrides = get_demand_overrides(as_of_date=CUTOFF_DATE, db_path=DB_PATH)

        # Export demand diagnostics
        if demand_results:
            estimator.export_diagnostics(demand_results, DIAGNOSTICS_PATH)
            print(f"  Demand diagnostics exported to: {DIAGNOSTICS_PATH}")
            persisted = persist_demand_estimates(conn, demand_results, overrides=overrides)
            print(f"  Demand estimates persisted: {persisted} rows")

        # Export stock timeline diagnostics (if available)
        stock_diags = getattr(estimator, "_stock_diagnostics", None)
        if stock_diags:
            builder = StockTimelineBuilder(DB_PATH)
            builder.export_diagnostics_csv(stock_diags, STOCK_DIAGNOSTICS_PATH)
            print(f"  Stock rebuild diagnostics exported to: {STOCK_DIAGNOSTICS_PATH}")

        # Build demand lookup: sku_key -> SKUDemandResult
        demand_lookup = {r.sku_key: r for r in demand_results}

        # Get all active SKUs
        skus = get_all_active_skus(conn)
        print(f"Found {len(skus)} active SKUs in dim_sku")
    else:
        fixture_by_sku = {case["sku_key"]: case for case in fixture_cases}
        skus = [
            {
                "sku_key": sku_key,
                "model": "",
                "color": "",
                "base_cost_cny": 1.0,
                "weight_kg": 0.5,
                "product_type": "CL",
            }
            for sku_key in fixture_by_sku
        ]

    sku_lines = []
    size_lines = []
    skipped_no_demand = 0
    skipped_no_stock = 0
    skipped_no_order = 0
    low_roic_count = 0

    for sku in skus:
        sku_key = sku['sku_key']
        sku_name = f"{sku.get('model', '')} {sku.get('color', '')}".strip() or sku_key

        # Skip if missing cost data (can't calculate ROIC)
        if sku['base_cost_cny'] is None:
            continue

        notes_list = []
        override_value = None

        if use_fixture:
            case = fixture_by_sku[sku_key]
            demand_result = None
            has_demand = True
            size_current = filter_valid_sizes(case["size_current_stock"])
            size_inbound = filter_valid_sizes(case["size_inbound_stock"])
        else:
            # Check if we have demand estimate for this SKU
            demand_result = demand_lookup.get(sku_key)
            has_demand = demand_result is not None
            if not has_demand:
                skipped_no_demand += 1
                notes_list.append("NO_DEMAND_ESTIMATE")

            # Get current stock from latest snapshot date
            size_current_raw = conn.execute("""
                SELECT my_size, current_stock, inbound_stock
                FROM fact_inventory_snapshot_size
                WHERE sku_key = ?
                  AND snapshot_date = ?
            """, (sku_key, STOCK_DATE)).fetchall()

            size_current = filter_valid_sizes({row['my_size']: row['current_stock'] for row in size_current_raw})
            size_inbound = filter_valid_sizes({row['my_size']: row['inbound_stock'] for row in size_current_raw})

        # Track SKUs with no stock snapshot
        has_stock = len(size_current) > 0
        if not has_stock:
            skipped_no_stock += 1
            notes_list.append("NO_STOCK_SNAPSHOT")

        # Get SKU cost/profit for ROIC
        if use_fixture:
            base_cost_cny = sku['base_cost_cny'] or 50
            weight_kg = sku['weight_kg'] or 0.5
            product_type = sku['product_type'] or 'CL'
            unit_cogs = case["unit_cogs"]
            unit_profit = case["unit_profit"]
        else:
            base_cost_cny = sku['base_cost_cny'] or 50
            weight_kg = sku['weight_kg'] or 0.5
            product_type = sku['product_type'] or 'CL'

            # COGS calculation (using economics.py - single source of truth)
            # Formula: COGS = base_cost_cny × CNY_KZT + weight_kg × 2.66 × 530
            unit_cogs = calc_cogs(base_cost_cny, weight_kg)

            # Get average sell price
            price_row = conn.execute("""
                SELECT AVG(sell_price_kzt) as avg_price
                FROM fact_sales
                WHERE sku_key = ?
                AND order_date >= date(?, '-90 days')
                AND order_date <= ?
            """, (sku_key, DATA_CUTOFF, DATA_CUTOFF)).fetchone()

            avg_sell_price = price_row['avg_price'] if price_row and price_row['avg_price'] else 15000

            # Calculate NET revenue (commission, delivery fee, VAT schedule)
            # Formula: (price * (1 - commission) - delivery_fee) * (1 - VAT)
            delivery_fee = calc_delivery_fee(avg_sell_price, weight_kg=weight_kg, delivery_type="city")
            avg_net_price = calc_net_rev(avg_sell_price, delivery_fee, as_of_date=CUTOFF_DATE)

            # Unit profit = NET revenue - COGS (not GROSS - COGS!)
            unit_profit = avg_net_price - unit_cogs

        # Use demand from DemandEstimator (blended d_final) or defaults
        if use_fixture:
            d_sku_blended = sum(case["size_sales_90d"].values()) / 90.0
            sigma_sku = case["sigma_sku"]
        elif has_demand:
            d_sku_blended = demand_result.d_final
            sigma_sku = demand_result.sigma_final
        else:
            d_sku_blended = 0.0
            sigma_sku = 0.0

        # Build size_demands from DemandEstimator (blended per-size demand)
        size_demands = {}
        size_sales_90d = {}  # Fallback for sizes not in demand_result
        if use_fixture:
            size_sales_90d = case["size_sales_90d"].copy()
            size_demands = {size: sales / 90.0 for size, sales in size_sales_90d.items()}
        elif has_demand:
            for size, size_result in demand_result.size_results.items():
                # Use blended d_size directly (includes anchor weighting)
                size_demands[size] = size_result.d_size
                # Also build 90d sales approximation for fallback
                size_sales_90d[size] = int(size_result.d_size * 90)

        size_demands = filter_valid_sizes(size_demands)
        size_sales_90d = filter_valid_sizes(size_sales_90d)

        # Renormalize size_demands to match SKU demand if invalid sizes were dropped
        if size_demands and d_sku_blended > 0:
            total_size_demand = sum(size_demands.values())
            if total_size_demand > 0 and abs(total_size_demand - d_sku_blended) > 0.001:
                scale = d_sku_blended / total_size_demand
                size_demands = {k: v * scale for k, v in size_demands.items()}
            size_sales_90d = {k: int(round(v * 90)) for k, v in size_demands.items()}

        if not use_fixture:
            override_value = overrides.get(sku_key)
            if override_value is not None:
                override_value = float(override_value)
                d_sku_blended = override_value
                notes_list.append(f"D_OVERRIDE={override_value}")
                total_size_demand = sum(size_demands.values()) if size_demands else 0
                if total_size_demand > 0:
                    scale = override_value / total_size_demand
                    size_demands = {k: v * scale for k, v in size_demands.items()}
                    size_sales_90d = {k: int(round(v * 90)) for k, v in size_demands.items()}

        if not use_fixture and d_sku_blended > 0 and not size_demands:
            proxy_key = SIZE_MIX_PROXY.get(sku_key)
            if proxy_key:
                proxy_result = demand_lookup.get(proxy_key)
                if proxy_result:
                    proxy_sizes = {size: res.d_size for size, res in proxy_result.size_results.items()}
                    proxy_sizes = filter_valid_sizes(proxy_sizes)
                    total_proxy = sum(proxy_sizes.values())
                    if total_proxy > 0:
                        scale = d_sku_blended / total_proxy
                        size_demands = {k: v * scale for k, v in proxy_sizes.items()}
                        notes_list.append(f"SIZE_MIX_PROXY={proxy_key}")

            if not size_demands:
                candidate_sizes = set(size_current.keys()) | set(size_inbound.keys()) | set(size_sales_90d.keys())
                candidate_sizes = filter_valid_sizes({k: 1 for k in candidate_sizes})
                if candidate_sizes:
                    per_size = d_sku_blended / len(candidate_sizes)
                    size_demands = {k: per_size for k in candidate_sizes.keys()}
                    notes_list.append("SIZE_MIX_FALLBACK=UNIFORM")

            if size_demands:
                size_sales_90d = {k: int(round(v * 90)) for k, v in size_demands.items()}

        # Generate PO draft with blended demands and pre-arrival projection
        # For SKUs without stock/demand data, create a placeholder draft
        draft = None
        alloc_override = None
        total_qty_override = None
        if has_stock or has_demand:
            try:
                draft = calc_po_draft_manual(
                    sku_key=sku_key,
                    size_sales_90d=size_sales_90d,
                    size_current=size_current,
                    size_inbound=size_inbound,
                    sigma_sku=sigma_sku,
                    unit_cogs=unit_cogs,
                    unit_profit=unit_profit,
                    weight_per_unit=weight_kg,
                    product_type=product_type,
                    params=params,
                    d_sku_blended=d_sku_blended,  # Pass blended SKU demand
                    size_demands=size_demands  # Pass blended size demands
                )
                if use_fixture:
                    # Fixture contract expects core/calc/size_allocation.generate_po_draft outputs
                    from core.calc.size_allocation import generate_po_draft as _generate_po_draft
                    fixture_draft = _generate_po_draft(
                        sku_key=case["sku_key"],
                        store_code=case["store_code"],
                        size_sales_90d=case["size_sales_90d"],
                        size_current_stock=case["size_current_stock"],
                        size_inbound_stock=case["size_inbound_stock"],
                        size_sales_history=case["size_sales_history"],
                        size_stock_history=case["size_stock_history"],
                        unit_cogs=case["unit_cogs"],
                        unit_profit=case["unit_profit"],
                        sigma_sku=case["sigma_sku"],
                        sku_age_days=case["sku_age_days"],
                    )
                    alloc_override = fixture_draft.allocations
                    total_qty_override = fixture_draft.total_qty
            except Exception as e:
                print(f"  Error generating draft for {sku_key}: {e}")
                draft = None

        # Track ROIC status (but don't filter!)
        roic_below_threshold = False
        if draft:
            roic_below_threshold = draft.roic_monthly < ROIC_THRESHOLD
            if roic_below_threshold:
                low_roic_count += 1
                notes_list.append(f"ROIC {draft.roic_monthly*100:.1f}% < 15%")

        # Track SKUs where no order is needed (but still include them with 0 qty)
        order_needed = draft and (draft.should_order and draft.total_qty > 0)
        if not order_needed:
            skipped_no_order += 1
            if "NO_DEMAND_ESTIMATE" not in notes_list and "NO_STOCK_SNAPSHOT" not in notes_list:
                notes_list.append("NO_ORDER_NEEDED")

        # Calculate values from draft or use defaults for missing data
        if draft:
            total_stock = draft.current_stock_total
            inbound_stock = draft.inbound_stock_total
            d_sku = draft.d_sku
            pre_arrival = draft.pre_arrival
            target_val = draft.target
            t_post_days = draft.t_post
            rop_sku = draft.rop_sku
            total_qty = total_qty_override if total_qty_override is not None else draft.total_qty
            roic_monthly = draft.roic_monthly
            size_allocs = alloc_override if alloc_override is not None else draft.size_allocations
            size_allocs_for_lines = draft.size_allocations
            effective_L = draft.effective_L
            consumption_until_arr = draft.consumption_until_arrival
        else:
            # Placeholder values for SKUs with no stock/demand
            total_stock = sum(size_current.values())
            inbound_stock = sum(size_inbound.values())
            d_sku = 0.0
            pre_arrival = total_stock + inbound_stock
            target_val = 0.0
            t_post_days = params.R  # Default T_post (R only, no L)
            rop_sku = 0.0
            total_qty = 0
            roic_monthly = 0.0
            size_allocs = {}
            size_allocs_for_lines = {}
            effective_L = params.L
            consumption_until_arr = 0.0

        size_orders = {}
        for size, alloc in size_allocs.items():
            if isinstance(alloc, dict):
                size_orders[size] = int(alloc.get('order_qty_adjusted', alloc.get('order_qty', 0)) or 0)
            else:
                size_orders[size] = int(
                    getattr(alloc, "order_qty_adjusted", getattr(alloc, "order_qty", 0)) or 0
                )

        # Calculate dates
        po_weight = weight_kg * total_qty
        prep_days = calc_prep_days(po_weight, product_type)

        # RECALCULATE effective_L with actual prep_days (fixes Days→Arr bug)
        # Days until arrival = prep_days + L (not just L!)
        effective_L = prep_days + params.L

        # Recalculate consumption with corrected effective_L
        consumption_until_arr = d_sku * effective_L

        # Message date is the "send message" date (today for PO-4)
        po_message = TODAY
        # PO send date is message date + prep days
        po_send = po_message + timedelta(days=prep_days)
        # Estimated arrival is send date + lead time L
        est_arr = po_send + timedelta(days=params.L)

        # Calculate days of coverage (DOC)
        if d_sku > 0:
            pre_arr_doc = pre_arrival / d_sku  # Days of coverage before arrival
            post_arr_doc = (pre_arrival + total_qty) / d_sku  # Days of coverage after order arrives
        else:
            pre_arr_doc = 999.0 if pre_arrival > 0 else 0.0
            post_arr_doc = 999.0 if (pre_arrival + total_qty) > 0 else 0.0

        # Calculate deficit (ROP - stock - inbound)
        deficit_total = max(0, int(rop_sku - total_stock - inbound_stock))

        # Extract demand result values or use defaults
        if use_fixture:
            d_final = d_sku_blended
            d_anchor = 0.0
            d_data = d_sku_blended
            d_model = d_sku_blended
            anchor_weight = 0.0
            availability_score = 0.0
            confidence = "FIXTURE"
            oos_type = "NONE"
            partial_oos_sizes = ""
        elif has_demand:
            d_final = demand_result.d_final
            d_anchor = demand_result.d_anchor
            d_data = demand_result.d_data
            d_model = getattr(demand_result, "d_model", d_final)
            anchor_weight = demand_result.anchor_weight
            availability_score = getattr(
                demand_result,
                "availability_score",
                getattr(demand_result, "coverage_pct", 0.0),
            )
            confidence = demand_result.confidence.name
            oos_type = demand_result.oos_type.name
            partial_oos_sizes = ",".join(demand_result.partial_oos_sizes)
        else:
            d_final = 0.0
            d_anchor = 0.0
            d_data = 0.0
            d_model = 0.0
            anchor_weight = 0.0
            availability_score = 0.0
            confidence = "NO_DATA"
            oos_type = "NONE"
            partial_oos_sizes = ""

        if override_value is not None:
            d_final = float(override_value)
            d_model = float(override_value)

        # Calculate economics for dashboard display
        ss_total = draft.ss_total if draft else 0.0
        monthly_profit, k_avg, _, profit_margin_pct = calc_economics(
            d_sku=d_final,
            ss_total=ss_total,
            unit_cogs=unit_cogs,
            unit_profit=unit_profit,
            L=params.L,
            R=params.R
        )

        # SKU-level line with DemandEstimator data (stock-first)
        # For PO-4, active_inbound=0 and inbound_total=0 (no previous POs)
        sku_line = SkuPOLine(
            sku_key=sku_key,
            sku_name=sku_name[:50] if sku_name else sku_key,
            stock=total_stock,
            inbound=inbound_stock,
            active_inbound=0,  # PO-4: no previous POs
            inbound_total=0,  # PO-4: no previous POs
            days_until_arrival=effective_L,  # Lead time including prep
            consumption_until_arrival=round(consumption_until_arr, 2),
            pre_arrival=pre_arrival,  # Projected stock at arrival
            d_sku=round(d_final, 3),  # Blended demand
            t_post_days=round(t_post_days, 1),  # Target coverage days
            target=round(target_val, 1),  # Target stock post-arrival
            rop_total=round(rop_sku, 1),
            deficit_total=deficit_total,
            po_qty_total=total_qty,
            size_orders=size_orders,
            po_weight_kg=round(po_weight, 2),
            prep_days=prep_days,
            po_send_date=po_send.isoformat(),
            po_message_date=po_message.isoformat(),
            est_arr_date=est_arr.isoformat(),  # Estimated arrival date
            pre_arr_doc=round(pre_arr_doc, 1),  # Days of coverage before arrival
            post_arr_doc=round(post_arr_doc, 1),  # Days of coverage after arrival
            monthly_profit=round(monthly_profit, 2),
            k_avg=round(k_avg, 2),
            roic_pct=round(roic_monthly * 100, 1),
            profit_margin_pct=round(profit_margin_pct, 1),
            roic_below_threshold=roic_below_threshold,
            d_anchor=round(d_anchor, 3),
            d_data=round(d_data, 3),
            d_model=round(d_model, 3),  # Availability-adjusted demand
            anchor_weight=round(anchor_weight, 2),
            availability_score=round(availability_score, 3),  # Stock-first availability
            confidence=confidence,
            oos_type=oos_type,
            partial_oos_sizes=partial_oos_sizes,  # Stock-first detected
            notes="; ".join(notes_list) if notes_list else ""
        )
        sku_lines.append(asdict(sku_line))

        # Size-level lines (include zero-order sizes for reconciliation)
        for size, alloc in size_allocs_for_lines.items():
            order_qty = alloc['order_qty']

            # Skip invalid sizes
            if size.upper() not in VALID_SIZES and size not in VALID_SIZES:
                continue

            size_stock = alloc['stock']
            size_inb = alloc['inbound']
            pre_arrival_size = alloc.get('pre_arrival', 0)
            target_size = alloc.get('target', 0)
            d_size_val = alloc.get('d_size', 0)
            size_consumption = alloc.get('consumption', 0)
            size_t_post = alloc.get('t_post', t_post_days)

            # Get ROP for this size
            rop_size = alloc['rop']

            deficit = max(0, int(rop_size - size_stock - size_inb))
            size_weight = weight_kg * order_qty

            # Size-level DOC
            if d_size_val > 0:
                size_pre_arr_doc = pre_arrival_size / d_size_val
                size_post_arr_doc = (pre_arrival_size + order_qty) / d_size_val
            else:
                size_pre_arr_doc = 999.0 if pre_arrival_size > 0 else 0.0
                size_post_arr_doc = 999.0 if (pre_arrival_size + order_qty) > 0 else 0.0

            size_line = SizePOLine(
                sku_key=sku_key,
                sku_id=f"{sku_key}_{size}",
                size=size,
                stock=size_stock,
                inbound=size_inb,
                active_inbound=0,  # PO-4: no previous POs
                inbound_total=0,  # PO-4: no previous POs
                days_until_arrival=effective_L,
                consumption_until_arrival=round(size_consumption, 2),
                pre_arrival=pre_arrival_size,
                d_size=round(d_size_val, 4),
                t_post_days=round(size_t_post, 1),
                target=round(target_size, 1),
                rop_size=round(rop_size, 1),
                deficit_size=deficit,
                order_qty=order_qty,
                weight_kg=round(size_weight, 2),
                prep_days=prep_days,
                po_send_date=po_send.isoformat(),
                po_message_date=po_message.isoformat(),
                est_arr_date=est_arr.isoformat(),
                pre_arr_doc=round(size_pre_arr_doc, 1),
                post_arr_doc=round(size_post_arr_doc, 1),
                roic_pct=round(roic_monthly * 100, 1),
                notes=""
            )
            size_lines.append(asdict(size_line))

    # === Prep Model B: shared prep days for CL, ELS=1 ===
    prep_model = "B"
    total_cl_weight = sum(
        s.get('po_weight_kg', 0.0) for s in sku_lines
        if s.get('po_qty_total', 0) > 0 and not s.get('sku_key', '').startswith('ELS_')
    )
    prep_days_clothes = calc_prep_days(total_cl_weight, "CL") if total_cl_weight > 0 else 1

    for sku_line in sku_lines:
        sku_key = sku_line.get('sku_key', '')
        if sku_key.startswith('ELS_'):
            new_prep = 1
        else:
            new_prep = prep_days_clothes

        if sku_line.get('prep_days') != new_prep:
            sku_line['prep_days'] = new_prep
            sku_line['days_until_arrival'] = new_prep + params.L
            sku_line['consumption_until_arrival'] = round(
                sku_line.get('d_sku', 0.0) * sku_line['days_until_arrival'], 2
            )
            msg_date = date.fromisoformat(sku_line['po_message_date'])
            send_date = msg_date + timedelta(days=new_prep)
            sku_line['po_send_date'] = send_date.isoformat()
            sku_line['est_arr_date'] = (send_date + timedelta(days=params.L)).isoformat()

    for size_line in size_lines:
        sku_key = size_line.get('sku_key', '')
        if sku_key.startswith('ELS_'):
            new_prep = 1
        else:
            new_prep = prep_days_clothes

        if size_line.get('prep_days') != new_prep:
            size_line['prep_days'] = new_prep
            size_line['days_until_arrival'] = new_prep + params.L
            size_line['consumption_until_arrival'] = round(
                size_line.get('d_size', 0.0) * size_line['days_until_arrival'], 2
            )
            msg_date = date.fromisoformat(size_line['po_message_date'])
            send_date = msg_date + timedelta(days=new_prep)
            size_line['po_send_date'] = send_date.isoformat()
            size_line['est_arr_date'] = (send_date + timedelta(days=params.L)).isoformat()

    # Sort by PO message date (most urgent first)
    sku_lines.sort(key=lambda x: x['po_message_date'])
    size_lines.sort(key=lambda x: (x['po_message_date'], x['sku_key'], x['size']))

    # Count SKUs with and without orders
    skus_with_orders = sum(1 for s in sku_lines if s['po_qty_total'] > 0)
    skus_without_orders = len(sku_lines) - skus_with_orders
    total_units = sum(s['po_qty_total'] for s in sku_lines)

    readiness_report = None
    day_complete_env = os.environ.get("AB_DAY_COMPLETE", "1").strip().lower()
    day_complete_ok = day_complete_env not in {"0", "false", "no"}
    if not use_fixture:
        from core.validation.production_readiness import evaluate_production_readiness

        readiness_payload = {
            "summary": {
                "total_skus": len(sku_lines),
                "skus_with_orders": skus_with_orders,
                "total_units": total_units,
                "no_demand_estimate": skipped_no_demand,
                "no_stock_snapshot": skipped_no_stock,
            },
            "sku_level": sku_lines,
            "stock_date": STOCK_DATE,
            "cutoff_date": DATA_CUTOFF,
            "sales_data_cutoff": DATA_CUTOFF,
        }
        readiness_report = evaluate_production_readiness(readiness_payload, db_path=DB_PATH)
        if not day_complete_ok:
            readiness_report.blockers.append("Day complete gate failed: sizes pending")
            print("\nPROVISIONAL: sizes pending; exports blocked.")
        if readiness_report.blockers:
            print("\nPRODUCTION READINESS BLOCKERS (export blocked):")
            for blocker in readiness_report.blockers:
                print(f"  - {blocker}")
        else:
            export_result = export_supplier_po(conn, size_lines, DATA_CUTOFF)
            if export_result:
                export_path, summary_path = export_result
                print(f"Supplier export written: {export_path}")
                print(f"Supplier summary written: {summary_path}")

    print(f"\nResults:")
    print(f"  Total SKUs in output: {len(sku_lines)}")
    print(f"    - With PO needed: {skus_with_orders}")
    print(f"    - With 0 qty (no order): {skus_without_orders}")
    print(f"  Flagged (no demand estimate): {skipped_no_demand}")
    print(f"  Flagged (no stock snapshot): {skipped_no_stock}")
    print(f"  Flagged (no order needed): {skipped_no_order}")
    print(f"  Low ROIC (included but flagged): {low_roic_count}")

    # Use configured cutoff date for output
    output_cutoff = DATA_CUTOFF

    # Build size_horizontal view (1 row per SKU with sizes as columns)
    size_horizontal = []
    for sku_line in sku_lines:
        sku_key = sku_line['sku_key']
        # Get all sizes for this SKU from size_lines
        sku_sizes = [s for s in size_lines if s['sku_key'] == sku_key]
        if not sku_sizes:
            continue

        row = {
            'sku_key': sku_key,
            'sku_name': sku_line['sku_name'],
            'stock': sku_line['stock'],
            'inbound': sku_line['inbound'],
            'days_until_arrival': sku_line['days_until_arrival'],
            'consumption_until_arrival': sku_line['consumption_until_arrival'],
            'pre_arrival': sku_line['pre_arrival'],
            'd_sku': sku_line['d_sku'],
            't_post_days': sku_line['t_post_days'],
            'target': sku_line['target'],
            'rop_total': sku_line['rop_total'],
            'po_qty_total': sku_line['po_qty_total'],
            'po_weight_kg': sku_line['po_weight_kg'],
            'prep_days': sku_line['prep_days'],
            'po_send_date': sku_line['po_send_date'],
            'po_message_date': sku_line['po_message_date'],
            'est_arr_date': sku_line['est_arr_date'],
            'pre_arr_doc': sku_line['pre_arr_doc'],
            'post_arr_doc': sku_line['post_arr_doc'],
            'roic_pct': sku_line['roic_pct'],
            'size_orders': {}  # Size -> order qty
        }
        for size_row in sku_sizes:
            row['size_orders'][size_row['size']] = size_row['order_qty']
        size_horizontal.append(row)

    priority_skus = sum(
        1 for s in sku_lines
        if "LINE52" in (s.get("sku_key") or "") or "LINE51" in (s.get("sku_key") or "")
    )

    if conn is not None:
        conn.close()

    generated_at = fixture_generated_at or TODAY.isoformat()

    output = {
        "generated_at": generated_at,
        "po_name": "PO-4",  # Base PO identifier
        "po_message_date": TODAY.isoformat(),  # Message date for this PO
        "cutoff_date": output_cutoff,
        "sales_data_cutoff": output_cutoff,
        "stock_date": STOCK_DATE,
        "lead_time_L": params.L,
        "reorder_cycle_R": params.R,
        "prep_model": prep_model,
        "prep_days_clothes": prep_days_clothes,
        "roic_threshold_pct": ROIC_THRESHOLD * 100,
        "summary": {
            "total_skus": len(sku_lines),
            "skus_with_orders": skus_with_orders,
            "skus_without_orders": skus_without_orders,
            "total_units": total_units,
            "total_weight_kg": round(sum(s['po_weight_kg'] for s in sku_lines), 1),
            "low_roic_skus": low_roic_count,
            "priority_skus": priority_skus,
            "no_demand_estimate": skipped_no_demand,
            "no_stock_snapshot": skipped_no_stock,
            "no_order_needed": skipped_no_order
        },
        "sku_level": sku_lines,
        "size_level": size_lines,
        "size_horizontal": size_horizontal,  # NEW: 1 row per SKU with sizes as columns
        "skipped_skus": skipped_skus
    }
    if use_fixture:
        globals()["CUTOFF_DATE"], globals()["DATA_CUTOFF"], globals()["STOCK_DATE"], globals()["TODAY"] = original_context
    return output


def load_po4_approved_orders(po_id: str = "PO-4") -> Optional[dict]:
    """Load approved PO-4 orders from po_line/po_header."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT sku_key, sku_id, my_size, order_qty
              FROM po_line
             WHERE po_id = ?
               AND order_qty > 0
            """,
            (po_id,),
        ).fetchall()
        if not rows:
            return None

        header = conn.execute(
            "SELECT message_date, ship_date_seller FROM po_header WHERE po_id = ?",
            (po_id,),
        ).fetchone()

        orders_by_sku: dict[str, dict[str, int]] = {}
        for row in rows:
            sku_key = str(row["sku_key"] or "").strip()
            if not sku_key:
                continue
            sku_id = str(row["sku_id"] or "").strip()
            my_size = str(row["my_size"] or "").strip()
            if not my_size and sku_id:
                my_size = sku_id.rsplit("_", 1)[-1]
            qty = int(row["order_qty"] or 0)
            if qty <= 0:
                continue
            if sku_key not in orders_by_sku:
                orders_by_sku[sku_key] = {}
            orders_by_sku[sku_key][my_size] = orders_by_sku[sku_key].get(my_size, 0) + qty

        return {
            "po_id": po_id,
            "message_date": header["message_date"] if header else None,
            "ship_date": header["ship_date_seller"] if header else None,
            "orders_by_sku": orders_by_sku,
        }
    finally:
        conn.close()


def apply_po4_overrides(base_data: dict, po4_data: dict, params) -> dict:
    """Override PO-4 quantities with approved supplier quantities."""
    orders_by_sku = po4_data.get("orders_by_sku", {})
    if not orders_by_sku:
        return base_data

    message_date = po4_data.get("message_date") or base_data.get("po_message_date")
    ship_date = po4_data.get("ship_date")
    prep_days_override = None
    if message_date and ship_date:
        try:
            prep_days_override = (date.fromisoformat(ship_date) - date.fromisoformat(message_date)).days
        except ValueError:
            prep_days_override = None

    if message_date:
        base_data["po_message_date"] = message_date

    total_units = 0
    skus_with_orders = 0
    for sku_line in base_data.get("sku_level", []):
        sku_key = sku_line.get("sku_key")
        size_map = orders_by_sku.get(sku_key, {})
        total_qty = sum(size_map.values())
        sku_line["po_qty_total"] = total_qty
        sku_line["size_orders"] = size_map
        if message_date:
            sku_line["po_message_date"] = message_date
        if ship_date:
            sku_line["po_send_date"] = ship_date
            try:
                est_arr = date.fromisoformat(ship_date) + timedelta(days=params.L)
                sku_line["est_arr_date"] = est_arr.isoformat()
                sku_line["days_until_arrival"] = params.L + (prep_days_override or sku_line.get("prep_days", 0))
            except ValueError:
                pass
        if prep_days_override is not None:
            sku_line["prep_days"] = prep_days_override
        total_units += total_qty
        if total_qty > 0:
            skus_with_orders += 1

    size_rows = []
    existing = {(s.get("sku_key"), s.get("size")): s for s in base_data.get("size_level", [])}
    for (sku_key, size), size_line in existing.items():
        size_map = orders_by_sku.get(sku_key, {})
        prev_qty = size_line.get("order_qty") or 0
        unit_weight = 0.0
        if prev_qty:
            unit_weight = (size_line.get("weight_kg") or 0.0) / prev_qty
        size_line["order_qty"] = int(size_map.get(size, 0))
        size_line["weight_kg"] = round(unit_weight * size_line["order_qty"], 2)
        if message_date:
            size_line["po_message_date"] = message_date
        if ship_date:
            size_line["po_send_date"] = ship_date
            try:
                est_arr = date.fromisoformat(ship_date) + timedelta(days=params.L)
                size_line["est_arr_date"] = est_arr.isoformat()
                size_line["days_until_arrival"] = params.L + (prep_days_override or size_line.get("prep_days", 0))
            except ValueError:
                pass
        if prep_days_override is not None:
            size_line["prep_days"] = prep_days_override
        size_rows.append(size_line)

    for sku_key, size_map in orders_by_sku.items():
        for size, qty in size_map.items():
            if (sku_key, size) in existing:
                continue
            size_rows.append({
                "sku_key": sku_key,
                "sku_id": f"{sku_key}_{size}",
                "size": size,
                "stock": 0,
                "inbound": 0,
                "active_inbound": 0,
                "inbound_total": 0,
                "days_until_arrival": params.L,
                "consumption_until_arrival": 0.0,
                "pre_arrival": 0,
                "d_size": 0.0,
                "t_post_days": params.R,
                "target": 0.0,
                "rop_size": 0.0,
                "deficit_size": 0,
                "order_qty": int(qty),
                "weight_kg": 0.0,
                "prep_days": prep_days_override or 0,
                "po_send_date": ship_date or "",
                "po_message_date": message_date or "",
                "est_arr_date": "",
                "pre_arr_doc": 0.0,
                "post_arr_doc": 0.0,
                "roic_pct": 0.0,
                "notes": ""
            })

    base_data["size_level"] = size_rows

    weight_by_sku: dict[str, float] = {}
    for size_line in size_rows:
        sku_key = size_line.get("sku_key")
        weight_by_sku[sku_key] = weight_by_sku.get(sku_key, 0.0) + (size_line.get("weight_kg") or 0.0)

    for sku_line in base_data.get("sku_level", []):
        sku_key = sku_line.get("sku_key")
        if sku_key in weight_by_sku:
            sku_line["po_weight_kg"] = round(weight_by_sku[sku_key], 2)

    size_horizontal = []
    for sku_line in base_data.get("sku_level", []):
        sku_key = sku_line.get("sku_key")
        sku_sizes = [s for s in size_rows if s.get("sku_key") == sku_key]
        if sku_sizes:
            row = {
                "sku_key": sku_key,
                "sku_name": sku_line.get("sku_name"),
                "stock": sku_line.get("stock"),
                "inbound": sku_line.get("inbound"),
                "days_until_arrival": sku_line.get("days_until_arrival"),
                "consumption_until_arrival": sku_line.get("consumption_until_arrival"),
                "pre_arrival": sku_line.get("pre_arrival"),
                "d_sku": sku_line.get("d_sku"),
                "t_post_days": sku_line.get("t_post_days"),
                "target": sku_line.get("target"),
                "rop_total": sku_line.get("rop_total"),
                "po_qty_total": sku_line.get("po_qty_total"),
                "po_weight_kg": sku_line.get("po_weight_kg"),
                "prep_days": sku_line.get("prep_days"),
                "po_send_date": sku_line.get("po_send_date"),
                "po_message_date": sku_line.get("po_message_date"),
                "est_arr_date": sku_line.get("est_arr_date"),
                "pre_arr_doc": sku_line.get("pre_arr_doc"),
                "post_arr_doc": sku_line.get("post_arr_doc"),
                "roic_pct": sku_line.get("roic_pct"),
                "size_orders": {}
            }
            for size_row in sku_sizes:
                row["size_orders"][size_row["size"]] = size_row["order_qty"]
            size_horizontal.append(row)
    base_data["size_horizontal"] = size_horizontal

    base_data["summary"]["total_units"] = total_units
    base_data["summary"]["skus_with_orders"] = skus_with_orders
    base_data["summary"]["skus_without_orders"] = len(base_data.get("sku_level", [])) - skus_with_orders
    base_data["summary"]["total_weight_kg"] = round(
        sum(s.get("po_weight_kg", 0.0) for s in base_data.get("sku_level", [])), 1
    )

    total_cl_weight = sum(
        s.get("po_weight_kg", 0.0) for s in base_data.get("sku_level", [])
        if s.get("po_qty_total", 0) > 0 and not s.get("sku_key", "").startswith("ELS_")
    )
    base_data["prep_days_clothes"] = calc_prep_days(total_cl_weight, "CL") if total_cl_weight > 0 else 1

    return base_data


def _build_po_schedule(today: date, params, prep_days_clothes: int) -> tuple[dict[str, date], int]:
    """Build PO message dates with CNY blackout constraints."""
    blackout_start = CNY_2026.start_date
    blackout_end = CNY_2026.end_date

    po5_default = today + timedelta(days=params.R)
    po6_default = today + timedelta(days=2 * params.R)

    po5_prep_days = PO5_PREP_DAYS_OVERRIDE or prep_days_clothes
    # Ensure PO-5 ship date is BEFORE blackout_start (blackout is inclusive)
    po5_latest = blackout_start - timedelta(days=po5_prep_days + 1)
    po5_message = min(po5_default, po5_latest)
    if po5_message < today:
        po5_message = today

    po6_message = max(po6_default, blackout_end)

    schedule = {"PO-5": po5_message, "PO-6": po6_message}
    for po_num in range(7, 11):
        schedule[f"PO-{po_num}"] = po6_message + timedelta(days=(po_num - 6) * params.R)

    gap_days = (po6_message - po5_message).days
    return schedule, gap_days


def generate_multi_po_data(num_pos: int = 7) -> dict:
    """
    Generate data for multiple POs (PO-4 through PO-10).

    Each subsequent PO:
    - Message date is R days after previous
    - Factors in arrivals from all previous POs
    - Uses same base demand/stock data but projects forward
    """
    params = get_params()
    R = params.R  # Reorder cycle (typically 10 days)
    L = params.L  # Lead time

    # Generate base PO-4 data
    base_data = generate_po_data()
    po4_actual = load_po4_approved_orders()
    if po4_actual:
        base_data = apply_po4_overrides(base_data, po4_actual, params)

    # Store all POs
    all_pos = {"PO-4": base_data}

    # Build cumulative orders per SKU for projection
    # Format: sku_key -> list of (arrival_date, order_qty_by_size)
    cumulative_orders = {}
    if po4_actual and po4_actual.get("orders_by_sku"):
        ship_date = po4_actual.get("ship_date")
        po4_arr_date = None
        if ship_date:
            try:
                po4_arr_date = date.fromisoformat(ship_date) + timedelta(days=params.L)
            except ValueError:
                po4_arr_date = None
        for sku_key, size_orders in po4_actual["orders_by_sku"].items():
            total_qty = sum(size_orders.values())
            if total_qty <= 0:
                continue
            arr_date = po4_arr_date
            if not arr_date:
                base_match = next((s for s in base_data["sku_level"] if s["sku_key"] == sku_key), None)
                arr_date = date.fromisoformat(base_match["est_arr_date"]) if base_match else TODAY + timedelta(days=params.L)
            cumulative_orders[sku_key] = [(arr_date, total_qty, size_orders)]
    else:
        for sku_line in base_data['sku_level']:
            sku_key = sku_line['sku_key']
            arr_date = date.fromisoformat(sku_line['est_arr_date'])
            # Get size orders from size_level
            size_orders = {}
            for size_line in base_data['size_level']:
                if size_line['sku_key'] == sku_key:
                    size_orders[size_line['size']] = size_line['order_qty']
            cumulative_orders[sku_key] = [(arr_date, sku_line['po_qty_total'], size_orders)]

    po_schedule, po5_gap_days = _build_po_schedule(
        TODAY, params, base_data.get("prep_days_clothes", 1)
    )

    prep_days_clothes = base_data.get("prep_days_clothes", 1)
    po5_prep_days = PO5_PREP_DAYS_OVERRIDE or prep_days_clothes

    # Generate PO-5 through PO-10
    for po_num in range(5, 4 + num_pos):
        po_name = f"PO-{po_num}"
        po_message_date = po_schedule.get(po_name, TODAY + timedelta(days=(po_num - 4) * R))
        days_offset = (po_message_date - TODAY).days
        effective_R = po5_gap_days if po_num == 5 else R

        # For each PO, we need to project stock at arrival time
        # Arrival time = message_date + prep_days + L
        # Pre-arrival stock = Current + Inbound + Previous_PO_arrivals - Consumption

        # Clone and modify base data for this PO
        po_data = {
            "generated_at": base_data['generated_at'],
            "po_name": po_name,
            "po_message_date": po_message_date.isoformat(),
            "cutoff_date": base_data['cutoff_date'],
            "sales_data_cutoff": base_data['sales_data_cutoff'],
            "stock_date": base_data['stock_date'],
            "lead_time_L": L,
            "reorder_cycle_R": effective_R,
            "prep_model": base_data.get('prep_model', 'B'),
            "prep_days_clothes": po5_prep_days if po_num == 5 else base_data.get('prep_days_clothes', 1),
            "roic_threshold_pct": base_data['roic_threshold_pct'],
            "summary": {
                "total_skus": 0,
                "skus_with_orders": 0,
                "skus_without_orders": 0,
                "total_units": 0,
                "total_weight_kg": 0,
                "low_roic_skus": 0,
                "no_demand_estimate": base_data['summary']['no_demand_estimate'],
                "no_stock_snapshot": base_data['summary']['no_stock_snapshot'],
                "no_order_needed": 0
            },
            "sku_level": [],
            "size_level": [],
            "size_horizontal": [],
            "skipped_skus": base_data['skipped_skus']
        }

        # Process each SKU
        for base_sku in base_data['sku_level']:
            sku_key = base_sku['sku_key']
            d_sku = base_sku['d_sku']
            weight_kg = base_sku['po_weight_kg'] / base_sku['po_qty_total'] if base_sku['po_qty_total'] > 0 else 0.5

            # Calculate days from TODAY to this PO's message date
            days_to_message = days_offset

            # Estimate prep days (use base as approximation)
            if sku_key.startswith("ELS_"):
                prep_days = 1
            else:
                prep_days = po5_prep_days if po_num == 5 else prep_days_clothes

            # This PO's send and arrival dates
            po_send_date = po_message_date + timedelta(days=prep_days)
            po_arr_date = po_send_date + timedelta(days=L)
            effective_L = prep_days + L

            # === INBOUND CLASSIFICATION (stock-first approach) ===
            # Classify previous PO arrivals into three buckets:
            # 1. arrivals_before_msg: arrive ON or BEFORE msg_date → add to stock_at_msg
            # 2. active_inbound: arrive AFTER msg_date but BEFORE arr_date → active during lead time
            # 3. inbound_total: all arrivals from TODAY to before arr_date (cumulative view)
            arrivals_before_msg = 0
            arrivals_before_msg_by_size = {}
            active_inbound = 0
            active_inbound_by_size = {}
            inbound_total = 0
            inbound_total_by_size = {}

            if sku_key in cumulative_orders:
                for prev_arr_date, qty, size_orders in cumulative_orders[sku_key]:
                    # Arrivals before or on message date → added to stock_at_msg
                    if prev_arr_date <= po_message_date:
                        arrivals_before_msg += qty
                        for sz, sq in size_orders.items():
                            arrivals_before_msg_by_size[sz] = arrivals_before_msg_by_size.get(sz, 0) + sq
                    # Arrivals AFTER msg but BEFORE arr → active inbound
                    elif prev_arr_date < po_arr_date:
                        active_inbound += qty
                        for sz, sq in size_orders.items():
                            active_inbound_by_size[sz] = active_inbound_by_size.get(sz, 0) + sq

                    # Inbound total: all arrivals from TODAY to before arr_date
                    if prev_arr_date < po_arr_date:
                        inbound_total += qty
                        for sz, sq in size_orders.items():
                            inbound_total_by_size[sz] = inbound_total_by_size.get(sz, 0) + sq

            # === CONSUMPTION & PRE-ARRIVAL (from MESSAGE DATE) ===
            current_stock = base_sku['stock']
            inbound_stock = base_sku['inbound']

            # Consumption FROM TODAY TO message date
            consumption_to_msg = d_sku * days_offset

            # Stock AT message date = current + snapshot_inbound + arrivals_before_msg - consumption_to_msg
            stock_at_msg = max(0, current_stock + inbound_stock + arrivals_before_msg - consumption_to_msg)

            # Consumption FROM message date TO arrival (this is what the dashboard shows)
            consumption_msg_to_arr = d_sku * effective_L

            # Pre-arrival = stock_at_msg + active_inbound - consumption_msg_to_arr
            pre_arrival = max(0, stock_at_msg + active_inbound - consumption_msg_to_arr)

            # Target and ROP (same formula)
            if po_num == 5:
                base_target = base_sku['target']
                ss_total = base_target - (d_sku * R) if d_sku > 0 else 0
                target = (d_sku * effective_R) + ss_total
            else:
                target = base_sku['target']
            rop = base_sku['rop_total']

            # Order qty
            order_qty = max(0, int(round(target - pre_arrival)))
            po_weight = weight_kg * order_qty

            # Days of coverage
            if d_sku > 0:
                pre_arr_doc = pre_arrival / d_sku
                post_arr_doc = (pre_arrival + order_qty) / d_sku
            else:
                pre_arr_doc = 999.0 if pre_arrival > 0 else 0.0
                post_arr_doc = 999.0 if (pre_arrival + order_qty) > 0 else 0.0

            # Build SKU line
            size_orders_this_po = {}
            t_post_days = base_sku.get('t_post_days', R)
            if po_num == 5 and d_sku > 0:
                ss_total = base_sku['target'] - (d_sku * R)
                t_post_days = effective_R + (ss_total / d_sku)

            adj = adjust_po_dates(po_message_date, po_send_date, po_arr_date)
            po_send_date = adj["ship_date"]
            po_arr_date = adj["est_arrival"]

            sku_line = {
                'sku_key': sku_key,
                'sku_name': base_sku['sku_name'],
                'stock': current_stock,
                'inbound': inbound_stock,
                'active_inbound': active_inbound,
                'inbound_total': inbound_total,
                'days_until_arrival': effective_L,
                'consumption_until_arrival': round(consumption_msg_to_arr, 2),  # msg→arr only
                'pre_arrival': int(pre_arrival),
                'd_sku': d_sku,
                't_post_days': round(t_post_days, 1),
                'target': round(target, 1),
                'rop_total': rop,
                'deficit_total': max(0, int(rop - pre_arrival)),
                'po_qty_total': order_qty,
                'size_orders': size_orders_this_po,
                'po_weight_kg': round(po_weight, 2),
                'prep_days': prep_days,
                'po_send_date': po_send_date.isoformat(),
                'po_message_date': po_message_date.isoformat(),
                'est_arr_date': po_arr_date.isoformat(),
                'pre_arr_doc': round(pre_arr_doc, 1),
                'post_arr_doc': round(post_arr_doc, 1),
                'monthly_profit': base_sku.get('monthly_profit', 0),
                'k_avg': base_sku.get('k_avg', 0),
                'roic_pct': base_sku['roic_pct'],
                'profit_margin_pct': base_sku.get('profit_margin_pct', 0),
                'roic_below_threshold': base_sku['roic_below_threshold'],
                'd_anchor': base_sku['d_anchor'],
                'd_data': base_sku['d_data'],
                'd_model': base_sku['d_model'],
                'anchor_weight': base_sku['anchor_weight'],
                'availability_score': base_sku['availability_score'],
                'confidence': base_sku['confidence'],
                'oos_type': base_sku['oos_type'],
                'partial_oos_sizes': base_sku['partial_oos_sizes'],
                'notes': base_sku['notes']
            }
            po_data['sku_level'].append(sku_line)

            # Update summary
            po_data['summary']['total_skus'] += 1
            if order_qty > 0:
                po_data['summary']['skus_with_orders'] += 1
            else:
                po_data['summary']['skus_without_orders'] += 1
                po_data['summary']['no_order_needed'] += 1
            po_data['summary']['total_units'] += order_qty
            po_data['summary']['total_weight_kg'] += po_weight
            if base_sku['roic_below_threshold']:
                po_data['summary']['low_roic_skus'] += 1

            # Size-level processing (simplified - proportional allocation)
            if order_qty > 0:
                # Get size mix from base data
                base_sizes = [s for s in base_data['size_level'] if s['sku_key'] == sku_key]
                total_base_qty = sum(s['order_qty'] for s in base_sizes) if base_sizes else 1

                for base_size in base_sizes:
                    size = base_size['size']
                    d_size = base_size['d_size']

                    # === SIZE-LEVEL INBOUND CLASSIFICATION ===
                    size_arrivals_before_msg = arrivals_before_msg_by_size.get(size, 0)
                    size_active_inbound = active_inbound_by_size.get(size, 0)
                    size_inbound_total = inbound_total_by_size.get(size, 0)

                    # === SIZE-LEVEL CONSUMPTION & PRE-ARRIVAL (from MESSAGE DATE) ===
                    size_consumption_to_msg = d_size * days_offset
                    size_stock_at_msg = max(0, base_size['stock'] + base_size['inbound'] + size_arrivals_before_msg - size_consumption_to_msg)
                    size_consumption_msg_to_arr = d_size * effective_L
                    size_pre_arrival = max(0, size_stock_at_msg + size_active_inbound - size_consumption_msg_to_arr)

                    # Size order (proportional to base)
                    mix = base_size['order_qty'] / total_base_qty if total_base_qty > 0 else 0
                    size_order_qty = int(round(order_qty * mix))
                    size_orders_this_po[size] = size_order_qty

                    if size_order_qty > 0:
                        if po_num == 5 and d_size > 0:
                            ss_total_size = base_size['target'] - (d_size * R)
                            t_post_size = effective_R + (ss_total_size / d_size)
                            target_size = d_size * t_post_size
                        else:
                            t_post_size = base_size['t_post_days']
                            target_size = base_size['target']

                        # DOC for size
                        if d_size > 0:
                            size_pre_doc = size_pre_arrival / d_size
                            size_post_doc = (size_pre_arrival + size_order_qty) / d_size
                        else:
                            size_pre_doc = 999.0
                            size_post_doc = 999.0

                        size_line = {
                            'sku_key': sku_key,
                            'sku_id': f"{sku_key}_{size}",
                            'size': size,
                            'stock': base_size['stock'],
                            'inbound': base_size['inbound'],
                            'active_inbound': size_active_inbound,
                            'inbound_total': size_inbound_total,
                            'days_until_arrival': effective_L,
                            'consumption_until_arrival': round(size_consumption_msg_to_arr, 2),  # msg→arr only
                            'pre_arrival': int(size_pre_arrival),
                            'd_size': d_size,
                            't_post_days': round(t_post_size, 1),
                            'target': round(target_size, 1),
                            'rop_size': base_size['rop_size'],
                            'deficit_size': max(0, int(base_size['rop_size'] - size_pre_arrival)),
                            'order_qty': size_order_qty,
                            'weight_kg': round(weight_kg * size_order_qty, 2),
                            'prep_days': prep_days,
                            'po_send_date': po_send_date.isoformat(),
                            'po_message_date': po_message_date.isoformat(),
                            'est_arr_date': po_arr_date.isoformat(),
                            'pre_arr_doc': round(size_pre_doc, 1),
                            'post_arr_doc': round(size_post_doc, 1),
                            'roic_pct': base_sku['roic_pct'],
                            'notes': ''
                        }
                        po_data['size_level'].append(size_line)
                        size_orders_this_po[size] = size_order_qty

                # Add to cumulative for next PO
                if sku_key not in cumulative_orders:
                    cumulative_orders[sku_key] = []
                cumulative_orders[sku_key].append((po_arr_date, order_qty, size_orders_this_po))

        # Round summary weight
        po_data['summary']['total_weight_kg'] = round(po_data['summary']['total_weight_kg'], 1)

        # Build size_horizontal for this PO
        for sku_line in po_data['sku_level']:
            sku_key = sku_line['sku_key']
            sku_sizes = [s for s in po_data['size_level'] if s['sku_key'] == sku_key]
            if sku_sizes:
                row = {
                    'sku_key': sku_key,
                    'sku_name': sku_line['sku_name'],
                    'stock': sku_line['stock'],
                    'inbound': sku_line['inbound'],
                    'days_until_arrival': sku_line['days_until_arrival'],
                    'consumption_until_arrival': sku_line['consumption_until_arrival'],
                    'pre_arrival': sku_line['pre_arrival'],
                    'd_sku': sku_line['d_sku'],
                    't_post_days': sku_line['t_post_days'],
                    'target': sku_line['target'],
                    'rop_total': sku_line['rop_total'],
                    'po_qty_total': sku_line['po_qty_total'],
                    'po_weight_kg': sku_line['po_weight_kg'],
                    'prep_days': sku_line['prep_days'],
                    'po_send_date': sku_line['po_send_date'],
                    'po_message_date': sku_line['po_message_date'],
                    'est_arr_date': sku_line['est_arr_date'],
                    'pre_arr_doc': sku_line['pre_arr_doc'],
                    'post_arr_doc': sku_line['post_arr_doc'],
                    'roic_pct': sku_line['roic_pct'],
                    'size_orders': {}
                }
                for size_row in sku_sizes:
                    row['size_orders'][size_row['size']] = size_row['order_qty']
                po_data['size_horizontal'].append(row)

        all_pos[po_name] = po_data

    return all_pos


if __name__ == "__main__":
    print("Generating PO dashboard data with DemandEstimator...")
    print(f"Cutoff date (Asia/Almaty yesterday): {DATA_CUTOFF}")
    print(f"Stock snapshot date: {STOCK_DATE}")
    print(f"ROIC threshold (display only): {ROIC_THRESHOLD * 100}%")
    print()

    # Generate all POs (PO-4 through PO-10)
    all_pos = generate_multi_po_data(num_pos=7)

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    base_summary = all_pos.get("PO-4", {}).get("summary", {})
    if "priority_skus" not in base_summary:
        base_summary["priority_skus"] = 0

    day_complete_env = os.environ.get("AB_DAY_COMPLETE", "1").strip().lower()
    day_complete_ok = day_complete_env not in {"0", "false", "no"}

    archived_pos = ["PO-4"] if "PO-4" in all_pos else []
    active_pos = [po for po in all_pos.keys() if po not in archived_pos]
    active_pos.sort(key=lambda p: int(p.split("-")[1]) if "-" in p else 0)

    # Save combined data
    combined_data = {
        "generated_at": TODAY.isoformat(),
        "base_stock_date": STOCK_DATE,
        "cutoff_date": DATA_CUTOFF,
        "day_complete_ok": day_complete_ok,
        "summary": base_summary,
        "pos": all_pos,
        "active_pos": active_pos,
        "archived_pos": archived_pos,
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(combined_data, f, indent=2)

    print(f"\nGenerated: {OUTPUT_PATH}")
    print(f"  - POs generated: {len(all_pos)}")
    for po_name, po_data in all_pos.items():
        print(f"  - {po_name}: {po_data['summary']['skus_with_orders']} SKUs need {po_data['summary']['total_units']} units")
