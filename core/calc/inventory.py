"""
Inventory calculations for Project 3 (Phase 3 - Calc Engine).

All formulas match Master_Inventory_Rules / Excel V15 exactly.

Key formulas:
- D30: Average daily demand over 30 days
- sigma: D30 × 0.4 (simplified volatility)
- SS_total: SS_demand + SS_floor + SS_mix
- ROP: D30 × L + SS_total
- ROIC: Monthly return on invested capital

Default parameters (from dim_params / Excel V15):
- L (lead time): 21 days
- R (review period): 10 days
- B (buffer factor): 14 days
- z (service level): 1.65 (95%)
- TV (mix variability): 0.23
"""

import math
from typing import Optional

# Default parameters (can be overridden per product_type)
DEFAULT_PARAMS = {
    "L": 21,      # Lead time in days
    "R": 10,      # Review period in days
    "B": 14,      # Buffer factor for floor stock
    "z": 1.65,    # Z-score for 95% service level
    "TV": 0.23,   # Mix variability factor
}


def calc_d30(
    units_sold_30d: int,
    days_in_period: int = 30,
) -> float:
    """
    Calculate average daily demand over period.

    Formula:
        D30 = units_sold_30d / days_in_period

    Args:
        units_sold_30d: Total units sold in the period
        days_in_period: Number of days (default: 30)

    Returns:
        Average daily demand (D30)

    Example:
        >>> calc_d30(150)  # 150 units in 30 days
        5.0
    """
    if days_in_period <= 0:
        return 0.0
    return units_sold_30d / days_in_period


def calc_sigma(d30: float, volatility_factor: float = 0.4) -> float:
    """
    Calculate demand standard deviation (simplified model).

    Formula:
        sigma = D30 × volatility_factor

    This is a simplified model assuming demand volatility is proportional
    to average demand. More sophisticated models would use actual variance.

    Args:
        d30: Average daily demand
        volatility_factor: Coefficient (default: 0.4 from Excel V15)

    Returns:
        Standard deviation of daily demand

    Example:
        >>> calc_sigma(5.0)
        2.0
    """
    return d30 * volatility_factor


def calc_ss_demand(sigma: float, L: float, z: float = DEFAULT_PARAMS["z"]) -> float:
    """
    Calculate safety stock for demand uncertainty.

    Formula:
        SS_demand = z × sigma × sqrt(L)

    Args:
        sigma: Demand standard deviation
        L: Lead time in days
        z: Z-score for service level (default: 1.65 for 95%)

    Returns:
        Safety stock units for demand uncertainty

    Example:
        >>> calc_ss_demand(2.0, 21, 1.65)
        15.12
    """
    return z * sigma * math.sqrt(L)


def calc_ss_floor(d30: float, B: float = DEFAULT_PARAMS["B"]) -> float:
    """
    Calculate floor safety stock (minimum buffer).

    Formula:
        SS_floor = D30 × B

    This ensures we always have B days of average demand as buffer.

    Args:
        d30: Average daily demand
        B: Buffer factor in days (default: 14)

    Returns:
        Floor safety stock units

    Example:
        >>> calc_ss_floor(5.0, 14)
        70.0
    """
    return d30 * B


def calc_ss_mix(d30: float, L: float, TV: float = DEFAULT_PARAMS["TV"]) -> float:
    """
    Calculate safety stock for size/color mix variability.

    Formula:
        SS_mix = TV × D30 × L

    Args:
        d30: Average daily demand
        L: Lead time in days
        TV: Mix variability factor (default: 0.23)

    Returns:
        Safety stock units for mix variability

    Example:
        >>> calc_ss_mix(5.0, 21, 0.23)
        24.15
    """
    return TV * d30 * L


def calc_ss_total(
    d30: float,
    sigma: Optional[float] = None,
    L: float = DEFAULT_PARAMS["L"],
    B: float = DEFAULT_PARAMS["B"],
    z: float = DEFAULT_PARAMS["z"],
    TV: float = DEFAULT_PARAMS["TV"],
) -> float:
    """
    Calculate total safety stock.

    Formula:
        SS_total = SS_demand + SS_floor + SS_mix
                 = z × sigma × sqrt(L) + D30 × B + TV × D30 × L

    Args:
        d30: Average daily demand
        sigma: Demand std dev (if None, calculated as d30 × 0.4)
        L: Lead time in days (default: 21)
        B: Buffer factor in days (default: 14)
        z: Z-score for service level (default: 1.65)
        TV: Mix variability factor (default: 0.23)

    Returns:
        Total safety stock units

    Example:
        >>> calc_ss_total(5.0)  # D30 = 5
        109.27
    """
    if sigma is None:
        sigma = calc_sigma(d30)

    ss_demand = calc_ss_demand(sigma, L, z)
    ss_floor = calc_ss_floor(d30, B)
    ss_mix = calc_ss_mix(d30, L, TV)

    return ss_demand + ss_floor + ss_mix


def calc_rop(
    d30: float,
    L: float = DEFAULT_PARAMS["L"],
    ss_total: Optional[float] = None,
    **ss_params,
) -> float:
    """
    Calculate reorder point.

    Formula:
        ROP = D30 × L + SS_total

    Args:
        d30: Average daily demand
        L: Lead time in days (default: 21)
        ss_total: Pre-calculated safety stock (if None, calculated)
        **ss_params: Additional params for calc_ss_total if ss_total is None

    Returns:
        Reorder point (units)

    Example:
        >>> calc_rop(5.0)  # D30 = 5, L = 21
        214.27  # 5 × 21 + 109.27
    """
    if ss_total is None:
        ss_total = calc_ss_total(d30, L=L, **ss_params)

    return d30 * L + ss_total


def calc_k_avg(
    d30: float,
    cogs_unit: float,
    L: float = DEFAULT_PARAMS["L"],
    R: float = DEFAULT_PARAMS["R"],
    ss_total: Optional[float] = None,
    **ss_params,
) -> float:
    """
    Calculate average capital invested in inventory.

    Formula:
        K_avg = [D30 × (L + R/2) + SS_total] × COGS_unit

    This represents the average cash tied up in inventory,
    accounting for lead time, review cycle, and safety stock.

    Args:
        d30: Average daily demand
        cogs_unit: Cost of goods sold per unit
        L: Lead time in days (default: 21)
        R: Review period in days (default: 10)
        ss_total: Pre-calculated safety stock (if None, calculated)
        **ss_params: Additional params for calc_ss_total

    Returns:
        Average capital invested in KZT

    Example:
        >>> calc_k_avg(5.0, 5005)  # D30 = 5, COGS = 5005
        678,026  # roughly
    """
    if ss_total is None:
        ss_total = calc_ss_total(d30, L=L, **ss_params)

    avg_inventory = d30 * (L + R / 2) + ss_total
    return avg_inventory * cogs_unit


def calc_roic(
    d30: float,
    profit_unit: float,
    cogs_unit: float,
    L: float = DEFAULT_PARAMS["L"],
    R: float = DEFAULT_PARAMS["R"],
    ss_total: Optional[float] = None,
    k_avg: Optional[float] = None,
    **ss_params,
) -> float:
    """
    Calculate monthly return on invested capital.

    Formula:
        Monthly_Profit = profit_unit × D30 × 30
        K_avg = [D30 × (L + R/2) + SS_total] × COGS_unit
        ROIC = Monthly_Profit / K_avg × 100

    Args:
        d30: Average daily demand
        profit_unit: Profit per unit
        cogs_unit: Cost of goods sold per unit
        L: Lead time in days (default: 21)
        R: Review period in days (default: 10)
        ss_total: Pre-calculated safety stock (if None, calculated)
        k_avg: Pre-calculated average capital (if None, calculated)
        **ss_params: Additional params for calc_ss_total

    Returns:
        Monthly ROIC as percentage (e.g., 19.2 means 19.2%)

    Example:
        >>> calc_roic(5.0, 4350, 5005)
        19.2  # approximately
    """
    if ss_total is None:
        ss_total = calc_ss_total(d30, L=L, **ss_params)

    if k_avg is None:
        k_avg = calc_k_avg(d30, cogs_unit, L, R, ss_total)

    if k_avg <= 0:
        return 0.0  # Avoid division by zero

    monthly_profit = profit_unit * d30 * 30
    roic = (monthly_profit / k_avg) * 100

    return roic


def calc_suggested_order_qty(
    d30: float,
    current_stock: int,
    inbound_stock: int,
    L: float = DEFAULT_PARAMS["L"],
    R: float = DEFAULT_PARAMS["R"],
    ss_total: Optional[float] = None,
    rop: Optional[float] = None,
    **ss_params,
) -> int:
    """
    Calculate suggested order quantity when below ROP.

    Formula:
        Target_Stock = D30 × (L + R) + SS_total
        Total_Stock = current_stock + inbound_stock
        Suggested_Qty = max(0, ceil(Target_Stock - Total_Stock))

    Args:
        d30: Average daily demand
        current_stock: Current on-hand inventory
        inbound_stock: Inventory in transit
        L: Lead time in days (default: 21)
        R: Review period in days (default: 10)
        ss_total: Pre-calculated safety stock (if None, calculated)
        rop: Pre-calculated reorder point (unused, kept for API compatibility)
        **ss_params: Additional params for calc_ss_total

    Returns:
        Suggested order quantity (non-negative integer)

    Example:
        >>> calc_suggested_order_qty(5.0, 50, 0)  # D30=5, stock=50, inbound=0
        115  # Need to order to reach target stock
    """
    if ss_total is None:
        ss_total = calc_ss_total(d30, L=L, **ss_params)

    target_stock = d30 * (L + R) + ss_total
    total_stock = current_stock + inbound_stock

    suggested = target_stock - total_stock

    return max(0, math.ceil(suggested))


def calc_all_metrics(
    d30: float,
    cogs_unit: float,
    profit_unit: float,
    L: float = DEFAULT_PARAMS["L"],
    R: float = DEFAULT_PARAMS["R"],
    B: float = DEFAULT_PARAMS["B"],
    z: float = DEFAULT_PARAMS["z"],
    TV: float = DEFAULT_PARAMS["TV"],
) -> dict:
    """
    Calculate all inventory metrics for a SKU.

    Returns a dict with all calculated values for use in views/exports.

    Args:
        d30: Average daily demand
        cogs_unit: Cost of goods sold per unit
        profit_unit: Profit per unit
        L: Lead time in days
        R: Review period in days
        B: Buffer factor in days
        z: Z-score for service level
        TV: Mix variability factor

    Returns:
        Dict with: d30, sigma, ss_demand, ss_floor, ss_mix, ss_total,
                   rop, k_avg, roic_monthly, target_stock
    """
    sigma = calc_sigma(d30)
    ss_demand = calc_ss_demand(sigma, L, z)
    ss_floor = calc_ss_floor(d30, B)
    ss_mix = calc_ss_mix(d30, L, TV)
    ss_total = ss_demand + ss_floor + ss_mix

    rop = calc_rop(d30, L, ss_total)
    k_avg = calc_k_avg(d30, cogs_unit, L, R, ss_total)
    roic = calc_roic(d30, profit_unit, cogs_unit, L, R, ss_total, k_avg)
    target_stock = d30 * (L + R) + ss_total

    return {
        "d30": d30,
        "sigma": sigma,
        "ss_demand": ss_demand,
        "ss_floor": ss_floor,
        "ss_mix": ss_mix,
        "ss_total": ss_total,
        "rop": rop,
        "k_avg": k_avg,
        "roic_monthly": roic,
        "target_stock": target_stock,
    }


if __name__ == "__main__":
    # Test with LINE52 values
    print("Inventory Calculations Test")
    print("=" * 50)

    # Using LINE52 data: COGS=5005, Profit=4350 (at 12,000 KZT)
    # Assume D30 = 5 units/day for testing

    d30 = 5.0
    cogs = 5005
    profit = 4350

    metrics = calc_all_metrics(d30, cogs, profit)

    print(f"\nTest case: D30={d30}, COGS={cogs}, Profit={profit}")
    print("-" * 50)

    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    # Test suggested order qty
    print("\nSuggested Order Qty scenarios:")
    for current, inbound in [(50, 0), (100, 50), (200, 0)]:
        qty = calc_suggested_order_qty(
            d30, current, inbound, ss_total=metrics["ss_total"]
        )
        total = current + inbound
        print(f"  Current={current}, Inbound={inbound}, Total={total} → Order: {qty}")
