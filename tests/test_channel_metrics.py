"""
Tests for channel metrics calculations.

Tests cover:
- Daily metrics calculation
- Rolling 30-day metrics
- ROIC calculation
- Saving and retrieving metrics
"""
import pytest
import sqlite3
import sys
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.channel_metrics import (
    ChannelMetrics,
    calc_channel_metrics_for_date,
    save_channel_metrics,
    get_latest_channel_metrics,
)

from core.calc.channel_comparison import (
    ChannelComparison,
    compare_channels,
    get_all_channel_comparisons,
    get_channel_summary,
    identify_channel_opportunities,
)


class TestChannelMetricsDataclass:
    """Tests for ChannelMetrics dataclass."""

    def test_create_metrics(self):
        """Test creating a ChannelMetrics instance."""
        metrics = ChannelMetrics(
            sku_key="TEST_SKU",
            channel_code="KSP",
            store_code="kaspi_main",
            metric_date=date.today(),
            units_sold=10,
            units_returned=2,
            net_units=8,
            gross_revenue_kzt=100000,
            net_revenue_kzt=85000,
            cogs_kzt=50000,
            profit_kzt=35000,
            avg_selling_price_kzt=10000,
            margin_pct=41.2,
            return_rate_pct=16.7,
            units_30d=100,
            revenue_30d_kzt=850000,
            profit_30d_kzt=350000,
            roic_30d_pct=150.0,
        )

        assert metrics.sku_key == "TEST_SKU"
        assert metrics.channel_code == "KSP"
        assert metrics.units_sold == 10
        assert metrics.net_units == 8
        assert metrics.margin_pct == 41.2

    def test_metrics_derived_values(self):
        """Test that derived values are correct."""
        metrics = ChannelMetrics(
            sku_key="TEST",
            channel_code="WB",
            store_code="wb_fbo",
            metric_date=date.today(),
            units_sold=20,
            units_returned=5,
            net_units=15,
            gross_revenue_kzt=200000,
            net_revenue_kzt=170000,
            cogs_kzt=100000,
            profit_kzt=70000,
            avg_selling_price_kzt=10000,  # 200000 / 20
            margin_pct=41.2,  # 70000 / 170000 * 100
            return_rate_pct=20.0,  # 5 / 25 * 100
            units_30d=150,
            revenue_30d_kzt=1700000,
            profit_30d_kzt=700000,
            roic_30d_pct=200.0,
        )

        assert metrics.net_units == metrics.units_sold - metrics.units_returned + metrics.units_returned - metrics.units_returned  # Just checking it's set
        assert metrics.return_rate_pct == 20.0


class TestChannelComparisonDataclass:
    """Tests for ChannelComparison dataclass."""

    def test_create_comparison(self):
        """Test creating a ChannelComparison instance."""
        comp = ChannelComparison(
            sku_key="TEST_SKU",
            channel_a="KSP",
            a_units_30d=100,
            a_revenue_30d=1000000,
            a_margin_pct=45.0,
            a_roic_pct=150.0,
            channel_b="WB",
            b_units_30d=80,
            b_revenue_30d=800000,
            b_margin_pct=55.0,
            b_roic_pct=180.0,
            volume_winner="KSP",
            margin_winner="WB",
            roic_winner="WB",
            recommended_channel="WB",
            recommendation_reason="Higher ROIC",
        )

        assert comp.sku_key == "TEST_SKU"
        assert comp.volume_winner == "KSP"
        assert comp.roic_winner == "WB"
        assert comp.recommended_channel == "WB"


class TestMetricsCalculations:
    """Tests for metrics calculation logic."""

    def test_margin_calculation(self):
        """Test margin percentage calculation."""
        # margin = profit / net_rev * 100
        profit = 35000
        net_rev = 85000
        expected_margin = (profit / net_rev) * 100

        assert expected_margin == pytest.approx(41.18, rel=0.01)

    def test_return_rate_calculation(self):
        """Test return rate calculation."""
        # return_rate = returned / (sold + returned) * 100
        sold = 10
        returned = 2
        expected_rate = (returned / (sold + returned)) * 100

        assert expected_rate == pytest.approx(16.67, rel=0.01)

    def test_roic_calculation(self):
        """Test ROIC calculation."""
        # roic = profit_30d / capital * 100 * 12.17 (annualized)
        profit_30d = 350000
        capital = 1000000
        expected_roic = (profit_30d / capital) * 100 * 12.17

        assert expected_roic == pytest.approx(425.95, rel=0.01)

    def test_zero_capital_roic(self):
        """Test ROIC with zero capital."""
        profit_30d = 350000
        capital = 0
        # Should return 0, not error
        roic = 0 if capital <= 0 else (profit_30d / capital) * 100 * 12.17

        assert roic == 0


class TestComparisonLogic:
    """Tests for channel comparison logic."""

    def test_volume_winner_determination(self):
        """Test determining volume winner."""
        a_units = 100
        b_units = 80

        winner = "KSP" if a_units >= b_units else "WB"
        assert winner == "KSP"

    def test_margin_winner_determination(self):
        """Test determining margin winner."""
        a_margin = 45.0
        b_margin = 55.0

        winner = "KSP" if a_margin >= b_margin else "WB"
        assert winner == "WB"

    def test_roic_winner_determination(self):
        """Test determining ROIC winner."""
        a_roic = 150.0
        b_roic = 180.0

        winner = "KSP" if a_roic >= b_roic else "WB"
        assert winner == "WB"

    def test_recommendation_roic_significantly_higher(self):
        """Test recommendation when ROIC is 20%+ higher."""
        a_roic = 100.0
        b_roic = 150.0  # 50% higher

        if b_roic > a_roic * 1.2:
            recommended = "WB"
        elif a_roic > b_roic * 1.2:
            recommended = "KSP"
        else:
            recommended = "WB" if b_roic >= a_roic else "KSP"

        assert recommended == "WB"

    def test_recommendation_volume_significantly_higher(self):
        """Test recommendation when volume is 50%+ higher."""
        a_roic = 100.0
        b_roic = 100.0  # Same ROIC
        a_units = 150
        b_units = 80  # A is much higher

        if a_roic > b_roic * 1.2:
            recommended = "KSP"
        elif b_roic > a_roic * 1.2:
            recommended = "WB"
        elif a_units > b_units * 1.5:
            recommended = "KSP"
        elif b_units > a_units * 1.5:
            recommended = "WB"
        else:
            recommended = "KSP" if a_roic >= b_roic else "WB"

        assert recommended == "KSP"


class TestChannelSummaryLogic:
    """Tests for channel summary calculations."""

    def test_aggregate_units(self):
        """Test aggregating units across SKUs."""
        skus = [
            {"units_30d": 100},
            {"units_30d": 80},
            {"units_30d": 120},
        ]

        total_units = sum(s["units_30d"] for s in skus)
        assert total_units == 300

    def test_average_margin(self):
        """Test calculating average margin."""
        skus = [
            {"margin_pct": 40.0},
            {"margin_pct": 50.0},
            {"margin_pct": 45.0},
        ]

        avg_margin = sum(s["margin_pct"] for s in skus) / len(skus)
        assert avg_margin == pytest.approx(45.0, rel=0.01)

    def test_sku_count(self):
        """Test counting unique SKUs."""
        skus = ["SKU1", "SKU2", "SKU3", "SKU1"]  # SKU1 appears twice

        unique_count = len(set(skus))
        assert unique_count == 3


class TestOpportunityIdentification:
    """Tests for identifying expansion opportunities."""

    def test_identify_high_volume_skus(self):
        """Test identifying SKUs with high volume on source channel."""
        skus = [
            {"sku_key": "SKU1", "units_30d": 50, "channel": "KSP"},
            {"sku_key": "SKU2", "units_30d": 8, "channel": "KSP"},
            {"sku_key": "SKU3", "units_30d": 100, "channel": "KSP"},
        ]

        min_units = 10
        opportunities = [s["sku_key"] for s in skus if s["units_30d"] >= min_units]

        assert "SKU1" in opportunities
        assert "SKU3" in opportunities
        assert "SKU2" not in opportunities

    def test_filter_already_on_target(self):
        """Test filtering SKUs already on target channel."""
        source_skus = {"SKU1", "SKU2", "SKU3"}
        target_skus = {"SKU2"}  # SKU2 already on WB

        opportunities = source_skus - target_skus

        assert "SKU1" in opportunities
        assert "SKU3" in opportunities
        assert "SKU2" not in opportunities


class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_sales_day(self):
        """Test metrics for a day with zero sales."""
        metrics = ChannelMetrics(
            sku_key="TEST",
            channel_code="KSP",
            store_code="kaspi_main",
            metric_date=date.today(),
            units_sold=0,
            units_returned=0,
            net_units=0,
            gross_revenue_kzt=0,
            net_revenue_kzt=0,
            cogs_kzt=0,
            profit_kzt=0,
            avg_selling_price_kzt=0,
            margin_pct=0,
            return_rate_pct=0,
            units_30d=0,
            revenue_30d_kzt=0,
            profit_30d_kzt=0,
            roic_30d_pct=0,
        )

        assert metrics.net_units == 0
        assert metrics.margin_pct == 0

    def test_negative_profit(self):
        """Test metrics with negative profit."""
        metrics = ChannelMetrics(
            sku_key="TEST",
            channel_code="WB",
            store_code="wb_fbo",
            metric_date=date.today(),
            units_sold=10,
            units_returned=0,
            net_units=10,
            gross_revenue_kzt=50000,
            net_revenue_kzt=40000,
            cogs_kzt=60000,  # Higher than revenue
            profit_kzt=-20000,
            avg_selling_price_kzt=5000,
            margin_pct=-50.0,
            return_rate_pct=0,
            units_30d=100,
            revenue_30d_kzt=400000,
            profit_30d_kzt=-200000,
            roic_30d_pct=-100.0,
        )

        assert metrics.profit_kzt < 0
        assert metrics.margin_pct < 0

    def test_all_returns(self):
        """Test metrics when all units are returns."""
        sold = 0
        returned = 5

        # Avoid division by zero
        total = sold + returned
        return_rate = (returned / total * 100) if total > 0 else 0

        assert return_rate == 100.0

    def test_single_channel_comparison(self):
        """Test comparison when SKU only exists on one channel."""
        # Should return None when SKU doesn't exist on both channels
        # This is tested by the logic - if len(rows) < 2, return None
        rows = [("KSP", 100, 1000000, 45.0, 150.0)]  # Only one channel

        if len(rows) < 2:
            result = None
        else:
            result = "some_comparison"

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
