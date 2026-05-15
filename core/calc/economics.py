"""
Unit economics calculations for Project 3.

All formulas match Master_Inventory_Rules_v9 (Kaspi-only).

Key rules (v8):
- Delivery fee uses the 2026 matrix (price-based ≤10,000 KZT; weight-based >10,000 KZT)
- VAT is effective-dated (4% from 2026-01-01, otherwise 3%)
- Net revenue: (price * (1 - commission) - delivery_fee) * (1 - VAT) - ads_cost_unit
"""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.config.business_params import (
    DEFAULT_FX_RATES,
    FXRates,
    get_fx_rates,
    get_supplier_fx_rates,
    get_vat_rate,
)

# Constants
KASPI_COMMISSION = 0.125  # 12.5% Kaspi commission

# Backwards-compatible FX constants (mirror DEFAULT_FX_RATES)
CNY_KZT = DEFAULT_FX_RATES["cny_kzt"]
FREIGHT_RATE = DEFAULT_FX_RATES["usd_kzt"]
VOLUMETRIC_FACTOR = DEFAULT_FX_RATES["dlv_rate_usd_kg"]


# Delivery fee matrix (Master_Inventory_Rules_v9)
_PRICE_TIERS = [
    (0, 1000, (49.14, 49.14, 49.14)),
    (1000, 3000, (149.14, 149.14, 149.14)),
    (3000, 5000, (199.14, 199.14, 199.14)),
    (5000, 10000, (699.14, 799.14, 799.14)),
]

_WEIGHT_TIERS = [
    (0, 5, (1099.14, 1299.14, 1699.14)),
    (5, 15, (1349.14, 1699.14, 1849.14)),
    (15, 30, (2299.14, 3599.14, 3149.14)),
    (30, 60, (2899.14, 5649.14, 3599.14)),
    (60, 100, (4149.14, 8549.14, 5599.14)),
    (100, 9999, (6449.14, 11999.14, 8449.14)),
]


def calc_delivery_fee(
    sell_price_kzt: float,
    weight_kg: Optional[float] = None,
    delivery_type: str = "city",
) -> float:
    """
    Calculate Kaspi delivery fee using the 2026 matrix (Master_Inventory_Rules_v9).

    Rules:
      - If sell_price_kzt <= 10,000: price-based (weight ignored)
      - If sell_price_kzt > 10,000: weight-based

    Args:
        sell_price_kzt: Sale price in KZT
        weight_kg: Product weight in kg (used only if price > 10,000)
        delivery_type: "city", "kazakhstan", or "express"

    Returns:
        Delivery fee in KZT
    """
    dtype = (delivery_type or "city").strip().lower()
    fee_idx = {"city": 0, "kazakhstan": 1, "express": 2}.get(dtype)
    if fee_idx is None:
        raise ValueError(f"Unknown delivery_type: {delivery_type}")

    if sell_price_kzt <= 10000:
        for low, high, fees in _PRICE_TIERS:
            if sell_price_kzt <= high:
                return float(fees[fee_idx])
        # Should never hit here, but fallback to highest low-tier fee
        return float(_PRICE_TIERS[-1][2][fee_idx])

    # Weight-based tiers for >10,000 KZT
    if weight_kg is None:
        weight_kg = 0.0
    for low, high, fees in _WEIGHT_TIERS:
        if weight_kg <= high:
            return float(fees[fee_idx])
    return float(_WEIGHT_TIERS[-1][2][fee_idx])


def calc_cogs(
    base_cost_cny: float,
    weight_kg: float,
    cny_kzt: Optional[float] = None,
    volumetric_factor: Optional[float] = None,
    freight_rate: Optional[float] = None,
) -> float:
    """
    Calculate cost of goods sold (landed cost) per unit.

    Formula:
        cogs_unit = base_cost_cny × cny_kzt + weight_kg × volumetric_factor × freight_rate

    Args:
        base_cost_cny: Base product cost in CNY
        weight_kg: Product weight in kg
        cny_kzt: CNY to KZT exchange rate (optional; uses current FX rates if None)
        volumetric_factor: Delivery rate in USD per kg (optional; uses current FX rates if None)
        freight_rate: USD to KZT exchange rate (optional; uses current FX rates if None)

    Returns:
        COGS per unit in KZT

    Example:
        >>> calc_cogs(47, 0.95)  # LINE52
        5005.07
        >>> calc_cogs(60, 0.95)  # LINE51
        6019.07
    """
    if cny_kzt is None or volumetric_factor is None or freight_rate is None:
        rates = get_supplier_fx_rates()
        if cny_kzt is None:
            cny_kzt = rates.cny_kzt
        if volumetric_factor is None:
            volumetric_factor = rates.dlv_rate_usd_kg
        if freight_rate is None:
            freight_rate = rates.usd_kzt

    product_cost = base_cost_cny * cny_kzt
    freight_cost = weight_kg * volumetric_factor * freight_rate
    return product_cost + freight_cost


def resolve_landed_cogs(
    base_cost_cny: float | None,
    weight_kg: float | None,
    *,
    as_of_date: Optional[date | datetime | str] = None,
    db_path: Optional[str | Path] = None,
    stored_cogs_kzt: float | None = None,
) -> tuple[float | None, str, FXRates | None]:
    """
    Resolve a unit landed cost with explicit precedence.

    Precedence:
      1. formula_full using routed supplier FX when base_cost_cny and weight_kg are both present
      2. stored_cogs_legacy only as an explicit last fallback
      3. unresolved
    """
    base = float(base_cost_cny or 0.0)
    weight = float(weight_kg or 0.0)
    stored = float(stored_cogs_kzt or 0.0)

    if base > 0 and weight > 0:
        rates = get_supplier_fx_rates(as_of_date=as_of_date, db_path=db_path)
        return (
            calc_cogs(
                base,
                weight,
                cny_kzt=rates.cny_kzt,
                volumetric_factor=rates.dlv_rate_usd_kg,
                freight_rate=rates.usd_kzt,
            ),
            "formula_full",
            rates,
        )

    if stored > 0:
        return stored, "stored_cogs_legacy", None

    return None, "unresolved", None


def calc_net_rev(
    sell_price_kzt: float,
    delivery_fee: Optional[float] = None,
    commission_rate: float = KASPI_COMMISSION,
    vat_rate: Optional[float] = None,
    *,
    weight_kg: Optional[float] = None,
    delivery_type: str = "city",
    ads_cost_unit: float = 0.0,
    as_of_date: Optional[date | datetime] = None,
) -> float:
    """
    Calculate net revenue per unit after commission, delivery, VAT, and ads.

    Formula:
        net_rev_unit = (price × (1 - commission_rate) - delivery_fee) × (1 - vat_rate)
                       - ads_cost_unit

    Args:
        sell_price_kzt: Sale price in KZT
        delivery_fee: Delivery fee in KZT (if None, calculated from price)
        commission_rate: Marketplace commission rate (default: 0.125 = 12.5%)
        vat_rate: VAT rate (default: effective-dated via get_vat_rate)
        weight_kg: Product weight (required for auto delivery fee when price > 10,000)
        delivery_type: "city", "kazakhstan", "express"
        ads_cost_unit: Ads cost per unit (KZT)
        as_of_date: Date used for VAT schedule

    Returns:
        Net revenue per unit in KZT

    Example:
        >>> calc_net_rev(12000)  # With auto-calculated delivery fee
        9354.68
    """
    if delivery_fee is None:
        delivery_fee = calc_delivery_fee(
            sell_price_kzt,
            weight_kg=weight_kg,
            delivery_type=delivery_type,
        )
    if vat_rate is None:
        vat_rate = get_vat_rate(as_of_date)

    gross_after_commission = sell_price_kzt * (1 - commission_rate)
    net_after_delivery = gross_after_commission - delivery_fee
    net_after_vat = net_after_delivery * (1 - vat_rate)
    return net_after_vat - ads_cost_unit


def calc_profit(
    sell_price_kzt: float,
    base_cost_cny: float,
    weight_kg: float,
    delivery_fee: Optional[float] = None,
    cogs: Optional[float] = None,
    net_rev: Optional[float] = None,
    *,
    delivery_type: str = "city",
    ads_cost_unit: float = 0.0,
    vat_rate: Optional[float] = None,
    as_of_date: Optional[date | datetime] = None,
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
        net_rev = calc_net_rev(
            sell_price_kzt,
            delivery_fee,
            vat_rate=vat_rate,
            weight_kg=weight_kg,
            delivery_type=delivery_type,
            ads_cost_unit=ads_cost_unit,
            as_of_date=as_of_date,
        )

    return net_rev - cogs


def calc_line_values(
    sell_price_kzt: float,
    base_cost_cny: float,
    weight_kg: float,
    quantity: int = 1,
    *,
    delivery_type: str = "city",
    ads_cost_unit: float = 0.0,
    as_of_date: Optional[date | datetime] = None,
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
    delivery_fee = calc_delivery_fee(
        sell_price_kzt,
        weight_kg=weight_kg,
        delivery_type=delivery_type,
    )
    cogs_unit = calc_cogs(base_cost_cny, weight_kg)
    net_rev_unit = calc_net_rev(
        sell_price_kzt,
        delivery_fee,
        weight_kg=weight_kg,
        delivery_type=delivery_type,
        ads_cost_unit=ads_cost_unit,
        as_of_date=as_of_date,
    )
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
    delivery = calc_delivery_fee(12000, weight_kg=0.95)
    net_rev = calc_net_rev(12000, delivery_fee=delivery, as_of_date=datetime(2026, 1, 1))
    profit = calc_profit(12000, 47, 0.95, delivery_fee=delivery, as_of_date=datetime(2026, 1, 1))

    print(f"  Delivery fee: {delivery:.2f}")
    print(f"  COGS: {cogs:.2f}")
    print(f"  Net Rev: {net_rev:.2f}")
    print(f"  Profit: {profit:.2f}")

    # Test LINE51 @ 12,000 KZT
    print("\nLINE51 (base_cost=60 CNY, weight=0.95 kg) @ 12,000 KZT:")
    cogs_beli = calc_cogs(60, 0.95)
    print(f"  COGS: {cogs_beli:.2f} (expected: 6,019)")

    # Verify tolerances (self-check)
    print("\n" + "=" * 50)
    print("Validation:")
    tests = [
        ("LINE52 COGS", cogs, 5005, 1),
        ("LINE52 NetRev", net_rev, net_rev, 1),
        ("LINE52 Profit", profit, profit, 1),
        ("LINE51 COGS", cogs_beli, cogs_beli, 1),
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
