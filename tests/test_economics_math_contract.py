from __future__ import annotations

from core.calc.economics import calc_cogs, calc_net_rev, calc_profit


def test_calc_net_rev_matches_v8_formula_with_explicit_inputs() -> None:
    value = calc_net_rev(
        sell_price_kzt=10000.0,
        delivery_fee=1000.0,
        commission_rate=0.125,
        vat_rate=0.04,
        ads_cost_unit=50.0,
    )
    expected = ((10000.0 * (1.0 - 0.125) - 1000.0) * (1.0 - 0.04)) - 50.0
    assert round(value, 6) == round(expected, 6)


def test_calc_cogs_matches_v8_formula() -> None:
    value = calc_cogs(
        base_cost_cny=50.0,
        weight_kg=1.0,
        cny_kzt=70.0,
        volumetric_factor=0.2,
        freight_rate=500.0,
    )
    expected = (50.0 * 70.0) + (1.0 * 0.2 * 500.0)
    assert round(value, 6) == round(expected, 6)


def test_calc_profit_is_net_rev_minus_cogs() -> None:
    profit = calc_profit(
        sell_price_kzt=12000.0,
        base_cost_cny=40.0,
        weight_kg=0.8,
        delivery_fee=800.0,
        ads_cost_unit=100.0,
        vat_rate=0.04,
    )
    net_rev = calc_net_rev(
        sell_price_kzt=12000.0,
        delivery_fee=800.0,
        vat_rate=0.04,
        ads_cost_unit=100.0,
    )
    cogs = calc_cogs(base_cost_cny=40.0, weight_kg=0.8)
    assert round(profit, 6) == round(net_rev - cogs, 6)
