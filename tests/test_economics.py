"""
Tests for core/calc/economics.py

Test values from TASK-009 requirements:
- LINE52 @ 12,000 KZT → COGS=5,005, NetRev=9,355, Profit=4,350
- LINE51 @ 12,000 KZT → COGS=6,019
"""

import pytest
from core.calc.economics import (
    calc_delivery_fee,
    calc_cogs,
    calc_net_rev,
    calc_profit,
    calc_line_values,
)


class TestDeliveryFee:
    """Tests for delivery fee calculation."""

    def test_free_delivery_under_5000(self):
        """Delivery is free for prices <= 4999."""
        assert calc_delivery_fee(4999) == 0.0
        assert calc_delivery_fee(3000) == 0.0
        assert calc_delivery_fee(0) == 0.0

    def test_low_tier_delivery_5000_to_15000(self):
        """Delivery is 856 for 5000 <= price <= 14999."""
        assert calc_delivery_fee(5000) == 856.0
        assert calc_delivery_fee(12000) == 856.0
        assert calc_delivery_fee(14999) == 856.0

    def test_high_tier_delivery_over_15000(self):
        """Delivery is 1259 for price > 14999."""
        assert calc_delivery_fee(15000) == 1259.0
        assert calc_delivery_fee(20000) == 1259.0
        assert calc_delivery_fee(50000) == 1259.0


class TestCogs:
    """Tests for COGS calculation."""

    def test_line52_cogs(self):
        """LINE52 COGS should be ~5,005."""
        # base_cost_cny=47, weight_kg=0.95
        cogs = calc_cogs(47, 0.95)
        assert abs(cogs - 5005) / 5005 < 0.01  # Within 1%

    def test_line51_cogs(self):
        """LINE51 COGS should be ~6,019."""
        # base_cost_cny=60, weight_kg=0.95
        cogs = calc_cogs(60, 0.95)
        assert abs(cogs - 6019) / 6019 < 0.01  # Within 1%

    def test_zero_weight(self):
        """Zero weight should only have product cost."""
        cogs = calc_cogs(47, 0)
        assert cogs == 47 * 78  # Just CNY conversion

    def test_zero_cost(self):
        """Zero base cost should only have freight."""
        cogs = calc_cogs(0, 0.95)
        expected = 0.95 * 2.66 * 530
        assert abs(cogs - expected) < 0.01

    def test_custom_rates(self):
        """Custom exchange rate and freight should work."""
        cogs = calc_cogs(47, 0.95, cny_kzt=80, freight_rate=500)
        expected = 47 * 80 + 0.95 * 2.66 * 500
        assert abs(cogs - expected) < 0.01


class TestNetRev:
    """Tests for net revenue calculation."""

    def test_net_rev_at_12000(self):
        """Net revenue at 12,000 KZT should be ~9,355."""
        net_rev = calc_net_rev(12000)
        assert abs(net_rev - 9355) / 9355 < 0.01  # Within 1%

    def test_net_rev_with_explicit_delivery(self):
        """Explicit delivery fee should override auto-calculation."""
        # With delivery=856: (12000 * 0.875 - 856) * 0.97
        net_rev = calc_net_rev(12000, delivery_fee=856)
        expected = (12000 * 0.875 - 856) * 0.97
        assert abs(net_rev - expected) < 0.01

    def test_net_rev_low_price(self):
        """Low price (free delivery) calculation."""
        # price=4000, delivery=0
        net_rev = calc_net_rev(4000)
        expected = (4000 * 0.875 - 0) * 0.97
        assert abs(net_rev - expected) < 0.01

    def test_net_rev_high_price(self):
        """High price (1259 delivery) calculation."""
        # price=20000, delivery=1259
        net_rev = calc_net_rev(20000)
        expected = (20000 * 0.875 - 1259) * 0.97
        assert abs(net_rev - expected) < 0.01


class TestProfit:
    """Tests for profit calculation."""

    def test_line52_profit_at_12000(self):
        """LINE52 profit at 12,000 should be ~4,350."""
        profit = calc_profit(12000, 47, 0.95)
        assert abs(profit - 4350) / 4350 < 0.01  # Within 1%

    def test_profit_with_precalculated_values(self):
        """Pre-calculated COGS and net_rev should be used."""
        profit = calc_profit(12000, 47, 0.95, cogs=5005, net_rev=9355)
        assert profit == 9355 - 5005

    def test_negative_profit(self):
        """Low price can result in negative profit."""
        # Very low price: 5000, high cost
        profit = calc_profit(5000, 100, 2.0)
        assert profit < 0


class TestLineValues:
    """Tests for line-level calculations."""

    def test_line_values_single_unit(self):
        """Single unit calculation should match individual functions."""
        result = calc_line_values(12000, 47, 0.95, 1)

        assert result["delivery_fee"] == 856.0
        assert abs(result["cogs_unit"] - 5005) < 1
        assert abs(result["net_rev_unit"] - 9355) < 1
        assert abs(result["profit_unit"] - 4350) < 1

        # Line values should equal unit values for qty=1
        assert result["cogs_line"] == result["cogs_unit"]
        assert result["line_net_rev"] == result["net_rev_unit"]
        assert result["profit_line"] == result["profit_unit"]

    def test_line_values_multiple_units(self):
        """Multiple units should multiply line values."""
        qty = 5
        result = calc_line_values(12000, 47, 0.95, qty)

        assert abs(result["cogs_line"] - result["cogs_unit"] * qty) < 0.01
        assert abs(result["line_net_rev"] - result["net_rev_unit"] * qty) < 0.01
        assert abs(result["profit_line"] - result["profit_unit"] * qty) < 0.01

    def test_line_values_zero_quantity(self):
        """Zero quantity should give zero line values."""
        result = calc_line_values(12000, 47, 0.95, 0)

        assert result["cogs_line"] == 0
        assert result["line_net_rev"] == 0
        assert result["profit_line"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
