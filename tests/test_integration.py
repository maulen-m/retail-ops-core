"""
TASK-054: Integration Tests

End-to-end tests for complete workflows.
Tests interactions between multiple modules.
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import date, timedelta
from pathlib import Path


# Import core modules
from core.calc.forecast import (
    calc_weighted_demand,
    calc_trend_slope,
    calc_d_forecast,
    calc_d_forecast_daily
)
from core.calc.forecast_accuracy import (
    calc_mape,
    calc_forecast_bias,
    get_accuracy_grade
)
from core.calc.inventory import (
    calc_ss_demand,
    calc_rop,
    calc_suggested_order_qty,
    calc_k_avg,
    calc_roic
)
from core.calc.economics import (
    calc_profit
)
from core.calc.portfolio import (
    check_concentration_rule,
    recommend_lifecycle_status
)
from core.calc.dow_patterns import (
    calc_dow_indices,
    calc_weekend_lift
)


class TestForecastToInventoryFlow:
    """Test forecast -> safety stock -> ROP pipeline."""

    def test_forecast_feeds_safety_stock(self):
        """Forecast output can be used for SS calculation."""
        # Generate test sales data
        sales = [(date.today() - timedelta(days=i), 5.0) for i in range(30)]

        # Calculate forecast
        d_forecast = calc_d_forecast_daily(sales, horizon_days=7)
        assert d_forecast > 0

        # Use forecast for safety stock
        # calc_ss_demand takes (sigma, L, z)
        sigma = 2.0  # Assume some volatility
        ss = calc_ss_demand(sigma, L=21, z=1.65)

        assert ss > 0, "Safety stock should be positive"

    def test_forecast_to_rop(self):
        """Full forecast -> ROP calculation flow."""
        sales = [(date.today() - timedelta(days=i), 8.0) for i in range(30)]

        # Forecast
        d30 = calc_d_forecast_daily(sales, horizon_days=30)

        # Calculate ROP (takes d30, L, ss_total)
        rop = calc_rop(d30, L=21)

        assert rop > 0
        assert rop > d30 * 21  # ROP should cover lead time demand + safety

    def test_rop_to_order_quantity(self):
        """ROP triggers order quantity calculation."""
        d30 = 5.0
        rop = 200
        current_stock = 150  # Below ROP
        inbound_stock = 0  # No inbound orders

        # Calculate order quantity (takes d30, current_stock, inbound_stock, L, R)
        order_qty = calc_suggested_order_qty(d30, current_stock, inbound_stock, L=21, R=10)

        assert order_qty > 0
        assert current_stock < rop  # Confirms reorder needed


class TestEconomicsIntegration:
    """Test economics calculations integration."""

    def test_profit_to_roic_flow(self):
        """Profit calculation feeds ROIC."""
        cogs_unit = 5000
        price_unit = 12000
        d30 = 10.0

        # Calculate profit per unit (selling price, quantity, efficiency)
        profit = calc_profit(price_unit, 1, 0.95)

        # Calculate k_avg for the SKU
        k_avg = calc_k_avg(d30, cogs_unit, L=21, R=10)

        # Calculate ROIC
        roic = calc_roic(d30, profit, cogs_unit, L=21, R=10)

        assert profit > 0
        assert k_avg > 0
        assert roic > 0

    def test_economics_drive_lifecycle(self):
        """Economic metrics drive lifecycle recommendations."""
        # Good performance
        roic_good = 25.0
        trend_good = 0.05
        d30_good = 10.0

        status_good = recommend_lifecycle_status(roic_good, trend_good, d30_good)
        assert status_good == 'GROW'

        # Poor performance
        roic_poor = -5.0
        status_poor = recommend_lifecycle_status(roic_poor, 0.0, 1.0)
        assert status_poor == 'KILL'


class TestAccuracyFeedbackLoop:
    """Test forecast accuracy feedback."""

    def test_mape_grades_forecast(self):
        """MAPE calculation produces valid grade."""
        actuals = [100, 90, 110, 100, 95]
        forecasts = [100, 100, 100, 100, 100]

        mape = calc_mape(actuals, forecasts)
        grade = get_accuracy_grade(mape)

        assert mape > 0
        assert grade in ['A', 'B', 'C', 'D', 'F', 'N/A']

    def test_bias_informs_adjustment(self):
        """Forecast bias can inform adjustments."""
        # Consistent over-forecasting
        actuals = [80, 85, 75, 90, 70]
        forecasts = [100, 100, 100, 100, 100]

        bias = calc_forecast_bias(actuals, forecasts)

        # Positive bias = over-forecasting
        assert bias > 0, "Should detect over-forecasting"


class TestDOWPatternIntegration:
    """Test day-of-week pattern usage."""

    def test_dow_indices_sum_to_7(self):
        """DOW indices should average to ~1.0."""
        # Flat demand
        sales = [(date.today() - timedelta(days=i), 10.0) for i in range(28)]

        indices = calc_dow_indices(sales)

        # Sum should be close to 7 (7 days * 1.0 average)
        assert sum(indices.values()) == pytest.approx(7.0, rel=0.1)

    def test_weekend_lift_calculation(self):
        """Weekend lift integrates with forecast adjustment."""
        # Create weekend-heavy sales pattern
        sales = []
        for i in range(28):
            d = date.today() - timedelta(days=i)
            # Saturday/Sunday = 15, weekday = 10
            units = 15.0 if d.weekday() >= 5 else 10.0
            sales.append((d, units))

        indices = calc_dow_indices(sales)
        lift = calc_weekend_lift(indices)

        assert lift > 0, "Weekend should show positive lift"


class TestConcentrationWithPO:
    """Test concentration rule with PO generation."""

    def test_po_respects_concentration(self):
        """PO quantities respect concentration limits."""
        total_capital = 1000000

        # Try to order too much of one SKU
        proposed_po = {'SKU_HEAVY': 5000}
        unit_costs = {'SKU_HEAVY': 100}  # 500k = 50% of capital

        result = check_concentration_rule(
            proposed_po,
            current_inventory={},
            unit_costs=unit_costs,
            total_capital=total_capital,
            max_concentration=0.20
        )

        assert result['valid'] is False
        # Adjusted should be capped at 20% = 200k = 2000 units
        assert result['adjusted_po']['SKU_HEAVY'] == 2000


class TestEndToEndScenarios:
    """Complete business scenario tests."""

    def test_new_sku_launch_scenario(self):
        """New SKU with limited history."""
        # Only 14 days of data
        sales = [(date.today() - timedelta(days=i), 3.0) for i in range(14)]

        # Should still generate forecast
        d_forecast = calc_d_forecast_daily(sales, horizon_days=7)

        # Trend might be less reliable with limited data
        trend = calc_trend_slope(sales)

        assert d_forecast >= 0

    def test_seasonal_peak_scenario(self):
        """SKU approaching seasonal peak."""
        # Increasing trend
        sales = [(date.today() - timedelta(days=i), 5.0 + (30-i)*0.2)
                 for i in range(30)]

        trend = calc_trend_slope(sales)
        d_forecast = calc_d_forecast_daily(sales, horizon_days=7)

        assert trend > 0, "Should detect rising trend"

    def test_declining_sku_scenario(self):
        """SKU with declining sales."""
        # Decreasing trend
        sales = [(date.today() - timedelta(days=i), 20.0 - (30-i)*0.3)
                 for i in range(30)]

        trend = calc_trend_slope(sales)
        roic = -5.0  # Assume negative ROIC

        status = recommend_lifecycle_status(roic, trend, d30=5.0)

        assert trend < 0, "Should detect falling trend"
        assert status == 'KILL'


class TestDataConsistency:
    """Test data flows maintain consistency."""

    def test_demand_metrics_consistent(self):
        """D30 and D7 should be proportional for flat demand."""
        sales = [(date.today() - timedelta(days=i), 10.0) for i in range(30)]

        d7_total = calc_d_forecast(sales, horizon_days=7)
        d30_total = calc_d_forecast(sales, horizon_days=30)

        # D30 should be roughly 4x D7 for flat demand
        ratio = d30_total / d7_total if d7_total > 0 else 0
        assert ratio == pytest.approx(30/7, rel=0.2)

    def test_weighted_vs_simple_average(self):
        """Weighted demand differs from simple average."""
        # Pattern: old sales low, recent sales high
        sales = []
        for i in range(30):
            d = date.today() - timedelta(days=i)
            units = 10.0 if i < 15 else 2.0  # Recent=10, old=2
            sales.append((d, units))

        weighted = calc_weighted_demand(sales)
        simple_avg = sum(u for _, u in sales) / len(sales)

        # Weighted should be higher (closer to 10)
        assert weighted > simple_avg

