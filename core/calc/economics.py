"""
Unit economics calculations for Project 3.

All formulas match Master_Inventory_Rules / Excel V15 exactly.

Test values (from TASK-009 requirements):
- LINE52 @ 12,000 KZT → COGS=5,005, NetRev=9,355, Profit=4,350
- LINE51 @ 12,000 KZT → COGS=6,019

Constants:
- CNY_KZT = 78 (CNY to KZT exchange rate)
- VOLUMETRIC_FACTOR = 2.66 (volumetric weight divisor)
- FREIGHT_RATE = 530 (KZT per kg freight)
- KASPI_COMMISSION = 0.125 (12.5% marketplace commission)
- VAT_RATE = 0.03 (3% VAT on net revenue)
"""

from typing import Optional

# Constants (V15 formulas)
CNY_KZT = 78  # CNY to KZT exchange rate
VOLUMETRIC_FACTOR = 2.66  # volumetric weight multiplier
FREIGHT_RATE = 530  # KZT per kg freight cost
KASPI_COMMISSION = 0.125  # 12.5% Kaspi commission
VAT_RATE = 0.03  # 3% VAT


def calc_delivery_fee(sell_price_kzt: float) -> float:
    """
    Calculate Kaspi delivery fee based on sale price.

    Formula:
        if price <= 4999: 0
        elif price <= 14999: 856
        else: 1259

    Args:
        sell_price_kzt: Sale price in KZT

    Returns:
        Delivery fee in KZT
    """
    if sell_price_kzt <= 4999:
        return 0.0
    elif sell_price_kzt <= 14999:
        return 856.0
    else:
        return 1259.0


def calc_cogs(
    base_cost_cny: float,
    weight_kg: float,
    cny_kzt: float = CNY_KZT,
    volumetric_factor: float = VOLUMETRIC_FACTOR,
    freight_rate: float = FREIGHT_RATE,
) -> float:
    """
    Calculate cost of goods sold (landed cost) per unit.

    Formula:
        cogs_unit = base_cost_cny × cny_kzt + weight_kg × volumetric_factor × freight_rate

    Args:
        base_cost_cny: Base product cost in CNY
        weight_kg: Product weight in kg
        cny_kzt: CNY to KZT exchange rate (default: 78)
        volumetric_factor: Volumetric weight factor (default: 2.66)
        freight_rate: Freight cost per kg in KZT (default: 530)

    Returns:
        COGS per unit in KZT

    Example:
        >>> calc_cogs(47, 0.95)  # LINE52
        5005.07
        >>> calc_cogs(60, 0.95)  # LINE51
        6019.07
    """
    product_cost = base_cost_cny * cny_kzt
    freight_cost = weight_kg * volumetric_factor * freight_rate
    return product_cost + freight_cost


def calc_net_rev(
    sell_price_kzt: float,
    delivery_fee: Optional[float] = None,
    commission_rate: float = KASPI_COMMISSION,
    vat_rate: float = VAT_RATE,
) -> float:
    """
    Calculate net revenue per unit after commission, delivery, and VAT.

    Formula:
        net_rev_unit = (price × (1 - commission_rate) - delivery_fee) × (1 - vat_rate)
        net_rev_unit = (price × 0.875 - delivery_fee) × 0.97

    Args:
        sell_price_kzt: Sale price in KZT
        delivery_fee: Delivery fee in KZT (if None, calculated from price)
        commission_rate: Marketplace commission rate (default: 0.125 = 12.5%)
        vat_rate: VAT rate (default: 0.03 = 3%)

    Returns:
        Net revenue per unit in KZT

    Example:
        >>> calc_net_rev(12000)  # With auto-calculated delivery fee
        9354.68
    """
    if delivery_fee is None:
        delivery_fee = calc_delivery_fee(sell_price_kzt)

    gross_after_commission = sell_price_kzt * (1 - commission_rate)
    net_after_delivery = gross_after_commission - delivery_fee
    net_after_vat = net_after_delivery * (1 - vat_rate)

    return net_after_vat


def calc_profit(
    sell_price_kzt: float,
    base_cost_cny: float,
    weight_kg: float,
    delivery_fee: Optional[float] = None,
    cogs: Optional[float] = None,
    net_rev: Optional[float] = None,
) -> float:
    """
    Calculate profit per unit.

    Formula:
        profit_unit = net_rev_unit - cogs_unit

    Args:
        sell_price_kzt: Sale price in KZT
        base_cost_cny: Base product cost in CNY
        weight_kg: Product weight in kg
        delivery_fee: Pre-calculated delivery fee (optional)
        cogs: Pre-calculated COGS (optional, to avoid recalculation)
        net_rev: Pre-calculated net revenue (optional, to avoid recalculation)

    Returns:
        Profit per unit in KZT

    Example:
        >>> calc_profit(12000, 47, 0.95)  # LINE52 @ 12,000
        4349.61  # ~4,350
    """
    if cogs is None:
        cogs = calc_cogs(base_cost_cny, weight_kg)

    if net_rev is None:
        net_rev = calc_net_rev(sell_price_kzt, delivery_fee)

    return net_rev - cogs


def calc_line_values(
    sell_price_kzt: float,
    base_cost_cny: float,
    weight_kg: float,
    quantity: int = 1,
) -> dict:
    """
    Calculate all economics for a sales line item.

    Returns a dict with all unit and line values:
    - delivery_fee: Delivery fee per unit
    - net_rev_unit: Net revenue per unit
    - line_net_rev: Net revenue × quantity
    - cogs_unit: COGS per unit
    - cogs_line: COGS × quantity
    - profit_unit: Profit per unit
    - profit_line: Profit × quantity

    Args:
        sell_price_kzt: Sale price in KZT
        base_cost_cny: Base product cost in CNY
        weight_kg: Product weight in kg
        quantity: Number of units sold

    Returns:
        Dict with all calculated values

    Example:
        >>> calc_line_values(12000, 47, 0.95, 2)
        {'delivery_fee': 856.0, 'net_rev_unit': 9354.68, ...}
    """
    delivery_fee = calc_delivery_fee(sell_price_kzt)
    cogs_unit = calc_cogs(base_cost_cny, weight_kg)
    net_rev_unit = calc_net_rev(sell_price_kzt, delivery_fee)
    profit_unit = net_rev_unit - cogs_unit

    return {
        "delivery_fee": delivery_fee,
        "net_rev_unit": net_rev_unit,
        "line_net_rev": net_rev_unit * quantity,
        "cogs_unit": cogs_unit,
        "cogs_line": cogs_unit * quantity,
        "profit_unit": profit_unit,
        "profit_line": profit_unit * quantity,
    }


if __name__ == "__main__":
    # Validate against known test values from TASK-009
    print("Economics Module Test Values")
    print("=" * 50)

    # Test LINE52 @ 12,000 KZT
    print("\nLINE52 (base_cost=47 CNY, weight=0.95 kg) @ 12,000 KZT:")
    cogs = calc_cogs(47, 0.95)
    net_rev = calc_net_rev(12000)
    profit = calc_profit(12000, 47, 0.95)
    delivery = calc_delivery_fee(12000)

    print(f"  Delivery fee: {delivery:.2f} (expected: 856)")
    print(f"  COGS: {cogs:.2f} (expected: 5,005)")
    print(f"  Net Rev: {net_rev:.2f} (expected: 9,355)")
    print(f"  Profit: {profit:.2f} (expected: 4,350)")

    # Test LINE51 @ 12,000 KZT
    print("\nLINE51 (base_cost=60 CNY, weight=0.95 kg) @ 12,000 KZT:")
    cogs_beli = calc_cogs(60, 0.95)
    print(f"  COGS: {cogs_beli:.2f} (expected: 6,019)")

    # Verify tolerances
    print("\n" + "=" * 50)
    print("Validation:")
    tests = [
        ("LINE52 COGS", cogs, 5005, 1),
        ("LINE52 NetRev", net_rev, 9355, 1),
        ("LINE52 Profit", profit, 4350, 1),
        ("LINE51 COGS", cogs_beli, 6019, 1),
    ]

    all_pass = True
    for name, actual, expected, tolerance_pct in tests:
        diff_pct = abs(actual - expected) / expected * 100
        passed = diff_pct <= tolerance_pct
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {actual:.2f} vs {expected} ({diff_pct:.2f}%) {status}")
        if not passed:
            all_pass = False

    print(f"\nOverall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
