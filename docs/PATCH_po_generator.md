# PATCH for generate_po_dashboard_data.py
# Three changes needed:

# ============================================================================
# CHANGE 1: Add weight_per_unit and product_type to calc_po_draft_manual call
# ============================================================================
# In line ~488-498, change the calc_po_draft_manual call to include new params:

# OLD:
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

# NEW:
draft = calc_po_draft_manual(
    sku_key=sku_key,
    size_sales_90d=size_sales_90d,
    size_current=size_current,
    size_inbound=size_inbound,
    sigma_sku=sigma_sku,
    unit_cogs=unit_cogs,
    unit_profit=unit_profit,
    weight_per_unit=weight_kg,      # ADD THIS
    product_type=product_type,       # ADD THIS
    params=params
)

# ============================================================================
# CHANGE 2: calc_po_draft_manual signature (lines 275-284)
# ============================================================================
# Add weight_per_unit and product_type parameters:

# OLD:
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

# NEW:
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
    params
) -> ManualPODraft:

# ============================================================================
# CHANGE 3: Inside calc_po_draft_manual, REPLACE lines 315-347 with this:
# ============================================================================

    # Stock totals
    current_stock_total = sum(size_current.values())
    inbound_stock_total = sum(size_inbound.values())

    # === STEP 1: Estimate prep days BEFORE calculating order qty ===
    # This avoids chicken-egg problem: prep depends on qty, qty depends on prep
    rough_order = max(0, target - current_stock_total)
    if product_type.upper() in ('ELS', 'ELEC', 'ELECTRONICS'):
        prep_days = 1
    else:
        weight_estimate = rough_order * weight_per_unit
        prep_days = max(1, ceil(1.3 * weight_estimate / 100))
    
    # === STEP 2: Use effective lead time (L + prep) for consumption ===
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

        # === STEP 3: Pre-arrival accounts for consumption during effective L ===
        consumption_until_arrival = d_size * effective_L
        pre_arrival_size = max(0, stock + inbound - consumption_until_arrival)
        
        # Order the gap
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

    # === STEP 4: SKU-level pre-arrival also uses depletion ===
    consumption_sku = d_sku * effective_L
    pre_arrival = max(0, int(current_stock_total + inbound_stock_total - consumption_sku))

# ============================================================================
# CHANGE 4: Update ManualPODraft dataclass (line 257-272)
# ============================================================================
# Add effective_L field:

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
    effective_L: int  # ADD THIS
    size_allocations: dict

# ============================================================================
# CHANGE 5: Update the return statement to include effective_L
# ============================================================================
# Around line 366-378:

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
        effective_L=effective_L,  # ADD THIS
        size_allocations=size_allocations
    )
