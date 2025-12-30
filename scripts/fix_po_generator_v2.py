"""
FIX for generate_po_dashboard_data.py - calc_po_draft_manual function

THREE BUGS FIXED:
1. Pre-arrival doesn't subtract consumption during lead time
2. Lead time (L) doesn't include prep days 
3. Prep days calculated AFTER qty (chicken-egg), should estimate upfront

LINE52_BLACK Example (proving the bug):
- 3XL: Stock=173, D=8.52/day
- Current code: Pre = 173 → "we have stock"  
- Fixed code: Pre = max(0, 173 - 8.52×27) = 0 → "order 200+ units"

Where 27 = L(21) + prep_days(6) for ~445 unit order at 0.95kg each
"""

from dataclasses import dataclass
from math import ceil


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
    effective_L: int  # NEW: actual lead time including prep
    size_allocations: dict


def calc_prep_days_estimate(
    current_stock: int, 
    d_sku: float, 
    target: float,
    weight_per_unit: float,
    product_type: str = 'CL'
) -> int:
    """
    Estimate prep days BEFORE knowing exact PO qty.
    
    Logic: 
    1. Rough order = target - current (ignoring inbound complexity)
    2. Weight = rough_order × weight_per_unit
    3. Prep = ceil(1.3 × weight_kg / 100)
    
    This gives us effective_L for consumption calc.
    """
    if product_type.upper() in ('ELS', 'ELEC', 'ELECTRONICS'):
        return 1
    
    # Rough order estimate (simple version)
    rough_order = max(0, target - current_stock)
    if rough_order == 0:
        return 1
    
    weight_kg = rough_order * weight_per_unit
    return max(1, ceil(1.3 * weight_kg / 100))


def calc_po_draft_manual_fixed(
    sku_key: str,
    size_sales_90d: dict[str, int],
    size_current: dict[str, int],
    size_inbound: dict[str, int],
    sigma_sku: float,
    unit_cogs: float,
    unit_profit: float,
    weight_per_unit: float,  # NEW: needed for prep calculation
    product_type: str,       # NEW: CL vs ELS
    params
) -> ManualPODraft:
    """
    Fixed PO calculation with proper pre-arrival depletion.
    
    Key changes from original:
    1. Estimate prep_days upfront from rough order
    2. effective_L = L + prep_days
    3. Pre_size = max(0, stock + inbound - D_size × effective_L)
    4. Order_size = max(0, Target_size - Pre_size)
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

    # === FIX #1: Estimate prep days FIRST ===
    prep_days = calc_prep_days_estimate(
        current_stock=current_stock_total,
        d_sku=d_sku,
        target=target,
        weight_per_unit=weight_per_unit,
        product_type=product_type
    )
    
    # === FIX #2: Use effective lead time including prep ===
    effective_L = L + prep_days

    # Size mix allocation
    all_sizes = set(size_sales_90d.keys()) | set(size_current.keys())
    size_allocations = {}
    total_qty = 0

    for size in all_sizes:
        sales_90d_size = size_sales_90d.get(size, 0)
        stock = size_current.get(size, 0)
        inbound = size_inbound.get(size, 0)

        # Size demand
        d_size = sales_90d_size / 90.0

        # Size mix (with guardrails)
        if total_sales > 0:
            raw_mix = sales_90d_size / total_sales
            mix = max(0.03, min(0.40, raw_mix)) if raw_mix > 0 else 0.03
        else:
            mix = 1.0 / max(len(all_sizes), 1)

        # Size-level ROP and Target (proportional to mix)
        rop_size = mix * rop_sku
        target_size = mix * target

        # === FIX #3: Subtract consumption during effective lead time ===
        consumption_until_arrival = d_size * effective_L
        pre_arrival_size = max(0, stock + inbound - consumption_until_arrival)
        
        # Order the gap
        order_qty_size = max(0, int(target_size - pre_arrival_size))

        size_allocations[size] = {
            'stock': stock,
            'inbound': inbound,
            'd_size': round(d_size, 3),
            'mix': round(mix, 4),
            'rop': round(rop_size, 1),
            'target': round(target_size, 1),
            'consumption': round(consumption_until_arrival, 1),  # DEBUG
            'pre_arrival': round(pre_arrival_size, 1),           # DEBUG
            'order_qty': order_qty_size
        }
        total_qty += order_qty_size

    # === FIX #4: Pre-arrival at SKU level also needs depletion ===
    consumption_sku = d_sku * effective_L
    pre_arrival = max(0, current_stock_total + inbound_stock_total - consumption_sku)
    
    # Should order?
    should_order = pre_arrival < rop_sku or total_qty > 0

    # ROIC (unchanged)
    if d_sku <= 0 or unit_cogs <= 0:
        roic = 0.0
    else:
        cycle_stock_value = d_sku * (L + R / 2) * unit_cogs
        safety_stock_value = ss_total * unit_cogs
        k_avg = cycle_stock_value + safety_stock_value
        monthly_profit = unit_profit * d_sku * 30
        roic = monthly_profit / k_avg if k_avg > 0 else 0.0

    return ManualPODraft(
        sku_key=sku_key,
        d_sku=d_sku,
        ss_total=ss_total,
        rop_sku=rop_sku,
        target=target,
        current_stock_total=current_stock_total,
        inbound_stock_total=inbound_stock_total,
        pre_arrival=int(pre_arrival),
        total_qty=total_qty,
        should_order=should_order,
        roic_monthly=roic,
        effective_L=effective_L,
        size_allocations=size_allocations
    )


# ============================================================================
# TEST: LINE52_BLACK validation
# ============================================================================

if __name__ == "__main__":
    """Validate against LINE52_BLACK from actual data."""
    
    # From Current_stock_15_12_2025
    size_current = {
        'S': 154, 'M': 158, 'L': 513, 'XL': 671, 
        '2XL': 344, '3XL': 173, '4XL': 118
    }
    
    # From D_size_mix_reference.xlsx (D_active=45, converted to 90d)
    # D_size × 90 days = 90-day sales equivalent
    size_sales_90d = {
        'S': int(0.73 * 90),     # 66
        'M': int(3.06 * 90),     # 275
        'L': int(7.62 * 90),     # 686
        'XL': int(13.29 * 90),   # 1196
        '2XL': int(9.29 * 90),   # 836
        '3XL': int(8.52 * 90),   # 767
        '4XL': int(2.49 * 90),   # 224
    }
    
    size_inbound = {s: 0 for s in size_current}  # No inbound
    
    # Params mock
    class Params:
        L = 21
        R = 10
        z = 1.65
        TV = 0.23
    
    params = Params()
    sigma_sku = 45 * 0.4  # 18
    
    # COGS estimation
    base_cost_cny = 47
    weight_kg = 0.95
    cny_to_kzt = 78
    shipping_per_kg = 150
    unit_cogs = base_cost_cny * cny_to_kzt + weight_kg * shipping_per_kg  # 3808.5
    avg_price = 16500  # Approximate
    unit_profit = avg_price - unit_cogs  # 12691.5
    
    result = calc_po_draft_manual_fixed(
        sku_key='CL_OC_MEN_LINE52_BLACK',
        size_sales_90d=size_sales_90d,
        size_current=size_current,
        size_inbound=size_inbound,
        sigma_sku=sigma_sku,
        unit_cogs=unit_cogs,
        unit_profit=unit_profit,
        weight_per_unit=weight_kg,
        product_type='CL',
        params=params
    )
    
    print("=" * 70)
    print("LINE52_BLACK FIXED CALCULATION")
    print("=" * 70)
    print(f"D_sku: {result.d_sku:.2f}/day")
    print(f"SS_total: {result.ss_total:.1f}")
    print(f"ROP_sku: {result.rop_sku:.1f}")
    print(f"Target: {result.target:.1f}")
    print(f"Current stock: {result.current_stock_total}")
    print(f"Effective L (L + prep): {result.effective_L} days")
    print(f"Pre-arrival (with depletion): {result.pre_arrival}")
    print(f"TOTAL PO QTY: {result.total_qty}")
    print(f"Should order: {result.should_order}")
    print(f"ROIC monthly: {result.roic_monthly * 100:.1f}%")
    print()
    print("SIZE-LEVEL BREAKDOWN:")
    print("-" * 70)
    print(f"{'Size':<6} {'Stock':>6} {'D':>6} {'Consump':>8} {'Pre':>6} {'Target':>7} {'Order':>6}")
    print("-" * 70)
    
    for size in ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']:
        if size in result.size_allocations:
            a = result.size_allocations[size]
            print(f"{size:<6} {a['stock']:>6} {a['d_size']:>6.2f} {a['consumption']:>8.1f} "
                  f"{a['pre_arrival']:>6.1f} {a['target']:>7.1f} {a['order_qty']:>6}")
    
    print("-" * 70)
    print(f"{'TOTAL':<6} {result.current_stock_total:>6} {result.d_sku:>6.2f} "
          f"{result.d_sku * result.effective_L:>8.1f} "
          f"{result.pre_arrival:>6} {result.target:>7.1f} {result.total_qty:>6}")
    print()
    
    # Compare with Adil's Excel target
    print("VALIDATION vs Adil's Excel PO-4:")
    print(f"  Expected LINE52 order: ~445 units")
    print(f"  Calculated order:       {result.total_qty} units")
    print(f"  Delta:                  {result.total_qty - 445:+d} units")
