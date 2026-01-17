"""
TASK-151: Size-Aware PO Allocation Engine

Phase 9.6: True size-level allocation per spec.
- OOS-filtered demand calculation
- Size mix with 3%/40% guardrails
- Per-size safety stock, ROP, T_post
- Lead time consumption projection
- ANY-size REORDER trigger
- 3-tier ROIC gate

Data structures defined here:
- OrderStatus: REORDER, WAIT, OK
- ROICAction: ORDER_FULL, ORDER_WITH_FLAG, REVIEW_REQUIRED
- SizeData: Per-size metrics
- SizeAllocation: Per-size order quantities
- PODraft: Complete PO draft with all sizes
"""

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Optional


class OrderStatus(Enum):
    """
    Order status for a size or SKU.

    Status determination logic (check Total FIRST):
    1. Total_stock < ROP → REORDER
    2. Current_stock < ROP (but Total ≥ ROP) → WAIT
    3. Else → OK
    """
    REORDER = "REORDER"  # Total stock below ROP, need to order
    WAIT = "WAIT"        # Current below ROP but inbound covers
    OK = "OK"            # Sufficient stock


class ROICAction(Enum):
    """
    ROIC gate decision for PO approval.

    3-tier gate:
    - ≥20%: ORDER_FULL (auto-approve)
    - 10-20%: ORDER_WITH_FLAG (approve but flag for review)
    - <10%: REVIEW_REQUIRED (manual approval needed)
    """
    ORDER_FULL = "ORDER_FULL"            # ROIC ≥ 20%, full auto-approval
    ORDER_WITH_FLAG = "ORDER_WITH_FLAG"  # ROIC 10-20%, approve with flag
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # ROIC < 10%, needs manual review


class DemandConfidence(Enum):
    """
    Confidence level for demand calculation based on data availability.

    From TASK-152 OOS-filtered demand:
    - ≥30 good days → ACTUAL
    - 14-29 good days → MARGINAL (1.2× uplift)
    - <14 good days → FALLBACK (1.5× uplift)
    - 0 good days → NO_DATA
    """
    ACTUAL = "ACTUAL"      # ≥30 good days, high confidence
    MARGINAL = "MARGINAL"  # 14-29 good days, moderate confidence
    FALLBACK = "FALLBACK"  # <14 good days, low confidence
    NO_DATA = "NO_DATA"    # 0 good days, no data available


@dataclass
class SizeData:
    """
    Per-size inventory and demand data.

    Contains all metrics needed for size-level allocation:
    - Current stock and inbound
    - Historical sales and demand
    - Safety stock components
    - Status determination
    """
    my_size: str                          # Size label (S, M, L, XL, etc.)
    size_order: int = 0                   # Sort order for display

    # Stock levels
    current_stock: int = 0                # On-hand inventory
    inbound_stock: int = 0                # In-transit inventory
    total_stock: int = 0                  # current + inbound

    # Demand metrics
    sales_90d: int = 0                    # Units sold in last 90 days
    good_days: int = 0                    # Days with valid data (not OOS)
    d_size: float = 0.0                   # Daily demand for this size
    demand_confidence: DemandConfidence = DemandConfidence.NO_DATA

    # Size mix
    raw_mix: float = 0.0                  # Raw percentage from sales
    mix: float = 0.0                      # Adjusted mix (with guardrails)

    # Safety stock (per size)
    sigma_size: float = 0.0              # Size-level volatility
    ss_demand: float = 0.0               # SS for demand uncertainty
    ss_floor: float = 0.0                # SS floor buffer
    ss_mix: float = 0.0                  # SS for mix variability
    ss_total: float = 0.0                # Total safety stock

    # Reorder metrics
    rop: float = 0.0                     # Reorder point
    t_post: float = 0.0                  # Target days of cover after arrival

    # Stock projection
    pre_arrival_stock: float = 0.0       # Projected stock at arrival
    days_to_arrival: int = 21            # Lead time assumption

    # Status
    status: OrderStatus = OrderStatus.OK


@dataclass
class SizeAllocation:
    """
    Order quantity allocation for a single size.
    """
    my_size: str                          # Size label
    size_order: int = 0                   # Sort order

    # Order calculation
    target_stock: float = 0.0             # Target = T_post × D_size
    order_qty: int = 0                    # Calculated order quantity
    order_qty_adjusted: int = 0           # After new SKU / insurance adjustments

    # Status
    status: OrderStatus = OrderStatus.OK
    is_trigger: bool = False              # True if this size triggered the PO


@dataclass
class PODraft:
    """
    Complete PO draft with all size-level allocations.
    """
    sku_key: str                          # Style-level SKU key
    store_code: str = "UNIVERSAL"         # Store code

    # SKU-level metrics
    d_sku: float = 0.0                    # Total SKU daily demand
    sigma_sku: float = 0.0                # SKU-level volatility
    ss_total_sku: float = 0.0             # SKU-level safety stock
    rop_sku: float = 0.0                  # SKU-level ROP
    demand_confidence: DemandConfidence = DemandConfidence.NO_DATA

    # Stock totals
    current_stock_total: int = 0
    inbound_stock_total: int = 0
    total_stock: int = 0

    # Order decision
    should_order: bool = False            # True if ANY size in REORDER
    trigger_sizes: list[str] = field(default_factory=list)  # Sizes that triggered

    # ROIC gate
    roic_monthly: float = 0.0             # Monthly ROIC percentage
    roic_action: ROICAction = ROICAction.REVIEW_REQUIRED
    cogs_unit: float = 0.0                # Cost per unit
    profit_unit: float = 0.0              # Profit per unit

    # Size allocations
    allocations: dict[str, SizeAllocation] = field(default_factory=dict)

    # Order totals (after all adjustments)
    total_qty: int = 0                    # Sum of all size quantities
    total_cost_cny: float = 0.0           # Total cost in CNY

    # Adjustment flags
    new_sku_factor: float = 1.0           # Age-based adjustment factor
    sku_age_days: int = 90                # Days since first sale
    insurance_applied: bool = False       # True if low-demand insurance added

    # Timestamps
    created_at: Optional[str] = None      # ISO timestamp


# =============================================================================
# TASK-152: OOS-filtered demand calculation
# =============================================================================

def calc_d_sku_with_oos_filter(
    sales_history: list[int],
    stock_history: list[int]
) -> tuple[float, int, DemandConfidence]:
    """
    Calculate daily demand with OOS (out-of-stock) filtering.

    TASK-152: True demand calculation that excludes stockout days.

    A "good day" is one where we had valid data:
    - If sales > 0: good day (we sold something)
    - If sales = 0 AND stock > 0: good day (we had stock but didn't sell)
    - If sales = 0 AND stock = 0: OOS day (skip - no data)

    Args:
        sales_history: List of daily sales units (most recent first or chronological)
        stock_history: List of daily stock levels (parallel to sales_history)

    Returns:
        Tuple of (d_daily, good_days, confidence):
        - d_daily: Average daily demand (with uplift if low confidence)
        - good_days: Number of valid data days
        - confidence: DemandConfidence enum value

    Confidence levels and uplifts:
        - ≥30 good days → ACTUAL (no uplift)
        - 14-29 good days → MARGINAL (1.2× uplift)
        - <14 good days → FALLBACK (1.5× uplift)
        - 0 good days → NO_DATA (returns 0)

    Example:
        >>> sales = [5, 3, 0, 2, 0, 4]  # 6 days of sales
        >>> stock = [10, 7, 4, 4, 0, 8]  # day 5 was OOS (sales=0, stock=0)
        >>> d, days, conf = calc_d_sku_with_oos_filter(sales, stock)
        >>> # days = 5 (excluding OOS day)
        >>> # d = (5+3+0+2+4) / 5 = 2.8
    """
    if not sales_history or not stock_history:
        return 0.0, 0, DemandConfidence.NO_DATA

    # Ensure same length
    min_len = min(len(sales_history), len(stock_history))

    # Count good days and sum sales
    good_days = 0
    total_sales = 0

    for i in range(min_len):
        sales = sales_history[i]
        stock = stock_history[i]

        # Check if this is a good day (not OOS)
        if sales > 0 or stock > 0:
            # Good day: either we sold something, or we had stock
            good_days += 1
            total_sales += sales

    # Handle no data case
    if good_days == 0:
        return 0.0, 0, DemandConfidence.NO_DATA

    # Calculate base demand
    d_base = total_sales / good_days

    # Determine confidence and apply uplift
    if good_days >= 30:
        confidence = DemandConfidence.ACTUAL
        d_daily = d_base  # No uplift
    elif good_days >= 14:
        confidence = DemandConfidence.MARGINAL
        d_daily = d_base * 1.2  # 20% uplift for uncertainty
    else:
        confidence = DemandConfidence.FALLBACK
        d_daily = d_base * 1.5  # 50% uplift for high uncertainty

    return d_daily, good_days, confidence


# =============================================================================
# TASK-153: Size mix with guardrails
# =============================================================================

def calc_size_mix_with_guardrails(
    size_sales: dict[str, int],
    min_mix: float = 0.03,
    max_mix: float = 0.40
) -> dict[str, float]:
    """
    Calculate size mix percentages with floor (3%) and cap (40%) guardrails.

    TASK-153: Prevents extreme allocations by:
    1. Computing raw mix from historical sales
    2. Applying minimum floor (3%) to each size
    3. Applying maximum cap (40%) to each size
    4. Renormalizing to sum to 1.0

    Args:
        size_sales: Dict mapping size -> units sold (e.g., {"S": 10, "M": 30, "L": 60})
        min_mix: Minimum percentage per size (default: 0.03 = 3%)
        max_mix: Maximum percentage per size (default: 0.40 = 40%)

    Returns:
        Dict mapping size -> mix percentage (e.g., {"S": 0.10, "M": 0.30, "L": 0.40, ...})
        All values sum to 1.0

    Edge cases:
        - Empty dict or all zeros: uniform distribution
        - Single size: capped at max_mix, rest distributed equally

    Example:
        >>> sales = {"S": 5, "M": 20, "L": 50, "XL": 20, "2XL": 5}
        >>> mix = calc_size_mix_with_guardrails(sales)
        >>> # L was 50%, capped to 40%, others adjusted
    """
    from core.config.inventory_params import get_params

    # Get params if not overridden
    if min_mix == 0.03 and max_mix == 0.40:
        params = get_params()
        min_mix = params.min_size_mix
        max_mix = params.max_size_mix

    # Handle empty or all-zero case
    if not size_sales:
        return {}

    total_sales = sum(size_sales.values())
    n_sizes = len(size_sales)

    if total_sales == 0 or n_sizes == 0:
        # Uniform distribution
        if n_sizes == 0:
            return {}
        uniform_mix = 1.0 / n_sizes
        return {size: uniform_mix for size in size_sales}

    # Step 1: Calculate raw mix
    raw_mix = {size: units / total_sales for size, units in size_sales.items()}

    # Step 2 & 3: Apply floor and cap
    adjusted_mix = {}
    for size, mix in raw_mix.items():
        if mix < min_mix:
            adjusted_mix[size] = min_mix
        elif mix > max_mix:
            adjusted_mix[size] = max_mix
        else:
            adjusted_mix[size] = mix

    # Step 4: Renormalize to sum to 1.0
    total_adjusted = sum(adjusted_mix.values())

    if total_adjusted == 0:
        # Shouldn't happen, but safety check
        uniform_mix = 1.0 / n_sizes
        return {size: uniform_mix for size in size_sales}

    # Renormalize
    final_mix = {size: mix / total_adjusted for size, mix in adjusted_mix.items()}

    return final_mix


# =============================================================================
# TASK-154: Per-size safety stock calculation
# =============================================================================

def calc_safety_stock_for_size(
    d_size: float,
    sigma_sku: float,
    size_mix: float,
    L: int = None,
    B: int = None,
    z: float = None,
    TV: float = None
) -> tuple[float, float, float, float, float]:
    """
    Calculate safety stock components for a single size.

    TASK-154: Per-size safety stock using Master_Inventory_Rules_v5.3.md formulas.

    Formulas:
        σ_size = σ_sku × size_mix
        SS_demand = z × σ_size × √L
        SS_floor = D_size × B
        SS_mix = TV × D_size × L
        SS_total = SS_demand + SS_floor + SS_mix

    Args:
        d_size: Daily demand for this size
        sigma_sku: SKU-level volatility (σ_sku)
        size_mix: This size's percentage of total (0.0 to 1.0)
        L: Lead time in days (default: from params)
        B: Buffer factor in days (default: from params)
        z: Service level z-score (default: from params)
        TV: Mix variability factor (default: from params)

    Returns:
        Tuple of (sigma_size, ss_demand, ss_floor, ss_mix, ss_total)

    Example:
        >>> sigma_size, ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock_for_size(
        ...     d_size=1.0, sigma_sku=2.0, size_mix=0.20
        ... )
    """
    import math
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L
    B = B if B is not None else params.B
    z = z if z is not None else params.z
    TV = TV if TV is not None else params.TV

    # Calculate size-level sigma
    sigma_size = sigma_sku * size_mix

    # Safety stock components
    ss_demand = z * sigma_size * math.sqrt(L)
    ss_floor = d_size * B
    ss_mix = TV * d_size * L
    ss_total = ss_demand + ss_floor + ss_mix

    return sigma_size, ss_demand, ss_floor, ss_mix, ss_total


# =============================================================================
# TASK-155: Per-size ROP and T_post calculation
# =============================================================================

def calc_rop_for_size(
    d_size: float,
    ss_total: float,
    L: int = None
) -> float:
    """
    Calculate reorder point for a single size.

    TASK-155: ROP = D_size × L + SS_total

    Args:
        d_size: Daily demand for this size
        ss_total: Total safety stock for this size
        L: Lead time in days (default: from params)

    Returns:
        Reorder point (units)

    Example:
        >>> rop = calc_rop_for_size(d_size=1.0, ss_total=25.0)
        >>> # ROP = 1.0 × 21 + 25.0 = 46.0
    """
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L

    return d_size * L + ss_total


def calc_t_post_for_size(
    d_size: float,
    ss_total: float,
    R: int = None
) -> float:
    """
    Calculate target days of cover after arrival (T_post) for a single size.

    TASK-155: T_post = R + (SS_total / D_size)

    This represents how many days of stock we target to have after
    a shipment arrives.

    Args:
        d_size: Daily demand for this size
        ss_total: Total safety stock for this size
        R: Review period in days (default: from params)

    Returns:
        Target days of cover (T_post)

    Edge case:
        If d_size = 0, returns R (minimum coverage)

    Example:
        >>> t_post = calc_t_post_for_size(d_size=1.0, ss_total=25.0)
        >>> # T_post = 10 + (25.0 / 1.0) = 35.0 days
    """
    from core.config.inventory_params import get_params

    params = get_params()
    R = R if R is not None else params.R

    # Edge case: zero demand
    if d_size <= 0:
        return float(R)  # Minimum is review period

    return R + (ss_total / d_size)


# =============================================================================
# TASK-156: Lead time consumption projection
# =============================================================================

def calc_pre_arrival_stock(
    current_stock: int,
    inbound_stock: int,
    d_size: float,
    days_to_arrival: int = None
) -> float:
    """
    Calculate projected stock at time of next shipment arrival.

    TASK-156: Pre = Current + Inbound - (D_size × days_to_arrival)

    This represents how much stock we expect to have when the new
    shipment arrives, accounting for consumption during lead time.

    Args:
        current_stock: Current on-hand inventory
        inbound_stock: Units already in transit
        d_size: Daily demand for this size
        days_to_arrival: Days until next shipment (default: L from params)

    Returns:
        Projected stock at arrival (minimum 0)

    Example:
        >>> pre = calc_pre_arrival_stock(
        ...     current_stock=50, inbound_stock=0, d_size=2.0, days_to_arrival=21
        ... )
        >>> # Pre = 50 + 0 - (2.0 × 21) = 50 - 42 = 8.0
    """
    from core.config.inventory_params import get_params

    params = get_params()
    days = days_to_arrival if days_to_arrival is not None else params.L

    # Projected stock = current + inbound - consumption
    pre = current_stock + inbound_stock - (d_size * days)

    # Can't go negative
    return max(0.0, pre)


# =============================================================================
# TASK-157: Per-size status calculation
# =============================================================================

def calc_status_for_size(
    current_stock: int,
    total_stock: int,
    rop: float
) -> OrderStatus:
    """
    Determine order status for a single size.

    TASK-157: Status logic from Master_Inventory_Rules_v5.3.md.

    IMPORTANT: Check Total FIRST, then Current.

    Logic:
    1. Total_stock < ROP → REORDER (nothing covers the gap)
    2. Current_stock < ROP (but Total ≥ ROP) → WAIT (inbound covers it)
    3. Else → OK

    Args:
        current_stock: On-hand inventory
        total_stock: Current + inbound
        rop: Reorder point

    Returns:
        OrderStatus enum: REORDER, WAIT, or OK

    Example:
        >>> status = calc_status_for_size(current=30, total=50, rop=40)
        >>> # Total 50 >= ROP 40, but Current 30 < ROP 40 → WAIT
    """
    # Check Total FIRST
    if total_stock < rop:
        return OrderStatus.REORDER

    # Total is sufficient, check Current
    if current_stock < rop:
        return OrderStatus.WAIT

    # Both Total and Current are sufficient
    return OrderStatus.OK


# =============================================================================
# TASK-158: PO trigger logic
# =============================================================================

def should_generate_po(
    size_statuses: dict[str, OrderStatus]
) -> tuple[bool, list[str]]:
    """
    Determine if a PO should be generated based on size statuses.

    TASK-158: ANY size in REORDER status → trigger PO for whole SKU.

    This is the "any-size trigger" rule: if even one size needs
    reorder, we generate a PO for the entire SKU.

    Args:
        size_statuses: Dict mapping size -> OrderStatus

    Returns:
        Tuple of (should_order, trigger_sizes):
        - should_order: True if any size is in REORDER
        - trigger_sizes: List of size labels that triggered the PO

    Example:
        >>> statuses = {"S": OrderStatus.OK, "M": OrderStatus.REORDER, "L": OrderStatus.WAIT}
        >>> should_order, triggers = should_generate_po(statuses)
        >>> # should_order = True, triggers = ["M"]
    """
    trigger_sizes = []

    for size, status in size_statuses.items():
        if status == OrderStatus.REORDER:
            trigger_sizes.append(size)

    should_order = len(trigger_sizes) > 0

    return should_order, trigger_sizes


# =============================================================================
# TASK-159: Size allocation calculation
# =============================================================================

def calc_order_qty_for_size(
    d_size: float,
    t_post: float,
    pre_arrival_stock: float
) -> int:
    """
    Calculate order quantity for a single size.

    TASK-159: target = T_post × D_size, order = max(0, round(target - pre_arrival))

    Args:
        d_size: Daily demand for this size
        t_post: Target days of cover after arrival
        pre_arrival_stock: Projected stock when shipment arrives

    Returns:
        Order quantity (non-negative integer)

    Example:
        >>> qty = calc_order_qty_for_size(d_size=2.0, t_post=35.0, pre_arrival_stock=20.0)
        >>> # target = 35 × 2 = 70, order = max(0, round(70 - 20)) = 50
    """
    # Target stock level
    target = t_post * d_size

    # Order quantity
    order = target - pre_arrival_stock

    # Ensure non-negative integer
    return max(0, round(order))


def calc_deficit_capped_order_qty(
    d_size: float,
    t_post: float,
    pre_arrival_stock: float,
    *,
    eps: float = 1e-9,
) -> int:
    """
    Calculate order quantity with deficit-capped logic.

    Rule: if pre_arrival >= target, order MUST be 0 (no cross-size netting).
    Uses ceil(deficit - eps) to avoid rounding a zero deficit up to 1.
    """
    if d_size <= 0:
        return 0

    target = d_size * t_post
    deficit = target - pre_arrival_stock
    if deficit <= 0:
        return 0

    return max(0, int(ceil(deficit - eps)))


# =============================================================================
# TASK-160: New SKU adjustments
# =============================================================================

def adjust_for_new_sku(
    order_qty: int,
    sku_age_days: int
) -> tuple[int, float]:
    """
    Apply age-based adjustment factor for new SKUs.

    TASK-160: Reduce order quantities for SKUs with limited sales history
    to manage risk of overstocking unproven products.

    Factors:
    - <30 days: 0.75× (25% reduction)
    - 30-60 days: 0.85× (15% reduction)
    - 60-90 days: 0.95× (5% reduction)
    - ≥90 days: 1.0× (no adjustment)

    Args:
        order_qty: Original order quantity
        sku_age_days: Days since first sale of this SKU

    Returns:
        Tuple of (adjusted_qty, factor_applied):
        - adjusted_qty: Quantity after age adjustment (minimum 1 if order_qty > 0)
        - factor_applied: The factor that was applied

    Example:
        >>> adj_qty, factor = adjust_for_new_sku(order_qty=100, sku_age_days=25)
        >>> # adj_qty = round(100 × 0.75) = 75, factor = 0.75
    """
    from core.config.inventory_params import get_params

    params = get_params()

    # Determine adjustment factor based on age
    if sku_age_days < 30:
        factor = params.new_sku_30d_factor  # 0.75
    elif sku_age_days < 60:
        factor = params.new_sku_60d_factor  # 0.85
    elif sku_age_days < 90:
        factor = params.new_sku_90d_factor  # 0.95
    else:
        factor = 1.0  # Full order

    # Apply factor
    adjusted_qty = round(order_qty * factor)

    # Ensure minimum of 1 if we were going to order something
    if order_qty > 0 and adjusted_qty < 1:
        adjusted_qty = 1

    return adjusted_qty, factor


# =============================================================================
# TASK-161: Low demand insurance
# =============================================================================

def apply_low_demand_insurance(
    size_allocations: dict[str, int],
    size_demands: dict[str, float],
    size_mixes: dict[str, float],
    total_po_qty: int,
    demand_threshold: float = 0.1,
    mix_threshold: float = 0.05
) -> dict[str, int]:
    """
    Apply low-demand insurance to protect sizes with sporadic demand.

    TASK-161: If D_size < 0.1 AND mix ≥ 5% → add 1% of total PO to that size.

    This ensures we don't completely starve sizes that have historical
    importance (≥5% mix) but currently show very low demand (< 0.1/day).

    Args:
        size_allocations: Current allocation {size: qty}
        size_demands: Daily demand {size: d_size}
        size_mixes: Size mix percentages {size: mix}
        total_po_qty: Total PO quantity before insurance
        demand_threshold: Low demand threshold (default: 0.1)
        mix_threshold: Significant mix threshold (default: 0.05 = 5%)

    Returns:
        Updated allocations with insurance applied

    Example:
        >>> allocs = {"S": 0, "M": 50, "L": 100}
        >>> demands = {"S": 0.05, "M": 2.0, "L": 4.0}
        >>> mixes = {"S": 0.10, "M": 0.30, "L": 0.60}
        >>> new_allocs = apply_low_demand_insurance(allocs, demands, mixes, 150)
        >>> # S has low demand (0.05 < 0.1) but significant mix (10% >= 5%)
        >>> # S gets 1% of 150 = 2 units added
    """
    # Work with a copy
    updated = dict(size_allocations)

    for size in size_allocations:
        d_size = size_demands.get(size, 0.0)
        mix = size_mixes.get(size, 0.0)

        # Check insurance conditions
        if d_size < demand_threshold and mix >= mix_threshold:
            # Add 1% of total PO
            insurance_qty = max(1, round(total_po_qty * 0.01))
            updated[size] = size_allocations[size] + insurance_qty

    return updated


# =============================================================================
# TASK-162: ROIC calculation
# =============================================================================

def calc_roic(
    d_sku: float,
    ss_total: float,
    unit_cogs: float,
    unit_profit: float,
    L: int = None,
    R: int = None
) -> float:
    """
    Calculate monthly ROIC (Return on Invested Capital) for a SKU.

    TASK-162: ROIC formula from Master_Inventory_Rules_v5.3.md.

    Formulas:
        K_avg = D × (L + R/2) × COGS + SS_total × COGS
        Monthly_ROIC = (Unit_profit × D × 30) / K_avg

    This measures the monthly return on the capital tied up in inventory,
    including both cycle stock and safety stock.

    Args:
        d_sku: Daily demand for the SKU
        ss_total: Total safety stock for the SKU
        unit_cogs: Cost of goods sold per unit
        unit_profit: Profit per unit (price - COGS)
        L: Lead time in days (default: from params)
        R: Review period in days (default: from params)

    Returns:
        Monthly ROIC as a decimal (e.g., 0.20 = 20%)

    Edge case:
        If K_avg = 0 (no capital invested), returns 0.0

    Example:
        >>> roic = calc_roic(d_sku=2.0, ss_total=50.0, unit_cogs=100.0, unit_profit=30.0)
        >>> # K_avg = 2.0 × (21 + 10/2) × 100 + 50 × 100 = 2.0 × 26 × 100 + 5000 = 10200
        >>> # Monthly_ROIC = (30 × 2.0 × 30) / 10200 = 1800 / 10200 ≈ 0.176 (17.6%)
    """
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L
    R = R if R is not None else params.R

    # Calculate average capital tied up
    # K_avg = D × (L + R/2) × COGS + SS_total × COGS
    # This represents: cycle stock during lead time + safety stock, all at COGS
    cycle_stock_value = d_sku * (L + R / 2) * unit_cogs
    safety_stock_value = ss_total * unit_cogs
    k_avg = cycle_stock_value + safety_stock_value

    # Edge case: no capital invested
    if k_avg <= 0:
        return 0.0

    # Monthly profit = Unit_profit × D × 30 days
    monthly_profit = unit_profit * d_sku * 30

    # Monthly ROIC
    monthly_roic = monthly_profit / k_avg

    return monthly_roic


# =============================================================================
# TASK-163: 3-tier ROIC gate
# =============================================================================

def apply_roic_gate(
    roic: float,
    order_qty: int
) -> tuple[ROICAction, int]:
    """
    Apply 3-tier ROIC gate to determine PO approval status.

    TASK-163: ROIC gate from Phase 9.6 spec.

    Tiers:
    - ≥20%: ORDER_FULL - Full auto-approval
    - 10-20%: ORDER_WITH_FLAG - Approve but flag for review
    - <10%: REVIEW_REQUIRED - Block order, needs manual approval

    Args:
        roic: Monthly ROIC as a decimal (e.g., 0.20 = 20%)
        order_qty: Original order quantity

    Returns:
        Tuple of (action, final_qty):
        - action: ROICAction enum value
        - final_qty: Order quantity (0 if REVIEW_REQUIRED)

    Example:
        >>> action, qty = apply_roic_gate(roic=0.25, order_qty=100)
        >>> # action = ORDER_FULL, qty = 100

        >>> action, qty = apply_roic_gate(roic=0.15, order_qty=100)
        >>> # action = ORDER_WITH_FLAG, qty = 100

        >>> action, qty = apply_roic_gate(roic=0.05, order_qty=100)
        >>> # action = REVIEW_REQUIRED, qty = 0
    """
    from core.config.inventory_params import get_params

    params = get_params()

    # 3-tier gate
    if roic >= params.roic_full_approval:  # 20%
        return ROICAction.ORDER_FULL, order_qty

    elif roic >= params.roic_flag_threshold:  # 10%
        return ROICAction.ORDER_WITH_FLAG, order_qty

    else:  # < 10%
        return ROICAction.REVIEW_REQUIRED, 0


# =============================================================================
# TASK-164: Main PO Draft Generator
# =============================================================================

def generate_po_draft(
    sku_key: str,
    store_code: str,
    size_sales_90d: dict[str, int],
    size_current_stock: dict[str, int],
    size_inbound_stock: dict[str, int],
    size_sales_history: dict[str, list[int]],
    size_stock_history: dict[str, list[int]],
    unit_cogs: float,
    unit_profit: float,
    sigma_sku: float,
    sku_age_days: int = 90
) -> PODraft:
    """
    Generate a complete PO draft with size-aware allocation.

    TASK-164: Main orchestrator that combines all Phase 9.6 components.

    Steps:
    1. Get params
    2. Calculate size mix with guardrails
    3. Calculate per-size metrics (D, SS, ROP, T_post)
    4. Calculate per-size status
    5. Check if PO needed (trigger logic)
    6. Calculate allocations
    7. Apply low demand insurance
    8. Apply new SKU adjustment
    9. Build totals
    10. Calculate ROIC
    11. Apply ROIC gate
    12. Return PODraft

    Args:
        sku_key: Style-level SKU key (e.g., "LINE52_BLACK")
        store_code: Store code (e.g., "UNIVERSAL")
        size_sales_90d: 90-day sales by size {size: total_units}
        size_current_stock: Current on-hand stock {size: units}
        size_inbound_stock: In-transit stock {size: units}
        size_sales_history: Daily sales history by size {size: [daily_sales]}
        size_stock_history: Daily stock history by size {size: [daily_stock]}
        unit_cogs: Cost of goods sold per unit
        unit_profit: Profit per unit (price - COGS)
        sigma_sku: SKU-level demand volatility
        sku_age_days: Days since first sale (default: 90)

    Returns:
        PODraft with complete size-level allocations and ROIC gate result

    Example:
        >>> draft = generate_po_draft(
        ...     sku_key="LINE52_BLACK",
        ...     store_code="UNIVERSAL",
        ...     size_sales_90d={"S": 100, "M": 300, "L": 400, "XL": 150, "2XL": 50},
        ...     size_current_stock={"S": 20, "M": 30, "L": 25, "XL": 10, "2XL": 15},
        ...     size_inbound_stock={"S": 0, "M": 0, "L": 0, "XL": 0, "2XL": 0},
        ...     size_sales_history={"S": [...], ...},
        ...     size_stock_history={"S": [...], ...},
        ...     unit_cogs=100.0,
        ...     unit_profit=30.0,
        ...     sigma_sku=2.0,
        ...     sku_age_days=120
        ... )
    """
    from datetime import datetime
    from core.config.inventory_params import get_params

    params = get_params()
    sizes = list(size_sales_90d.keys())

    # Initialize PODraft
    draft = PODraft(
        sku_key=sku_key,
        store_code=store_code,
        cogs_unit=unit_cogs,
        profit_unit=unit_profit,
        sigma_sku=sigma_sku,
        sku_age_days=sku_age_days,
        created_at=datetime.now().isoformat()
    )

    # ==========================================================================
    # Step 2: Calculate size mix with guardrails
    # ==========================================================================
    size_mix = calc_size_mix_with_guardrails(size_sales_90d)

    # ==========================================================================
    # Step 3: Calculate per-size metrics (D, SS, ROP, T_post)
    # ==========================================================================
    size_data: dict[str, SizeData] = {}
    size_demands: dict[str, float] = {}
    size_ss_totals: dict[str, float] = {}

    for size in sizes:
        # Get histories for this size
        sales_hist = size_sales_history.get(size, [])
        stock_hist = size_stock_history.get(size, [])

        # OOS-filtered demand
        d_size, good_days, confidence = calc_d_sku_with_oos_filter(sales_hist, stock_hist)
        size_demands[size] = d_size

        # Safety stock components
        mix = size_mix.get(size, 0.0)
        sigma_size, ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock_for_size(
            d_size=d_size,
            sigma_sku=sigma_sku,
            size_mix=mix
        )
        size_ss_totals[size] = ss_total

        # ROP and T_post
        rop = calc_rop_for_size(d_size=d_size, ss_total=ss_total)
        t_post = calc_t_post_for_size(d_size=d_size, ss_total=ss_total)

        # Current stock levels
        current = size_current_stock.get(size, 0)
        inbound = size_inbound_stock.get(size, 0)
        total = current + inbound

        # Pre-arrival stock projection
        pre_arrival = calc_pre_arrival_stock(
            current_stock=current,
            inbound_stock=inbound,
            d_size=d_size
        )

        # Build SizeData
        size_data[size] = SizeData(
            my_size=size,
            size_order=sizes.index(size),
            current_stock=current,
            inbound_stock=inbound,
            total_stock=total,
            sales_90d=size_sales_90d.get(size, 0),
            good_days=good_days,
            d_size=d_size,
            demand_confidence=confidence,
            raw_mix=size_sales_90d.get(size, 0) / max(1, sum(size_sales_90d.values())),
            mix=mix,
            sigma_size=sigma_size,
            ss_demand=ss_demand,
            ss_floor=ss_floor,
            ss_mix=ss_mix,
            ss_total=ss_total,
            rop=rop,
            t_post=t_post,
            pre_arrival_stock=pre_arrival,
            days_to_arrival=params.L
        )

    # ==========================================================================
    # Step 4: Calculate per-size status
    # ==========================================================================
    size_statuses: dict[str, OrderStatus] = {}
    for size, data in size_data.items():
        status = calc_status_for_size(
            current_stock=data.current_stock,
            total_stock=data.total_stock,
            rop=data.rop
        )
        size_data[size].status = status
        size_statuses[size] = status

    # ==========================================================================
    # Step 5: Check if PO needed (trigger logic)
    # ==========================================================================
    should_order, trigger_sizes = should_generate_po(size_statuses)
    draft.should_order = should_order
    draft.trigger_sizes = trigger_sizes

    # ==========================================================================
    # Step 6: Calculate allocations
    # ==========================================================================
    size_allocations: dict[str, int] = {}

    is_cl = sku_key.startswith("CL")
    if should_order:
        for size, data in size_data.items():
            if is_cl:
                qty = calc_deficit_capped_order_qty(
                    d_size=data.d_size,
                    t_post=data.t_post,
                    pre_arrival_stock=data.pre_arrival_stock,
                )
            else:
                qty = calc_order_qty_for_size(
                    d_size=data.d_size,
                    t_post=data.t_post,
                    pre_arrival_stock=data.pre_arrival_stock
                )
            size_allocations[size] = qty
    else:
        # No order needed, all allocations are 0
        for size in sizes:
            size_allocations[size] = 0

    # ==========================================================================
    # Step 7: Apply low demand insurance
    # ==========================================================================
    if should_order and not is_cl:
        total_before_insurance = sum(size_allocations.values())
        size_allocations = apply_low_demand_insurance(
            size_allocations=size_allocations,
            size_demands=size_demands,
            size_mixes=size_mix,
            total_po_qty=total_before_insurance
        )
        if sum(size_allocations.values()) > total_before_insurance:
            draft.insurance_applied = True

    # ==========================================================================
    # Step 8: Apply new SKU adjustment
    # ==========================================================================
    size_allocations_adjusted: dict[str, int] = {}
    for size, qty in size_allocations.items():
        adj_qty, factor = adjust_for_new_sku(order_qty=qty, sku_age_days=sku_age_days)
        size_allocations_adjusted[size] = adj_qty
        if factor < 1.0:
            draft.new_sku_factor = factor

    # ==========================================================================
    # Step 9: Build totals and SizeAllocation objects
    # ==========================================================================
    for size in sizes:
        original_qty = size_allocations.get(size, 0)
        adjusted_qty = size_allocations_adjusted.get(size, 0)
        status = size_statuses.get(size, OrderStatus.OK)

        allocation = SizeAllocation(
            my_size=size,
            size_order=sizes.index(size),
            target_stock=size_data[size].t_post * size_data[size].d_size,
            order_qty=original_qty,
            order_qty_adjusted=adjusted_qty,
            status=status,
            is_trigger=(size in trigger_sizes)
        )
        draft.allocations[size] = allocation

    # Totals
    draft.total_qty = sum(a.order_qty_adjusted for a in draft.allocations.values())
    draft.total_cost_cny = draft.total_qty * unit_cogs

    # Stock totals
    draft.current_stock_total = sum(size_current_stock.values())
    draft.inbound_stock_total = sum(size_inbound_stock.values())
    draft.total_stock = draft.current_stock_total + draft.inbound_stock_total

    # SKU-level metrics
    draft.d_sku = sum(size_demands.values())
    draft.ss_total_sku = sum(size_ss_totals.values())
    draft.rop_sku = sum(d.rop for d in size_data.values())
    # Use the most common confidence level
    confidences = [d.demand_confidence for d in size_data.values()]
    draft.demand_confidence = max(set(confidences), key=confidences.count)

    # ==========================================================================
    # Step 10: Calculate ROIC
    # ==========================================================================
    draft.roic_monthly = calc_roic(
        d_sku=draft.d_sku,
        ss_total=draft.ss_total_sku,
        unit_cogs=unit_cogs,
        unit_profit=unit_profit
    )

    # ==========================================================================
    # Step 11: Apply ROIC gate
    # ==========================================================================
    if should_order and draft.total_qty > 0:
        roic_action, gated_qty = apply_roic_gate(
            roic=draft.roic_monthly,
            order_qty=draft.total_qty
        )
        draft.roic_action = roic_action

        # If REVIEW_REQUIRED, set quantities to 0
        if roic_action == ROICAction.REVIEW_REQUIRED:
            for alloc in draft.allocations.values():
                alloc.order_qty_adjusted = 0
            draft.total_qty = 0
            draft.total_cost_cny = 0
    else:
        draft.roic_action = ROICAction.REVIEW_REQUIRED if not should_order else ROICAction.ORDER_FULL

    # ==========================================================================
    # Step 12: Return PODraft
    # ==========================================================================
    return draft
