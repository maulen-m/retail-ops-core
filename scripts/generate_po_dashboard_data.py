#!/usr/bin/env python3
"""
Generate PO dashboard data for webapp.
Outputs JSON with SKU-level and size-level PO recommendations.

Uses DemandEstimator for OOS-aware demand calculation with anchor data blending.
ROIC shown for info (not filtered). All active SKUs included.
Data cutoff: Yesterday in Asia/Almaty timezone.
"""

import sqlite3
import json
import statistics
from datetime import date, timedelta
from pathlib import Path
from math import ceil
from dataclasses import dataclass, asdict
from typing import Optional
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
from core.calc.demand_estimator import DemandEstimator, ConfidenceLevel, OOSType

# Constants
DB_PATH = PROJECT_ROOT / "db" / "app.db"
ANCHOR_FILE = PROJECT_ROOT / "excel" / "D_size_mix_reference.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DIAGNOSTICS_PATH = PROJECT_ROOT / "exports" / "demand_diagnostics.csv"
ROIC_THRESHOLD = 0.15  # 15% - for display only, not filtering
HOLIDAY_DEADLINE = date(2025, 12, 31)

# Valid size codes (filter out messy data like 'CB', '0', 'DRIVE', 'NAN')
VALID_SIZES = {'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', 'XS',
               '26', '28', '30', '32', '34', '36', '38', '40', '42',
               'ONE_SIZE', 'ONESIZE', 'OS'}


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

# Stock snapshot date (latest from database)
STOCK_DATE = get_stock_snapshot_date()
TODAY = date.fromisoformat(STOCK_DATE)  # Use stock date as "today" for calculations


@dataclass
class SizePOLine:
    """Size-level PO recommendation."""
    sku_key: str
    sku_id: str
    size: str
    stock: int
    inbound: int
    rop_size: float
    deficit_size: int
    order_qty: int
    weight_kg: float
    prep_days: int
    needed_by_date: str
    po_send_date: str
    po_message_date: str
    priority_flag: bool
    roic_pct: float
    notes: str


@dataclass
class SkuPOLine:
    """SKU-level PO summary."""
    sku_key: str
    sku_name: str
    stock: int
    inbound: int
    rop_total: float
    deficit_total: int
    po_qty_total: int
    po_weight_kg: float
    prep_days: int
    needed_by_date: str
    po_send_date: str
    po_message_date: str
    priority_flag: bool
    roic_pct: float
    roic_below_threshold: bool  # True if ROIC < 15% (display warning)
    d_sku: float  # Blended demand
    d_anchor: float  # Anchor demand
    d_data: float  # Data-driven demand
    anchor_weight: float  # Blend weight (0-1)
    confidence: str  # HIGH, MEDIUM, LOW, ANCHOR_ONLY
    oos_type: str  # NONE, EXTENDED, INTERMITTENT, PARTIAL
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


@dataclass
class ManualPODraft:
    """Manual PO calculation result."""
    sku_key: str
    d_sku: float
    ss_total: float
    rop_sku: float
    target: float
    current_stock_total: int
    inbound_stock_total: int
    pre_arrival: int
    total_qty: int
    should_order: bool
    roic_monthly: float
    # Size allocations: size -> (stock, inbound, d_size, rop, target, order_qty)
    size_allocations: dict


def calc_po_draft_manual(
    sku_key: str,
    size_sales_90d: dict[str, int],
    size_current: dict[str, int],
    size_inbound: dict[str, int],
    sigma_sku: float,
    unit_cogs: float,
    unit_profit: float,
    params
) -> ManualPODraft:
    """
    Calculate PO draft manually without OOS filtering.

    Formulas:
    - D = sales_90d / 90
    - SS = z×σ×√L + D×B + TV×D×L
    - ROP = D×L + SS
    - Target = R×D + SS (since T_post = R + SS/D)
    - Order_qty = max(0, Target - Pre_arrival)
    """
    L = params.L
    R = params.R
    z = params.z
    TV = params.TV
    B = 14  # Buffer days

    # SKU-level demand
    total_sales = sum(size_sales_90d.values())
    d_sku = total_sales / 90.0

    # Safety stock
    ss_demand = z * sigma_sku * (L ** 0.5)
    ss_floor = d_sku * B
    ss_mix = TV * d_sku * L
    ss_total = ss_demand + ss_floor + ss_mix

    # ROP and Target
    rop_sku = d_sku * L + ss_total
    target = R * d_sku + ss_total

    # Stock totals
    current_stock_total = sum(size_current.values())
    inbound_stock_total = sum(size_inbound.values())
    # Pre-arrival = Stock + Inbound - Consumption during lead time
    consumption_sku = d_sku * L
    pre_arrival = max(0, current_stock_total + inbound_stock_total - consumption_sku)

    # Size mix allocation
    all_sizes = set(size_sales_90d.keys()) | set(size_current.keys())
    size_allocations = {}
    total_qty = 0  # Will be sum of size allocations

    for size in all_sizes:
        sales_90d_size = size_sales_90d.get(size, 0)
        stock = size_current.get(size, 0)
        inbound = size_inbound.get(size, 0)

        # Size demand
        d_size = sales_90d_size / 90.0

        # Size mix (with guardrails)
        if total_sales > 0:
            raw_mix = sales_90d_size / total_sales
            # Apply 3%/40% guardrails
            mix = max(0.03, min(0.40, raw_mix)) if raw_mix > 0 else 0.03
        else:
            mix = 1.0 / max(len(all_sizes), 1)

        # Size-level ROP and Target (proportional to mix)
        rop_size = mix * rop_sku
        target_size = mix * target

        # Size order quantity (account for consumption during lead time)
        consumption_size = d_size * L
        pre_arrival_size = max(0, stock + inbound - consumption_size)
        order_qty_size = max(0, int(target_size - pre_arrival_size))

        size_allocations[size] = {
            'stock': stock,
            'inbound': inbound,
            'd_size': d_size,
            'mix': mix,
            'rop': rop_size,
            'target': target_size,
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
        current_stock_total=current_stock_total,
        inbound_stock_total=inbound_stock_total,
        pre_arrival=pre_arrival,
        total_qty=total_qty,
        should_order=should_order,
        roic_monthly=roic,
        size_allocations=size_allocations
    )


def generate_po_data() -> dict:
    """Main function to generate PO dashboard data using DemandEstimator."""

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    params = get_params()

    # Initialize DemandEstimator
    print("Initializing DemandEstimator...")
    estimator = DemandEstimator(DB_PATH, ANCHOR_FILE)
    print(f"  Cutoff date: {estimator.cutoff_date}")
    print(f"  Anchor SKUs loaded: {len(estimator.anchor_data)}")

    # Get demand estimates for all SKUs
    print("Estimating demand for all SKUs...")
    demand_results, skipped_skus = estimator.estimate_all(store_code="UNIVERSAL")
    print(f"  Estimated: {len(demand_results)} SKUs")
    print(f"  Skipped: {len(skipped_skus)} SKUs")

    # Export diagnostics
    if demand_results:
        estimator.export_diagnostics(demand_results, DIAGNOSTICS_PATH)
        print(f"  Diagnostics exported to: {DIAGNOSTICS_PATH}")

    # Build demand lookup: sku_key -> SKUDemandResult
    demand_lookup = {r.sku_key: r for r in demand_results}

    # Get all active SKUs
    skus = get_all_active_skus(conn)
    print(f"Found {len(skus)} active SKUs in dim_sku")

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

        # Check if we have demand estimate for this SKU
        demand_result = demand_lookup.get(sku_key)
        if not demand_result:
            skipped_no_demand += 1
            continue

        # Get current stock from latest snapshot date
        size_current_raw = conn.execute("""
            SELECT my_size, current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
              AND snapshot_date = ?
        """, (sku_key, STOCK_DATE)).fetchall()

        size_current = filter_valid_sizes({row['my_size']: row['current_stock'] for row in size_current_raw})
        size_inbound = filter_valid_sizes({row['my_size']: row['inbound_stock'] for row in size_current_raw})

        # If no snapshot for this SKU, skip (no valid stock data)
        if not size_current:
            skipped_no_stock += 1
            continue

        # Get SKU cost/profit for ROIC
        base_cost_cny = sku['base_cost_cny'] or 50
        weight_kg = sku['weight_kg'] or 0.5
        product_type = sku['product_type'] or 'CL'

        # COGS calculation
        cny_to_kzt = 78
        shipping_per_kg = 150
        unit_cogs = base_cost_cny * cny_to_kzt + weight_kg * shipping_per_kg

        # Get average sell price
        price_row = conn.execute("""
            SELECT AVG(sell_price_kzt) as avg_price
            FROM fact_sales
            WHERE sku_key = ?
            AND order_date >= date(?, '-90 days')
            AND order_date <= ?
        """, (sku_key, DATA_CUTOFF, DATA_CUTOFF)).fetchone()

        avg_price = price_row['avg_price'] if price_row and price_row['avg_price'] else 15000
        unit_profit = avg_price - unit_cogs

        # Use demand from DemandEstimator (blended d_final)
        d_sku = demand_result.d_final
        sigma_sku = demand_result.sigma_final

        # Build size_sales_90d from demand_result for size allocation
        size_sales_90d = {}
        for size, size_result in demand_result.size_results.items():
            # Approximate 90d sales from demand rate
            size_sales_90d[size] = int(size_result.d_size * 90)

        size_sales_90d = filter_valid_sizes(size_sales_90d)

        # Generate PO draft using manual calculation with DemandEstimator demand
        try:
            draft = calc_po_draft_manual(
                sku_key=sku_key,
                size_sales_90d=size_sales_90d,
                size_current=size_current,
                size_inbound=size_inbound,
                sigma_sku=sigma_sku,
                unit_cogs=unit_cogs,
                unit_profit=unit_profit,
                params=params
            )
            # Override d_sku with blended demand from estimator
            draft.d_sku = d_sku
        except Exception as e:
            print(f"  Error generating draft for {sku_key}: {e}")
            continue

        # Track ROIC status (but don't filter!)
        roic_below_threshold = draft.roic_monthly < ROIC_THRESHOLD
        if roic_below_threshold:
            low_roic_count += 1
            notes_list.append(f"ROIC {draft.roic_monthly*100:.1f}% < 15%")

        # Skip if no order needed
        if not draft.should_order or draft.total_qty == 0:
            skipped_no_order += 1
            continue

        # Calculate dates
        total_stock = draft.current_stock_total
        d_sku = draft.d_sku
        needed_by = calc_needed_by_date(total_stock, d_sku)

        po_weight = weight_kg * draft.total_qty
        prep_days = calc_prep_days(po_weight, product_type)
        po_send, po_message = calc_po_dates(needed_by, prep_days, params.L)
        priority = po_send <= HOLIDAY_DEADLINE

        # Calculate deficit (ROP - stock - inbound)
        deficit_total = max(0, int(draft.rop_sku - draft.current_stock_total - draft.inbound_stock_total))

        # SKU-level line with DemandEstimator data
        sku_line = SkuPOLine(
            sku_key=sku_key,
            sku_name=sku_name[:50] if sku_name else sku_key,
            stock=draft.current_stock_total,
            inbound=draft.inbound_stock_total,
            rop_total=round(draft.rop_sku, 1),
            deficit_total=deficit_total,
            po_qty_total=draft.total_qty,
            po_weight_kg=round(po_weight, 2),
            prep_days=prep_days,
            needed_by_date=needed_by.isoformat(),
            po_send_date=po_send.isoformat(),
            po_message_date=po_message.isoformat(),
            priority_flag=priority,
            roic_pct=round(draft.roic_monthly * 100, 1),
            roic_below_threshold=roic_below_threshold,
            d_sku=round(demand_result.d_final, 3),
            d_anchor=round(demand_result.d_anchor, 3),
            d_data=round(demand_result.d_data, 3),
            anchor_weight=round(demand_result.anchor_weight, 2),
            confidence=demand_result.confidence.name,
            oos_type=demand_result.oos_type.name,
            notes="; ".join(notes_list) if notes_list else ""
        )
        sku_lines.append(asdict(sku_line))

        # Size-level lines
        for size, alloc in draft.size_allocations.items():
            order_qty = alloc['order_qty']
            if order_qty <= 0:
                continue

            # Skip invalid sizes
            if size.upper() not in VALID_SIZES and size not in VALID_SIZES:
                continue

            size_stock = alloc['stock']
            size_inb = alloc['inbound']

            # Get ROP for this size
            rop_size = alloc['rop']

            deficit = max(0, int(rop_size - size_stock - size_inb))
            size_weight = weight_kg * order_qty

            size_line = SizePOLine(
                sku_key=sku_key,
                sku_id=f"{sku_key}_{size}",
                size=size,
                stock=size_stock,
                inbound=size_inb,
                rop_size=round(rop_size, 1),
                deficit_size=deficit,
                order_qty=order_qty,
                weight_kg=round(size_weight, 2),
                prep_days=prep_days,
                needed_by_date=needed_by.isoformat(),
                po_send_date=po_send.isoformat(),
                po_message_date=po_message.isoformat(),
                priority_flag=priority,
                roic_pct=round(draft.roic_monthly * 100, 1),
                notes=""
            )
            size_lines.append(asdict(size_line))

    conn.close()

    # Sort by PO message date (most urgent first)
    sku_lines.sort(key=lambda x: x['po_message_date'])
    size_lines.sort(key=lambda x: (x['po_message_date'], x['sku_key'], x['size']))

    print(f"\nResults:")
    print(f"  SKUs needing PO: {len(sku_lines)}")
    print(f"  Skipped (no demand estimate): {skipped_no_demand}")
    print(f"  Skipped (no stock snapshot): {skipped_no_stock}")
    print(f"  Skipped (no order needed): {skipped_no_order}")
    print(f"  Low ROIC (included but flagged): {low_roic_count}")

    # Use estimator's cutoff date for output
    output_cutoff = estimator.cutoff_date.isoformat()

    return {
        "generated_at": TODAY.isoformat(),
        "cutoff_date": output_cutoff,  # Proper cutoff from DemandEstimator
        "sales_data_cutoff": output_cutoff,  # Legacy field for compatibility
        "stock_date": STOCK_DATE,
        "roic_threshold_pct": ROIC_THRESHOLD * 100,
        "holiday_deadline": HOLIDAY_DEADLINE.isoformat(),
        "summary": {
            "total_skus": len(sku_lines),
            "total_units": sum(s['po_qty_total'] for s in sku_lines),
            "priority_skus": sum(1 for s in sku_lines if s['priority_flag']),
            "total_weight_kg": round(sum(s['po_weight_kg'] for s in sku_lines), 1),
            "low_roic_skus": low_roic_count,
            "skipped_count": len(skipped_skus)
        },
        "sku_level": sku_lines,
        "size_level": size_lines,
        "skipped_skus": skipped_skus  # From DemandEstimator
    }


if __name__ == "__main__":
    print("Generating PO dashboard data with DemandEstimator...")
    print(f"Cutoff date (Asia/Almaty yesterday): {DATA_CUTOFF}")
    print(f"Stock snapshot date: {STOCK_DATE}")
    print(f"ROIC threshold (display only): {ROIC_THRESHOLD * 100}%")
    print()

    data = generate_po_data()

    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nGenerated: {OUTPUT_PATH}")
    print(f"  - SKUs: {data['summary']['total_skus']}")
    print(f"  - Units: {data['summary']['total_units']}")
    print(f"  - Priority: {data['summary']['priority_skus']}")
    print(f"  - Weight: {data['summary']['total_weight_kg']} kg")
    print(f"  - Low ROIC (flagged): {data['summary']['low_roic_skus']}")
    print(f"  - Skipped SKUs: {data['summary']['skipped_count']}")
