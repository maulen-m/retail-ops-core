"""
Tests for capital allocation optimizer.

TASK-081
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.capital_optimizer import (
    optimize_allocation,
    calc_portfolio_impact,
    check_concentration_rule
)


class TestOptimizeAllocation:
    """Tests for optimize_allocation function."""

    def test_kills_low_roic_skus(self):
        """SKUs with ROIC < 5% should be killed."""
        allocations = [
            {'sku_key': 'HIGH', 'capital': 100000, 'roic': 25.0, 'share': 50, 'lifecycle': 'GROW'},
            {'sku_key': 'LOW', 'capital': 100000, 'roic': 3.0, 'share': 50, 'lifecycle': 'UNKNOWN'},
        ]

        result = optimize_allocation(allocations, kill_roic_threshold=5.0)

        killed = [r for r in result if r.action == 'KILL']
        assert len(killed) == 1
        assert killed[0].sku_key == 'LOW'
        assert killed[0].recommended_capital == 0

    def test_respects_concentration_limit(self):
        """SKUs over concentration limit should be decreased."""
        allocations = [
            {'sku_key': 'A', 'capital': 500000, 'roic': 30.0, 'share': 50, 'lifecycle': 'GROW'},
            {'sku_key': 'B', 'capital': 500000, 'roic': 15.0, 'share': 50, 'lifecycle': 'MAINTAIN'},
        ]

        result = optimize_allocation(allocations, max_concentration=0.20)

        # Both start at 50% concentration, both should be decreased to 20%
        a = next(r for r in result if r.sku_key == 'A')
        b = next(r for r in result if r.sku_key == 'B')

        # Both should be capped at 20% of budget (200000 each)
        assert a.recommended_capital == 200000
        assert b.recommended_capital == 200000
        assert a.action == 'DECREASE'
        assert b.action == 'DECREASE'

    def test_reallocates_to_top_performers(self):
        """Capital from killed SKUs should go to high-ROIC SKUs."""
        # Use smaller starting amounts so concentration limit doesn't trigger
        allocations = [
            {'sku_key': 'STAR', 'capital': 10000, 'roic': 40.0, 'share': 5, 'lifecycle': 'GROW'},
            {'sku_key': 'OK', 'capital': 10000, 'roic': 15.0, 'share': 5, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'BAD', 'capital': 180000, 'roic': 2.0, 'share': 90, 'lifecycle': 'KILL'},
        ]

        result = optimize_allocation(allocations)

        star = next(r for r in result if r.sku_key == 'STAR')
        bad = next(r for r in result if r.sku_key == 'BAD')

        # BAD should be killed
        assert bad.action == 'KILL'
        assert bad.recommended_capital == 0

        # STAR should get some of BAD's capital (up to 20% limit)
        # Total budget = 200K, max per SKU = 40K
        assert star.recommended_capital > 10000
        assert star.action == 'INCREASE'

    def test_empty_allocations(self):
        """Should handle empty allocation list."""
        result = optimize_allocation([])
        assert result == []

    def test_decrease_medium_roic(self):
        """SKUs with ROIC between 5-10% should be decreased."""
        allocations = [
            {'sku_key': 'MEDIUM', 'capital': 100000, 'roic': 7.5, 'share': 100, 'lifecycle': 'MAINTAIN'},
        ]

        result = optimize_allocation(allocations, min_roic_threshold=10.0)

        medium = result[0]
        assert medium.action == 'DECREASE'
        assert medium.recommended_capital < 100000

    def test_hold_good_performers(self):
        """SKUs with good ROIC within concentration should be held."""
        # Multiple SKUs to keep concentration reasonable
        allocations = [
            {'sku_key': 'GOOD', 'capital': 20000, 'roic': 15.0, 'share': 10, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'OTHER1', 'capital': 40000, 'roic': 12.0, 'share': 20, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'OTHER2', 'capital': 40000, 'roic': 11.0, 'share': 20, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'OTHER3', 'capital': 40000, 'roic': 10.5, 'share': 20, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'OTHER4', 'capital': 60000, 'roic': 10.1, 'share': 30, 'lifecycle': 'MAINTAIN'},
        ]

        result = optimize_allocation(allocations, max_concentration=0.30)

        good = next(r for r in result if r.sku_key == 'GOOD')
        # GOOD is at 10% concentration (20K/200K), below 30% limit, and ROIC 15% > 10%
        assert good.action == 'HOLD'
        assert good.recommended_capital == 20000


class TestConcentrationRule:
    """Tests for check_concentration_rule function."""

    def test_flags_violation(self):
        """Should flag when SKU would exceed 20%."""
        result = check_concentration_rule(
            proposed_po={'SKU_A': 100},
            current_inventory={'SKU_A': 400, 'SKU_B': 100},
            unit_costs={'SKU_A': 1000, 'SKU_B': 1000},
            max_concentration=0.20
        )

        assert not result['valid']
        assert len(result['violations']) == 1
        assert result['violations'][0]['sku_key'] == 'SKU_A'

    def test_adjusts_po(self):
        """Should provide adjusted PO quantities."""
        result = check_concentration_rule(
            proposed_po={'SKU_A': 300},
            current_inventory={'SKU_A': 0, 'SKU_B': 800},
            unit_costs={'SKU_A': 1000, 'SKU_B': 1000},
            max_concentration=0.20
        )

        # After PO: SKU_A=300, SKU_B=800, total=1100
        # 300/1100 = 27% > 20%
        assert not result['valid']
        assert result['adjusted_po']['SKU_A'] < 300

    def test_valid_po(self):
        """Should pass when within concentration limits."""
        result = check_concentration_rule(
            proposed_po={'SKU_A': 50},
            current_inventory={'SKU_A': 100, 'SKU_B': 400},
            unit_costs={'SKU_A': 1000, 'SKU_B': 1000},
            max_concentration=0.20
        )

        # After PO: SKU_A=150, SKU_B=400, total=550
        # 150/550 = 27% > 20% - still a violation
        # Actually recalculating: 150*1000 = 150K, 400*1000 = 400K, total 550K
        # 150/550 = 27.3% > 20% - this should still be a violation

        # Let me use a case that's actually valid
        result = check_concentration_rule(
            proposed_po={'SKU_A': 10},
            current_inventory={'SKU_A': 50, 'SKU_B': 400},
            unit_costs={'SKU_A': 1000, 'SKU_B': 1000},
            max_concentration=0.20
        )

        # After PO: SKU_A=60, SKU_B=400, total=460
        # 60/460 = 13% < 20% - should be valid
        assert result['valid']
        assert len(result['violations']) == 0

    def test_empty_po(self):
        """Should handle empty PO."""
        result = check_concentration_rule(
            proposed_po={},
            current_inventory={'SKU_A': 100},
            unit_costs={'SKU_A': 1000},
            max_concentration=0.20
        )

        assert result['valid']


class TestPortfolioImpact:
    """Tests for calc_portfolio_impact function."""

    def test_calculates_roic_lift(self):
        """Should calculate ROIC improvement correctly."""
        current = [
            {'sku_key': 'A', 'capital': 100000, 'roic': 10.0, 'share': 50, 'lifecycle': 'MAINTAIN'},
            {'sku_key': 'B', 'capital': 100000, 'roic': 20.0, 'share': 50, 'lifecycle': 'GROW'},
        ]

        from core.calc.capital_optimizer import SKUAllocation
        optimized = [
            SKUAllocation('A', 100000, 10.0, 50000, -50000, 'DECREASE'),
            SKUAllocation('B', 100000, 20.0, 150000, 50000, 'INCREASE'),
        ]

        impact = calc_portfolio_impact(current, optimized)

        # Current weighted ROIC = (100K*10 + 100K*20) / 200K = 15%
        assert impact['current_portfolio_roic'] == 15.0

        # New weighted ROIC = (50K*10 + 150K*20) / 200K = (500K + 3000K)/200K = 17.5%
        assert impact['projected_portfolio_roic'] == 17.5
        assert impact['roic_lift'] == 2.5

    def test_counts_actions(self):
        """Should correctly count action types."""
        current = [
            {'sku_key': 'A', 'capital': 100000, 'roic': 25.0, 'share': 50, 'lifecycle': 'GROW'},
            {'sku_key': 'B', 'capital': 100000, 'roic': 3.0, 'share': 50, 'lifecycle': 'KILL'},
        ]

        from core.calc.capital_optimizer import SKUAllocation
        optimized = [
            SKUAllocation('A', 100000, 25.0, 200000, 100000, 'INCREASE'),
            SKUAllocation('B', 100000, 3.0, 0, -100000, 'KILL'),
        ]

        impact = calc_portfolio_impact(current, optimized)

        assert impact['skus_increased'] == 1
        assert impact['skus_killed'] == 1
        assert impact['skus_decreased'] == 0
