"""
Tests for WB economics calculations.

Test values based on WB_policy_v4.md:
- Commission: 24.5%
- Logistics: 408₽ (weighted avg for Line52/Line51)
- Tax: 3%
- FX: RUB/KZT = 6.6

LINE52 COGS: 5,285 KZT
LINE51 COGS: 6,689 KZT
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.wb_economics import (
    calc_wb_net_revenue,
    calc_wb_profit,
    calc_wb_full_economics,
    calc_wb_breakeven_price,
    calc_wb_margin,
    calc_wb_roic,
    calc_wb_capital_required,
    compare_kaspi_vs_wb,
    WBEconomics,
    WB_COMMISSION_PCT,
    WB_LOGISTICS_FEE_RUB,
    WB_TAX_PCT,
    DEFAULT_FX_RUB_KZT,
)


# Test data
LINE52_COGS = 5285
LINE51_COGS = 6689


class TestWBNetRevenue:
    """Tests for calc_wb_net_revenue."""

    def test_basic_calculation(self):
        """Test basic net revenue calculation at 2,800₽."""
        net_rub, net_kzt = calc_wb_net_revenue(2800)

        # Commission: 2800 * 0.245 = 686
        # After commission: 2800 - 686 = 2114
        # After logistics: 2114 - 408 = 1706
        assert net_rub == pytest.approx(1706, rel=0.01)

        # KZT: 1706 * 6.6 = 11259.6
        # After 3% tax: 11259.6 * 0.97 = 10921.812
        assert net_kzt == pytest.approx(10921.81, rel=0.01)

    def test_zero_price(self):
        """Test with zero price."""
        net_rub, net_kzt = calc_wb_net_revenue(0)
        # 0 - 408 = -408 RUB
        assert net_rub == -408

    def test_custom_fx_rate(self):
        """Test with custom FX rate."""
        _, net_kzt_default = calc_wb_net_revenue(2800)
        _, net_kzt_higher = calc_wb_net_revenue(2800, fx_rub_kzt=7.0)

        assert net_kzt_higher > net_kzt_default

    def test_custom_logistics_fee(self):
        """Test with custom logistics fee."""
        net_rub_default, _ = calc_wb_net_revenue(2800)
        net_rub_lower, _ = calc_wb_net_revenue(2800, logistics_fee_rub=300)

        assert net_rub_lower > net_rub_default


class TestWBProfit:
    """Tests for calc_wb_profit."""

    def test_line52_at_2800(self):
        """Test LINE52 profit at 2,800₽."""
        profit = calc_wb_profit(2800, LINE52_COGS)

        # Net KZT: ~10,922 (from net revenue test)
        # Profit: 10,922 - 5,285 = 5,637
        assert profit == pytest.approx(5637, rel=0.02)

    def test_line51_at_3000(self):
        """Test LINE51 profit at 3,000₽."""
        profit = calc_wb_profit(3000, LINE51_COGS)

        # Higher price but higher COGS
        assert profit > 0  # Should still be profitable

    def test_breakeven_price(self):
        """Test that breakeven price yields ~0 profit."""
        breakeven = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=0)
        profit = calc_wb_profit(breakeven, LINE52_COGS)

        assert abs(profit) < 100  # Close to zero

    def test_negative_profit_low_price(self):
        """Test that very low price yields negative profit."""
        profit = calc_wb_profit(1000, LINE52_COGS)
        assert profit < 0


class TestWBFullEconomics:
    """Tests for calc_wb_full_economics."""

    def test_returns_dataclass(self):
        """Test that function returns WBEconomics dataclass."""
        result = calc_wb_full_economics(2800, LINE52_COGS)
        assert isinstance(result, WBEconomics)

    def test_commission_calculation(self):
        """Test commission is calculated correctly."""
        result = calc_wb_full_economics(2800, LINE52_COGS)

        expected_commission = 2800 * (WB_COMMISSION_PCT / 100)
        assert result.commission_rub == pytest.approx(expected_commission, rel=0.01)

    def test_logistics_fee_included(self):
        """Test logistics fee is included."""
        result = calc_wb_full_economics(2800, LINE52_COGS)
        assert result.logistics_fee_rub == WB_LOGISTICS_FEE_RUB

    def test_margin_calculation(self):
        """Test margin percentage."""
        result = calc_wb_full_economics(2800, LINE52_COGS)

        # Margin = profit / net_revenue * 100
        expected_margin = (result.profit_kzt / result.final_revenue_kzt * 100)
        assert result.margin_pct == pytest.approx(expected_margin, rel=0.01)

    def test_all_fields_populated(self):
        """Test all fields are populated."""
        result = calc_wb_full_economics(2800, LINE52_COGS)

        assert result.seller_price_rub > 0
        assert result.gross_revenue_rub > 0
        assert result.commission_rub > 0
        assert result.net_revenue_rub > 0
        assert result.net_revenue_kzt > 0
        assert result.tax_kzt > 0
        assert result.final_revenue_kzt > 0


class TestWBBreakevenPrice:
    """Tests for calc_wb_breakeven_price."""

    def test_breakeven_line52(self):
        """Test breakeven price for LINE52."""
        price = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=0)

        # Verify by calculating profit at this price
        profit = calc_wb_profit(price, LINE52_COGS)
        assert abs(profit) < 100  # Should be close to zero

    def test_target_margin_40(self):
        """Test price for 40% target margin."""
        price = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=40)

        margin = calc_wb_margin(price, LINE52_COGS)
        assert margin == pytest.approx(40, rel=0.05)

    def test_target_margin_50(self):
        """Test price for 50% target margin."""
        price = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=50)

        margin = calc_wb_margin(price, LINE52_COGS)
        assert margin == pytest.approx(50, rel=0.05)

    def test_higher_cogs_higher_price(self):
        """Test that higher COGS requires higher price."""
        price_line52 = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=40)
        price_line51 = calc_wb_breakeven_price(LINE51_COGS, target_margin_pct=40)

        assert price_line51 > price_line52


class TestWBMargin:
    """Tests for calc_wb_margin."""

    def test_line52_margin_at_2800(self):
        """Test LINE52 margin at 2,800₽."""
        margin = calc_wb_margin(2800, LINE52_COGS)

        # From WB_policy_v4.md, expected ~50%+ margin at this price
        assert margin > 45
        assert margin < 60

    def test_margin_at_breakeven(self):
        """Test margin at breakeven price is ~0%."""
        price = calc_wb_breakeven_price(LINE52_COGS, target_margin_pct=0)
        margin = calc_wb_margin(price, LINE52_COGS)

        assert abs(margin) < 5  # Close to zero

    def test_negative_margin(self):
        """Test that very low price yields negative margin."""
        margin = calc_wb_margin(1000, LINE52_COGS)
        assert margin < 0


class TestWBRoic:
    """Tests for calc_wb_roic."""

    def test_basic_roic(self):
        """Test basic ROIC calculation."""
        profit_30d = 500_000  # 500K KZT
        capital = 1_000_000  # 1M KZT

        roic = calc_wb_roic(profit_30d, capital, annualize=True)

        # 50% * 12.17 = 608.5% annualized
        assert roic == pytest.approx(608.5, rel=0.01)

    def test_non_annualized(self):
        """Test non-annualized ROIC."""
        profit_30d = 500_000
        capital = 1_000_000

        roic = calc_wb_roic(profit_30d, capital, annualize=False)

        # 50% monthly
        assert roic == pytest.approx(50, rel=0.01)

    def test_zero_capital(self):
        """Test ROIC with zero capital."""
        roic = calc_wb_roic(100000, 0)
        assert roic == 0

    def test_zero_profit(self):
        """Test ROIC with zero profit."""
        roic = calc_wb_roic(0, 1_000_000)
        assert roic == 0


class TestWBCapitalRequired:
    """Tests for calc_wb_capital_required."""

    def test_d12_per_day(self):
        """Test capital for D=12/day (360 units/30d)."""
        capital = calc_wb_capital_required(360, LINE52_COGS)

        # Lead time: 21 + 1 + 10 = 32 days
        # Safety: 14 days
        # Reorder: 10 days
        # Total: 56 days cover
        # Units: 12/day * 56 = 672 units
        # Capital: 672 * 5285 = 3,551,520 KZT

        assert capital == pytest.approx(3_551_520, rel=0.05)

    def test_zero_demand(self):
        """Test capital with zero demand."""
        capital = calc_wb_capital_required(0, LINE52_COGS)
        assert capital == 0


class TestKaspiVsWBComparison:
    """Tests for compare_kaspi_vs_wb."""

    def test_comparison_structure(self):
        """Test comparison returns expected structure."""
        result = compare_kaspi_vs_wb(
            kaspi_price_kzt=12000,
            wb_price_rub=2800,
            cogs_kzt=LINE52_COGS,
        )

        assert "kaspi" in result
        assert "wb" in result
        assert "diff" in result

    def test_kaspi_metrics_present(self):
        """Test Kaspi metrics are calculated."""
        result = compare_kaspi_vs_wb(12000, 2800, LINE52_COGS)

        assert result["kaspi"]["price_kzt"] == 12000
        assert result["kaspi"]["net_rev_kzt"] > 0
        assert result["kaspi"]["profit_kzt"] > 0
        assert result["kaspi"]["margin_pct"] > 0

    def test_wb_metrics_present(self):
        """Test WB metrics are calculated."""
        result = compare_kaspi_vs_wb(12000, 2800, LINE52_COGS)

        assert result["wb"]["price_rub"] == 2800
        assert result["wb"]["net_rev_kzt"] > 0
        assert result["wb"]["profit_kzt"] > 0
        assert result["wb"]["margin_pct"] > 0

    def test_winner_determined(self):
        """Test winner is determined."""
        result = compare_kaspi_vs_wb(12000, 2800, LINE52_COGS)

        assert result["diff"]["winner"] in ["Kaspi", "WB"]

    def test_wb_wins_at_good_price(self):
        """Test WB wins at favorable price point."""
        result = compare_kaspi_vs_wb(
            kaspi_price_kzt=12000,
            wb_price_rub=2800,
            cogs_kzt=LINE52_COGS,
        )

        # WB at 2,800₽ should have better margin than Kaspi at 12,000 KZT
        assert result["wb"]["profit_kzt"] > result["kaspi"]["profit_kzt"]
        assert result["diff"]["winner"] == "WB"


class TestConstants:
    """Tests for module constants."""

    def test_commission_rate(self):
        """Test commission rate matches WB_policy_v4.md."""
        assert WB_COMMISSION_PCT == 24.5

    def test_logistics_fee(self):
        """Test logistics fee matches WB_policy_v4.md."""
        assert WB_LOGISTICS_FEE_RUB == 408

    def test_tax_rate(self):
        """Test tax rate matches WB_policy_v4.md."""
        assert WB_TAX_PCT == 3.0

    def test_fx_rate(self):
        """Test default FX rate matches WB_policy_v4.md."""
        assert DEFAULT_FX_RUB_KZT == 6.6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
