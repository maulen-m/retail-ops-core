from __future__ import annotations

from pathlib import Path

from core.calc.economics import (
    GIFT_BAG_COST_CNY_PER_UNIT,
    GIFT_BAG_WEIGHT_KG_PER_UNIT,
    calc_cogs,
    resolve_landed_cogs,
)


def test_calc_cogs_can_include_internal_gift_bag_delta() -> None:
    plain = calc_cogs(
        base_cost_cny=50.0,
        weight_kg=1.0,
        cny_kzt=70.0,
        volumetric_factor=0.2,
        freight_rate=500.0,
    )
    with_gift_bag = calc_cogs(
        base_cost_cny=50.0,
        weight_kg=1.0,
        cny_kzt=70.0,
        volumetric_factor=0.2,
        freight_rate=500.0,
        include_gift_bag=True,
    )

    expected_delta = (GIFT_BAG_COST_CNY_PER_UNIT * 70.0) + (
        GIFT_BAG_WEIGHT_KG_PER_UNIT * 0.2 * 500.0
    )
    assert round(with_gift_bag - plain, 6) == round(expected_delta, 6)


def test_resolve_landed_cogs_labels_gift_bag_formula() -> None:
    value, basis, rates = resolve_landed_cogs(
        base_cost_cny=50.0,
        weight_kg=1.0,
        include_gift_bag=True,
    )

    assert value is not None
    assert basis == "formula_full_with_gift_bag"
    assert rates is not None


def test_review_only_po_export_surface_opts_into_gift_bag_cogs() -> None:
    source = Path("scripts/generate_po_dashboard_data.py").read_text(encoding="utf-8")

    assert "calc_cogs(base_cost_cny, weight_per_unit, include_gift_bag=True)" in source
    assert "calc_cogs(base_cost_cny, weight_kg, include_gift_bag=True)" in source
    assert "INTERNAL_GIFT_BAG_COGS_INCLUDED" in source
