"""
Wildberries economics calculations for Phase 8.

Based on WB_policy_v4.md:
- Commission: 24.5% of seller price (Цена товара)
- Logistics + Storage: 408₽ per unit (weighted avg for Line52/Line51)
- Government tax: 3% of KZT revenue
- FX: RUB/KZT = 6.6 (configurable)

NOTE: The 408₽ logistics fee is a PROXY value for Line52/Line51 clothes.
It's a composite of: logistics, storage, return handling, and warehouse fees.
Actual fees vary by product dimensions, weight, warehouse, and turnover.
Phase 9+ will integrate full WB tariff calculator for per-SKU accuracy.

Test values (from WB_policy_v4.md):
- LINE52 @ 2,800₽ SPP → Expected monthly ROIC ~68%
- Break-even at ~40% margin target
"""
from dataclasses import dataclass
from typing import Optional

# Default FX rates (can be overridden)
DEFAULT_FX_RUB_KZT = 6.6
DEFAULT_FX_USD_KZT = 530
DEFAULT_FX_CNY_KZT = 78

# WB fee structure
WB_COMMISSION_PCT = 24.5
WB_LOGISTICS_FEE_RUB = 408
WB_TAX_PCT = 3.0

# Payment terms
WB_PAYMENT_DELAY_DAYS = 11  # 7-day sales period + 4 days
WB_PAYMENT_CYCLE_DAYS = 7

# Lead times (King's formula parameters)
WB_L3_DAYS = 10  # Astana → WB warehouses
WB_SAFETY_BUFFER = 14
WB_REORDER_CYCLE = 10


@dataclass
class WBEconomics:
    """Result of WB unit economics calculation."""

    seller_price_rub: float  # Цена товара (before SPP discount)
    customer_price_rub: float  # Price customer sees (with SPP)
    gross_revenue_rub: float
    commission_rub: float
    logistics_fee_rub: float
    net_revenue_rub: float
    net_revenue_kzt: float
    tax_kzt: float
    final_revenue_kzt: float
    cogs_kzt: float
    profit_kzt: float
    margin_pct: float


def calc_wb_net_revenue(
    seller_price_rub: float,
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
    logistics_fee_rub: float = WB_LOGISTICS_FEE_RUB,
    commission_pct: float = WB_COMMISSION_PCT,
    tax_pct: float = WB_TAX_PCT,
) -> tuple[float, float]:
    """
    Calculate WB net revenue in RUB and KZT.

    Formula:
        NetRev_RUB = Price × (1 - comm%) - logistics
        NetRev_KZT = NetRev_RUB × FX × (1 - tax%)

    Args:
        seller_price_rub: Seller price in RUB (Цена товара)
        fx_rub_kzt: RUB to KZT exchange rate
        logistics_fee_rub: WB logistics fee in RUB
        commission_pct: WB commission percentage
        tax_pct: Government tax percentage

    Returns:
        Tuple of (net_revenue_rub, net_revenue_kzt)

    Example:
        >>> net_rub, net_kzt = calc_wb_net_revenue(2800)
        >>> print(f"Net RUB: {net_rub:.2f}, Net KZT: {net_kzt:.2f}")
        Net RUB: 1706.00, Net KZT: 10923.25
    """
    gross_rub = seller_price_rub
    commission_rub = gross_rub * (commission_pct / 100)
    after_commission = gross_rub - commission_rub
    net_rub = after_commission - logistics_fee_rub

    # Convert to KZT and apply tax
    gross_kzt = net_rub * fx_rub_kzt
    tax_kzt = gross_kzt * (tax_pct / 100)
    net_kzt = gross_kzt - tax_kzt

    return net_rub, net_kzt


def calc_wb_profit(
    seller_price_rub: float,
    cogs_kzt: float,
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
    logistics_fee_rub: float = WB_LOGISTICS_FEE_RUB,
    commission_pct: float = WB_COMMISSION_PCT,
    tax_pct: float = WB_TAX_PCT,
) -> float:
    """
    Calculate WB unit profit in KZT.

    Args:
        seller_price_rub: Seller price in RUB
        cogs_kzt: Cost of goods sold in KZT
        fx_rub_kzt: RUB to KZT exchange rate
        logistics_fee_rub: WB logistics fee in RUB
        commission_pct: WB commission percentage
        tax_pct: Government tax percentage

    Returns:
        Profit per unit in KZT

    Example:
        >>> profit = calc_wb_profit(2800, 5285)  # LINE52 @ 2,800₽
        >>> print(f"Profit: {profit:.2f} KZT")
    """
    _, net_kzt = calc_wb_net_revenue(
        seller_price_rub, fx_rub_kzt, logistics_fee_rub, commission_pct, tax_pct
    )
    return net_kzt - cogs_kzt


def calc_wb_full_economics(
    seller_price_rub: float,
    cogs_kzt: float,
    customer_price_rub: Optional[float] = None,
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
    logistics_fee_rub: float = WB_LOGISTICS_FEE_RUB,
    commission_pct: float = WB_COMMISSION_PCT,
    tax_pct: float = WB_TAX_PCT,
) -> WBEconomics:
    """
    Full WB unit economics breakdown.

    Args:
        seller_price_rub: Цена товара (seller's price, commission base)
        cogs_kzt: Cost of goods sold in KZT
        customer_price_rub: Optional customer-facing price (with SPP)
        fx_rub_kzt: RUB to KZT exchange rate
        logistics_fee_rub: WB logistics + storage fee
        commission_pct: WB commission percentage
        tax_pct: Government tax percentage

    Returns:
        WBEconomics dataclass with full breakdown

    Example:
        >>> econ = calc_wb_full_economics(2800, 5285)
        >>> print(f"Profit: {econ.profit_kzt:.2f}, Margin: {econ.margin_pct:.1f}%")
    """
    gross_rub = seller_price_rub
    commission_rub = gross_rub * (commission_pct / 100)
    after_commission = gross_rub - commission_rub
    net_rub = after_commission - logistics_fee_rub

    gross_kzt = net_rub * fx_rub_kzt
    tax_kzt = gross_kzt * (tax_pct / 100)
    net_kzt = gross_kzt - tax_kzt

    profit = net_kzt - cogs_kzt
    margin = (profit / net_kzt * 100) if net_kzt > 0 else 0

    return WBEconomics(
        seller_price_rub=seller_price_rub,
        customer_price_rub=customer_price_rub or seller_price_rub,
        gross_revenue_rub=gross_rub,
        commission_rub=commission_rub,
        logistics_fee_rub=logistics_fee_rub,
        net_revenue_rub=net_rub,
        net_revenue_kzt=gross_kzt,  # Before tax
        tax_kzt=tax_kzt,
        final_revenue_kzt=net_kzt,
        cogs_kzt=cogs_kzt,
        profit_kzt=profit,
        margin_pct=margin,
    )


def calc_wb_breakeven_price(
    cogs_kzt: float,
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
    target_margin_pct: float = 0,
    logistics_fee_rub: float = WB_LOGISTICS_FEE_RUB,
    commission_pct: float = WB_COMMISSION_PCT,
    tax_pct: float = WB_TAX_PCT,
) -> float:
    """
    Calculate minimum seller price (RUB) to achieve target margin.

    At breakeven (margin=0): NetRev_KZT = COGS_KZT

    Working backwards:
        NetRev_KZT = COGS / (1 - target_margin/100)
        NetRev_RUB = NetRev_KZT / FX / (1 - tax%)
        Price = (NetRev_RUB + logistics) / (1 - comm%)

    Args:
        cogs_kzt: Cost of goods sold in KZT
        fx_rub_kzt: RUB to KZT exchange rate
        target_margin_pct: Target margin percentage (0 = breakeven)
        logistics_fee_rub: WB logistics fee in RUB
        commission_pct: WB commission percentage
        tax_pct: Government tax percentage

    Returns:
        Minimum seller price in RUB (rounded)

    Example:
        >>> price = calc_wb_breakeven_price(5285, target_margin_pct=40)
        >>> print(f"Price for 40% margin: {price:.0f}₽")
    """
    # Calculate target final revenue
    if target_margin_pct >= 100:
        target_revenue_kzt = cogs_kzt
    else:
        target_revenue_kzt = cogs_kzt / (1 - target_margin_pct / 100)

    # Work backwards: final_kzt -> gross_kzt -> net_rub -> price
    target_gross_kzt = target_revenue_kzt / (1 - tax_pct / 100)
    target_net_rub = target_gross_kzt / fx_rub_kzt
    target_after_logistics = target_net_rub + logistics_fee_rub
    seller_price = target_after_logistics / (1 - commission_pct / 100)

    return round(seller_price, 0)


def calc_wb_margin(
    seller_price_rub: float,
    cogs_kzt: float,
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
    logistics_fee_rub: float = WB_LOGISTICS_FEE_RUB,
    commission_pct: float = WB_COMMISSION_PCT,
    tax_pct: float = WB_TAX_PCT,
) -> float:
    """
    Calculate WB margin percentage.

    Args:
        seller_price_rub: Seller price in RUB
        cogs_kzt: Cost of goods sold in KZT
        fx_rub_kzt: RUB to KZT exchange rate
        logistics_fee_rub: WB logistics fee in RUB
        commission_pct: WB commission percentage
        tax_pct: Government tax percentage

    Returns:
        Margin as percentage

    Example:
        >>> margin = calc_wb_margin(2800, 5285)
        >>> print(f"Margin: {margin:.1f}%")
    """
    _, net_kzt = calc_wb_net_revenue(
        seller_price_rub, fx_rub_kzt, logistics_fee_rub, commission_pct, tax_pct
    )
    profit = net_kzt - cogs_kzt
    return (profit / net_kzt * 100) if net_kzt > 0 else 0


def calc_wb_roic(
    profit_30d_kzt: float,
    capital_deployed_kzt: float,
    annualize: bool = True,
) -> float:
    """
    Calculate WB ROIC.

    Same formula as Kaspi, but capital deployed calculation
    accounts for longer lead times and payment delays.

    Args:
        profit_30d_kzt: 30-day profit in KZT
        capital_deployed_kzt: Capital deployed in KZT
        annualize: Whether to annualize (multiply by 12.17)

    Returns:
        ROIC as percentage

    Example:
        >>> roic = calc_wb_roic(500000, 1000000)
        >>> print(f"Annual ROIC: {roic:.1f}%")
    """
    if capital_deployed_kzt <= 0:
        return 0.0

    roic_30d = (profit_30d_kzt / capital_deployed_kzt) * 100

    if annualize:
        return roic_30d * 12.17  # Annualization factor
    return roic_30d


def calc_wb_capital_required(
    d30_units: float,
    cogs_kzt: float,
    safety_buffer_days: int = WB_SAFETY_BUFFER,
    l1_days: int = 21,  # China -> Astana
    l2_days: int = 1,  # Fulfillment (per 200 units, min 1)
    l3_days: int = WB_L3_DAYS,  # Astana -> WB
    reorder_cycle: int = WB_REORDER_CYCLE,
) -> float:
    """
    Calculate capital required for WB operations.

    Uses King's formula lead times specific to WB:
    - L1: China → Astana (21 days avg)
    - L2: Fulfillment (1 day per 200 units)
    - L3: Astana → WB (10 days)
    - B: Safety buffer (14 days)
    - R: Reorder cycle (10 days)

    Args:
        d30_units: 30-day demand in units
        cogs_kzt: COGS per unit in KZT
        safety_buffer_days: Safety buffer days
        l1_days: China to Astana lead time
        l2_days: Fulfillment days
        l3_days: Astana to WB lead time
        reorder_cycle: Reorder cycle days

    Returns:
        Capital required in KZT

    Example:
        >>> capital = calc_wb_capital_required(360, 5285)  # D=12/day for 30 days
        >>> print(f"Capital required: {capital:,.0f} KZT")
    """
    daily_demand = d30_units / 30
    total_lead_time = l1_days + l2_days + l3_days
    total_cover_days = total_lead_time + safety_buffer_days + reorder_cycle

    units_needed = daily_demand * total_cover_days
    return units_needed * cogs_kzt


def compare_kaspi_vs_wb(
    kaspi_price_kzt: float,
    wb_price_rub: float,
    cogs_kzt: float,
    kaspi_delivery_fee: float = 856,  # Default tier 2
    fx_rub_kzt: float = DEFAULT_FX_RUB_KZT,
) -> dict:
    """
    Compare unit economics between Kaspi and WB.

    Args:
        kaspi_price_kzt: Kaspi selling price in KZT
        wb_price_rub: WB selling price in RUB
        cogs_kzt: COGS in KZT (same product)
        kaspi_delivery_fee: Kaspi delivery fee
        fx_rub_kzt: RUB to KZT exchange rate

    Returns:
        Dict with comparison metrics
    """
    try:
        from core.calc.economics import calc_net_rev
    except ModuleNotFoundError:
        from economics import calc_net_rev

    # Kaspi economics
    kaspi_net_rev = calc_net_rev(kaspi_price_kzt, kaspi_delivery_fee)
    kaspi_profit = kaspi_net_rev - cogs_kzt
    kaspi_margin = (kaspi_profit / kaspi_net_rev * 100) if kaspi_net_rev > 0 else 0

    # WB economics
    wb_econ = calc_wb_full_economics(wb_price_rub, cogs_kzt, fx_rub_kzt=fx_rub_kzt)

    return {
        "kaspi": {
            "price_kzt": kaspi_price_kzt,
            "net_rev_kzt": kaspi_net_rev,
            "profit_kzt": kaspi_profit,
            "margin_pct": kaspi_margin,
        },
        "wb": {
            "price_rub": wb_price_rub,
            "price_kzt_equiv": wb_price_rub * fx_rub_kzt,
            "net_rev_kzt": wb_econ.final_revenue_kzt,
            "profit_kzt": wb_econ.profit_kzt,
            "margin_pct": wb_econ.margin_pct,
        },
        "diff": {
            "profit_diff_kzt": wb_econ.profit_kzt - kaspi_profit,
            "margin_diff_pct": wb_econ.margin_pct - kaspi_margin,
            "winner": "WB" if wb_econ.profit_kzt > kaspi_profit else "Kaspi",
        },
    }


if __name__ == "__main__":
    print("WB Economics Module Test Values")
    print("=" * 60)

    # Test LINE52 @ 2,800₽
    print("\nLINE52 (COGS=5,285 KZT) @ 2,800₽:")
    cogs_line52 = 5285

    econ = calc_wb_full_economics(2800, cogs_line52)
    print(f"  Commission: {econ.commission_rub:.2f}₽ (24.5%)")
    print(f"  Logistics:  {econ.logistics_fee_rub:.2f}₽")
    print(f"  Net RUB:    {econ.net_revenue_rub:.2f}₽")
    print(f"  Net KZT:    {econ.final_revenue_kzt:.2f} KZT")
    print(f"  Profit:     {econ.profit_kzt:.2f} KZT")
    print(f"  Margin:     {econ.margin_pct:.1f}%")

    # Test breakeven prices
    print("\nBreakeven prices for LINE52:")
    for margin in [0, 20, 40, 50]:
        price = calc_wb_breakeven_price(cogs_line52, target_margin_pct=margin)
        print(f"  {margin}% margin: {price:.0f}₽")

    # Test capital requirements
    print("\nCapital requirements (D=12/day):")
    capital = calc_wb_capital_required(360, cogs_line52)  # 360 = 12 * 30
    print(f"  WB capital needed: {capital:,.0f} KZT ({capital / 1000000:.2f}M)")

    # Compare Kaspi vs WB
    print("\nKaspi vs WB comparison (LINE52):")
    comp = compare_kaspi_vs_wb(
        kaspi_price_kzt=12000, wb_price_rub=2800, cogs_kzt=cogs_line52
    )
    print(f"  Kaspi @ 12,000 KZT:")
    print(f"    Net Rev: {comp['kaspi']['net_rev_kzt']:,.0f} KZT")
    print(f"    Profit:  {comp['kaspi']['profit_kzt']:,.0f} KZT")
    print(f"    Margin:  {comp['kaspi']['margin_pct']:.1f}%")
    print(f"  WB @ 2,800₽:")
    print(f"    Net Rev: {comp['wb']['net_rev_kzt']:,.0f} KZT")
    print(f"    Profit:  {comp['wb']['profit_kzt']:,.0f} KZT")
    print(f"    Margin:  {comp['wb']['margin_pct']:.1f}%")
    print(f"  Winner: {comp['diff']['winner']} (+{abs(comp['diff']['profit_diff_kzt']):,.0f} KZT)")

    print("\n" + "=" * 60)
    print("All calculations complete!")
