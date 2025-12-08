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
