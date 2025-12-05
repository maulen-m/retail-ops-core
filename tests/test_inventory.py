"""
Tests for core/calc/inventory.py

Tests inventory calculations against expected formulas.
"""

import pytest
import math
from core.calc.inventory import (
    calc_d30,
    calc_sigma,
    calc_ss_demand,
    calc_ss_floor,
    calc_ss_mix,
    calc_ss_total,
    calc_rop,
    calc_k_avg,
    calc_roic,
    calc_suggested_order_qty,
    calc_all_metrics,
    DEFAULT_PARAMS,
)


class TestD30:
    """Tests for daily demand calculation."""

    def test_standard_30_days(self):
        """Standard 30-day period calculation."""
        assert calc_d30(150, 30) == 5.0
        assert calc_d30(300, 30) == 10.0

    def test_different_period(self):
        """Non-30-day periods."""
        assert calc_d30(100, 10) == 10.0
        assert calc_d30(60, 60) == 1.0

    def test_zero_period(self):
        """Zero period should return 0, not error."""
        assert calc_d30(100, 0) == 0.0

    def test_zero_sales(self):
        """Zero sales should return 0."""
        assert calc_d30(0, 30) == 0.0


class TestSigma:
    """Tests for volatility calculation."""

    def test_default_factor(self):
        """Default volatility factor is 0.4."""
        assert calc_sigma(5.0) == 2.0
        assert calc_sigma(10.0) == 4.0

    def test_custom_factor(self):
        """Custom volatility factor."""
        assert calc_sigma(5.0, 0.5) == 2.5

    def test_zero_d30(self):
        """Zero demand should give zero volatility."""
        assert calc_sigma(0.0) == 0.0


class TestSafetyStockComponents:
    """Tests for individual safety stock components."""

    def test_ss_demand_formula(self):
        """SS_demand = z × sigma × sqrt(L)."""
        sigma = 2.0
        L = 21
        z = 1.65
        expected = z * sigma * math.sqrt(L)
        assert abs(calc_ss_demand(sigma, L, z) - expected) < 0.01

    def test_ss_floor_formula(self):
        """SS_floor = D30 × B."""
        d30 = 5.0
        B = 14
        assert calc_ss_floor(d30, B) == d30 * B

    def test_ss_mix_formula(self):
        """SS_mix = TV × D30 × L."""
        d30 = 5.0
        L = 21
        TV = 0.23
        assert abs(calc_ss_mix(d30, L, TV) - TV * d30 * L) < 0.01


class TestSSTotal:
    """Tests for total safety stock calculation."""

    def test_ss_total_with_default_params(self):
        """SS_total should be sum of components with defaults."""
        d30 = 5.0
        sigma = calc_sigma(d30)

        # Calculate expected using formulas
        ss_demand = DEFAULT_PARAMS["z"] * sigma * math.sqrt(DEFAULT_PARAMS["L"])
        ss_floor = d30 * DEFAULT_PARAMS["B"]
        ss_mix = DEFAULT_PARAMS["TV"] * d30 * DEFAULT_PARAMS["L"]
        expected = ss_demand + ss_floor + ss_mix

        actual = calc_ss_total(d30)
        assert abs(actual - expected) < 0.01

    def test_ss_total_with_explicit_sigma(self):
        """SS_total with explicitly provided sigma."""
        d30 = 5.0
        sigma = 3.0  # Custom sigma, not d30 * 0.4

        actual = calc_ss_total(d30, sigma=sigma)

        # ss_demand should use custom sigma
        expected_ss_demand = DEFAULT_PARAMS["z"] * sigma * math.sqrt(DEFAULT_PARAMS["L"])
        assert actual > calc_ss_total(d30)  # Higher sigma = higher SS

    def test_ss_total_zero_d30(self):
        """Zero demand should give zero safety stock."""
        assert calc_ss_total(0.0) == 0.0


class TestROP:
    """Tests for reorder point calculation."""

    def test_rop_formula(self):
        """ROP = D30 × L + SS_total."""
        d30 = 5.0
        L = DEFAULT_PARAMS["L"]
        ss_total = calc_ss_total(d30)

        expected = d30 * L + ss_total
        actual = calc_rop(d30)

        assert abs(actual - expected) < 0.01

    def test_rop_with_precomputed_ss(self):
        """ROP with pre-calculated SS_total."""
        d30 = 5.0
        ss_total = 100.0

        actual = calc_rop(d30, ss_total=ss_total)
        expected = d30 * DEFAULT_PARAMS["L"] + ss_total

        assert abs(actual - expected) < 0.01


class TestKAvg:
    """Tests for average capital calculation."""

    def test_k_avg_formula(self):
        """K_avg = [D30 × (L + R/2) + SS_total] × COGS."""
        d30 = 5.0
        cogs = 5005
        L = DEFAULT_PARAMS["L"]
        R = DEFAULT_PARAMS["R"]
        ss_total = calc_ss_total(d30)

        expected = (d30 * (L + R / 2) + ss_total) * cogs
        actual = calc_k_avg(d30, cogs)

        assert abs(actual - expected) < 1  # Within 1 KZT


class TestROIC:
    """Tests for return on invested capital calculation."""

    def test_roic_formula(self):
        """ROIC = (Profit × D30 × 30) / K_avg × 100."""
        d30 = 5.0
        profit = 4350
        cogs = 5005

        k_avg = calc_k_avg(d30, cogs)
        expected = (profit * d30 * 30) / k_avg * 100
        actual = calc_roic(d30, profit, cogs)

        assert abs(actual - expected) < 0.1

    def test_roic_zero_k_avg(self):
        """Zero K_avg should return 0, not error."""
        # Zero D30 and zero SS means zero K_avg
        assert calc_roic(0, 4350, 5005) == 0.0

    def test_roic_positive(self):
        """ROIC should be positive for profitable SKU."""
        roic = calc_roic(5.0, 4350, 5005)
        assert roic > 0


class TestSuggestedOrderQty:
    """Tests for suggested order quantity calculation."""

    def test_basic_order_qty(self):
        """Basic order quantity calculation."""
        d30 = 5.0
        current = 50
        inbound = 0
        ss_total = calc_ss_total(d30)

        qty = calc_suggested_order_qty(d30, current, inbound, ss_total=ss_total)

        # Target = D30 × (L + R) + SS_total
        target = d30 * (DEFAULT_PARAMS["L"] + DEFAULT_PARAMS["R"]) + ss_total
        expected = max(0, math.ceil(target - current - inbound))

        assert qty == expected

    def test_no_order_needed(self):
        """High stock should give zero order qty."""
        d30 = 5.0
        current = 500  # Very high stock
        inbound = 0

        qty = calc_suggested_order_qty(d30, current, inbound)
        assert qty == 0

    def test_inbound_reduces_order(self):
        """Inbound stock should reduce suggested order."""
        d30 = 5.0
        current = 50

        qty_no_inbound = calc_suggested_order_qty(d30, current, 0)
        qty_with_inbound = calc_suggested_order_qty(d30, current, 100)

        assert qty_with_inbound < qty_no_inbound


class TestAllMetrics:
    """Tests for combined metrics calculation."""

    def test_all_metrics_keys(self):
        """calc_all_metrics should return all expected keys."""
        metrics = calc_all_metrics(5.0, 5005, 4350)

        expected_keys = {
            "d30", "sigma", "ss_demand", "ss_floor", "ss_mix", "ss_total",
            "rop", "k_avg", "roic_monthly", "target_stock"
        }
        assert set(metrics.keys()) == expected_keys

    def test_all_metrics_consistency(self):
        """Metrics should be internally consistent."""
        metrics = calc_all_metrics(5.0, 5005, 4350)

        # SS_total should equal sum of components
        expected_ss = metrics["ss_demand"] + metrics["ss_floor"] + metrics["ss_mix"]
        assert abs(metrics["ss_total"] - expected_ss) < 0.01

        # ROP should match formula
        expected_rop = metrics["d30"] * DEFAULT_PARAMS["L"] + metrics["ss_total"]
        assert abs(metrics["rop"] - expected_rop) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
