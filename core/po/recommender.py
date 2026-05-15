"""
PO Recommender Engine — ONE Source of Truth

This module provides the canonical PO (Purchase Order) calculation functions.
All scripts should use these functions instead of implementing their own formulas.

CANONICAL FORMULAS (per Master_Inventory_Rules_v9.md):

    Safety Stock Components:
        SS_demand = z × σ × sqrt(L)     # Demand uncertainty buffer
        SS_floor = D × B                # Floor buffer (B days of demand)
        SS_mix = TV × D × L             # Mix variability buffer
        SS_total = SS_demand + SS_floor + SS_mix

    Reorder Point:
        ROP = D × L + SS_total

    Target Coverage:
        T_post = R + (SS_total / D)     # Post-arrival coverage days (NO L!)
        Target = D × T_post = D × R + SS_total

    Pre-Arrival Stock Projection:
        effective_L = L + prep_days
        Pre = Current + Inbound - D × effective_L

    Order Quantity:
        Order_qty = max(0, round(Target - Pre))

    Status Determination:
        Total < ROP → REORDER
        Current < ROP (but Total ≥ ROP) → WAIT
        Else → OK

    PO Trigger:
        ANY size in REORDER → generate PO for whole SKU

IMPORTANT: Do NOT add L to T_post. Lead time L is accounted in pre-arrival
consumption, not in post-arrival coverage.

Usage:
    from core.po.recommender import (
        calc_order_qty,
        calc_safety_stock,
        calc_t_post,
        calc_pre_arrival,
        calc_rop,
        OrderStatus,
        should_reorder,
    )

    # SKU-level calculation
    result = calc_order_qty(
        d=10.0,
        current_stock=50,
        inbound_stock=100,
        ss_total=25.0,
    )
    print(f"Order {result.order_qty} units")

    # Size-level calculation (use functions from size_allocation directly)
    from core.calc.size_allocation import (
        calc_order_qty_for_size,
        calc_t_post_for_size,
    )
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import math

# Re-export Phase 9.6 functions as canonical implementations
from core.calc.size_allocation import (
    # Data structures
    OrderStatus,
    ROICAction,
    DemandConfidence,
    SizeData,
    SizeAllocation,
    PODraft,
    # Safety stock
    calc_safety_stock_for_size,
    # ROP and T_post
    calc_rop_for_size,
    calc_t_post_for_size,
    # Pre-arrival projection
    calc_pre_arrival_stock,
    # Status determination
    calc_status_for_size,
    # PO trigger
    should_generate_po,
    # Order quantity
    calc_order_qty_for_size,
    # Adjustments
    adjust_for_new_sku,
    apply_low_demand_insurance,
    # Size mix
    calc_size_mix_with_guardrails,
    # ROIC
    calc_roic,
    apply_roic_gate,
)


@dataclass
class OrderQtyResult:
    """
    Result of order quantity calculation for a SKU.

    Provides both the recommended order quantity and the intermediate
    values used in the calculation for debugging and audit.
    """
    # Core result
    order_qty: int                      # Recommended order quantity

    # Inputs
    d: float                            # Daily demand
    current_stock: int                  # On-hand inventory
    inbound_stock: int                  # In-transit inventory

    # Intermediate values
    ss_total: float                     # Total safety stock
    rop: float                          # Reorder point
    t_post: float                       # Post-arrival coverage days
    target: float                       # Target stock level
    pre_arrival: float                  # Projected stock at arrival

    # Status
    status: OrderStatus                 # REORDER, WAIT, or OK

    # Calculation parameters
    L: int = 21                         # Lead time days
    R: int = 10                         # Review period days
    effective_L: Optional[int] = None   # L + prep_days if applicable

    @property
    def deficit(self) -> float:
        """Shortfall below target (positive = need to order)."""
        return max(0, self.target - self.pre_arrival)

    @property
    def days_of_cover(self) -> float:
        """Current days of cover (Total / D)."""
        if self.d <= 0:
            return float('inf')
        return (self.current_stock + self.inbound_stock) / self.d


def calc_order_qty(
    d: float,
    current_stock: int,
    inbound_stock: int,
    ss_total: float,
    L: int = None,
    R: int = None,
    prep_days: int = 0,
) -> OrderQtyResult:
    """
    Calculate order quantity for a SKU.

    This is the canonical order quantity calculation per Master_Inventory_Rules_v9.md.
    Use this for SKU-level calculations. For size-level, use calc_order_qty_for_size().

    Args:
        d: Daily demand
        current_stock: On-hand inventory
        inbound_stock: In-transit inventory
        ss_total: Total safety stock (SS_demand + SS_floor + SS_mix)
        L: Lead time in days (default: from inventory_params)
        R: Review period in days (default: from inventory_params)
        prep_days: Supplier preparation days (added to L for consumption window)

    Returns:
        OrderQtyResult with order_qty and intermediate values

    Formulas:
        ROP = D × L + SS_total
        T_post = R + (SS_total / D)  # NO L in T_post!
        Target = D × T_post = D × R + SS_total
        effective_L = L + prep_days
        Pre = Current + Inbound - D × effective_L
        Order = max(0, round(Target - Pre))

    Example:
        >>> result = calc_order_qty(
        ...     d=10.0, current_stock=50, inbound_stock=100, ss_total=25.0
        ... )
        >>> print(f"Order: {result.order_qty}, Status: {result.status}")
    """
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L
    R = R if R is not None else params.R

    # Effective lead time includes prep days
    effective_L = L + prep_days

    # ROP = D × L + SS
    rop = d * L + ss_total

    # T_post = R + (SS / D)  -- NO L in T_post!
    if d > 0:
        t_post = R + (ss_total / d)
    else:
        t_post = float(R)  # Minimum coverage

    # Target = D × T_post = D × R + SS
    target = d * t_post

    # Pre-arrival = Current + Inbound - D × effective_L
    pre_arrival = current_stock + inbound_stock - (d * effective_L)
    pre_arrival = max(0.0, pre_arrival)  # Can't go negative

    # Order = max(0, round(Target - Pre))
    order_qty = max(0, round(target - pre_arrival))

    # Status determination
    total_stock = current_stock + inbound_stock
    status = calc_status_for_size(current_stock, total_stock, rop)

    return OrderQtyResult(
        order_qty=order_qty,
        d=d,
        current_stock=current_stock,
        inbound_stock=inbound_stock,
        ss_total=ss_total,
        rop=rop,
        t_post=t_post,
        target=target,
        pre_arrival=pre_arrival,
        status=status,
        L=L,
        R=R,
        effective_L=effective_L,
    )


def calc_safety_stock(
    d: float,
    sigma: float = None,
    L: int = None,
    B: int = None,
    TV: float = None,
    z: float = None,
) -> tuple[float, float, float, float]:
    """
    Calculate safety stock components for a SKU.

    Args:
        d: Daily demand
        sigma: Demand standard deviation (default: from params or estimated)
        L: Lead time days (default: from inventory_params)
        B: Floor buffer days (default: from inventory_params)
        TV: Mix variability factor (default: from inventory_params)
        z: Service level z-score (default: from inventory_params)

    Returns:
        Tuple of (ss_demand, ss_floor, ss_mix, ss_total)

    Formulas:
        SS_demand = z × σ × sqrt(L)
        SS_floor = D × B
        SS_mix = TV × D × L
        SS_total = SS_demand + SS_floor + SS_mix

    Example:
        >>> ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock(d=10.0, sigma=3.0)
    """
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L
    B = B if B is not None else params.B
    TV = TV if TV is not None else params.TV
    z = z if z is not None else params.z

    # Default sigma if not provided (use coefficient of variation)
    if sigma is None:
        sigma = d * 0.3  # Assume 30% CV as default

    ss_demand = z * sigma * math.sqrt(L)
    ss_floor = d * B
    ss_mix = TV * d * L
    ss_total = ss_demand + ss_floor + ss_mix

    return ss_demand, ss_floor, ss_mix, ss_total


def calc_t_post(
    d: float,
    ss_total: float,
    R: int = None,
) -> float:
    """
    Calculate target post-arrival coverage days.

    IMPORTANT: T_post does NOT include lead time L.
    L is accounted in the pre-arrival consumption calculation.

    Args:
        d: Daily demand
        ss_total: Total safety stock
        R: Review period days (default: from inventory_params)

    Returns:
        T_post in days

    Formula:
        T_post = R + (SS_total / D)

    Edge case:
        If D = 0, returns R (minimum coverage)
    """
    return calc_t_post_for_size(d, ss_total, R)


def calc_pre_arrival(
    current_stock: int,
    inbound_stock: int,
    d: float,
    L: int = None,
    prep_days: int = 0,
) -> float:
    """
    Calculate projected stock at time of shipment arrival.

    Args:
        current_stock: On-hand inventory
        inbound_stock: In-transit inventory
        d: Daily demand
        L: Lead time days (default: from inventory_params)
        prep_days: Additional prep days to add to L

    Returns:
        Projected stock at arrival (minimum 0)

    Formula:
        effective_L = L + prep_days
        Pre = Current + Inbound - D × effective_L
    """
    from core.config.inventory_params import get_params

    params = get_params()
    L = L if L is not None else params.L
    effective_L = L + prep_days

    return calc_pre_arrival_stock(current_stock, inbound_stock, d, effective_L)


def calc_rop(
    d: float,
    ss_total: float,
    L: int = None,
) -> float:
    """
    Calculate reorder point for a SKU.

    Args:
        d: Daily demand
        ss_total: Total safety stock
        L: Lead time days (default: from inventory_params)

    Returns:
        Reorder point

    Formula:
        ROP = D × L + SS_total
    """
    return calc_rop_for_size(d, ss_total, L)


def should_reorder(
    current_stock: int,
    inbound_stock: int,
    rop: float,
) -> tuple[OrderStatus, str]:
    """
    Determine if a SKU should be reordered.

    Args:
        current_stock: On-hand inventory
        inbound_stock: In-transit inventory
        rop: Reorder point

    Returns:
        Tuple of (status, reason):
        - status: OrderStatus enum (REORDER, WAIT, OK)
        - reason: Human-readable explanation

    Logic:
        Total < ROP → REORDER ("Total stock below reorder point")
        Current < ROP (but Total ≥ ROP) → WAIT ("Inbound covers gap")
        Else → OK ("Sufficient stock")
    """
    total_stock = current_stock + inbound_stock
    status = calc_status_for_size(current_stock, total_stock, rop)

    if status == OrderStatus.REORDER:
        reason = f"Total stock ({total_stock}) below ROP ({rop:.0f})"
    elif status == OrderStatus.WAIT:
        reason = f"Current ({current_stock}) below ROP ({rop:.0f}) but inbound ({inbound_stock}) covers"
    else:
        reason = f"Sufficient stock: {total_stock} >= ROP ({rop:.0f})"

    return status, reason


# =============================================================================
# ROIC CALCULATION (re-exported from size_allocation)
# =============================================================================

def calc_sku_roic(
    d: float,
    profit_per_unit: float,
    cogs_per_unit: float,
    L: int = None,
    R: int = None,
    ss_total: float = 0,
) -> float:
    """
    Calculate monthly ROIC for a SKU.

    Args:
        d: Daily demand
        profit_per_unit: Profit per unit (KZT)
        cogs_per_unit: Cost of goods sold per unit (KZT)
        L: Lead time days
        R: Review period days
        ss_total: Total safety stock

    Returns:
        Monthly ROIC as a decimal (e.g., 0.25 = 25%)

    Formula:
        K_avg = D × (L + R/2) × COGS + SS × COGS
        Monthly_Profit = Profit × D × 30
        Monthly_ROIC = Monthly_Profit / K_avg
    """
    return calc_roic(d, profit_per_unit, cogs_per_unit, L, R, ss_total)


def check_roic_gate(roic: float, order_qty: int = 100) -> tuple[ROICAction, str]:
    """
    Apply 3-tier ROIC gate for PO approval.

    Args:
        roic: Monthly ROIC as a decimal
        order_qty: Order quantity (default: 100 for simple gate check)

    Returns:
        Tuple of (action, reason):
        - action: ROICAction enum
        - reason: Human-readable explanation

    Gates:
        ≥20%: ORDER_FULL (auto-approve)
        10-20%: ORDER_WITH_FLAG (approve with review flag)
        <10%: REVIEW_REQUIRED (manual approval needed)
    """
    action, _ = apply_roic_gate(roic, order_qty)

    if action == ROICAction.ORDER_FULL:
        reason = f"ROIC {roic*100:.1f}% >= 20%: Auto-approved"
    elif action == ROICAction.ORDER_WITH_FLAG:
        reason = f"ROIC {roic*100:.1f}% in 10-20%: Approved with review flag"
    else:
        reason = f"ROIC {roic*100:.1f}% < 10%: Manual review required"

    return action, reason


if __name__ == "__main__":
    # Quick sanity check
    print("PO Recommender Engine - Sanity Check")
    print("=" * 50)

    # Example: LINE52 with D=42 units/day
    result = calc_order_qty(
        d=42.0,
        current_stock=500,
        inbound_stock=300,
        ss_total=200.0,
        L=21,
        R=10,
        prep_days=5,
    )

    print(f"Daily demand: {result.d}")
    print(f"Current stock: {result.current_stock}")
    print(f"Inbound stock: {result.inbound_stock}")
    print(f"SS total: {result.ss_total}")
    print(f"ROP: {result.rop:.1f}")
    print(f"T_post: {result.t_post:.1f} days")
    print(f"Target: {result.target:.1f}")
    print(f"Pre-arrival: {result.pre_arrival:.1f}")
    print(f"Order qty: {result.order_qty}")
    print(f"Status: {result.status}")
    print(f"Deficit: {result.deficit:.1f}")
    print(f"Days of cover: {result.days_of_cover:.1f}")

    # Verify T_post formula: R + SS/D = 10 + 200/42 = 14.76
    expected_t_post = 10 + (200 / 42)
    assert abs(result.t_post - expected_t_post) < 0.01, f"T_post mismatch: {result.t_post} != {expected_t_post}"
    print(f"\nT_post formula verified: R + SS/D = {expected_t_post:.2f}")
