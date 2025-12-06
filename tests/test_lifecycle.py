"""
Tests for lifecycle classifier.

TASK-082
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.lifecycle_classifier import classify_lifecycle


class TestLifecycleClassifier:
    """Tests for classify_lifecycle function."""

    def test_grow_high_roic_rising(self):
        """High ROIC + rising trend = GROW."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=25.0,
            roic_30d_ago=20.0,
            sales_trend_slope=0.10,
            days_since_last_sale=1
        )
        assert result.recommended_status == 'GROW'
        assert result.trend == 'RISING'

    def test_grow_high_roic_stable(self):
        """High ROIC + stable trend = GROW."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=25.0,
            roic_30d_ago=25.0,
            sales_trend_slope=0.0,
            days_since_last_sale=2
        )
        assert result.recommended_status == 'GROW'
        assert result.trend == 'STABLE'

    def test_maintain_medium_roic_stable(self):
        """Medium ROIC + stable trend = MAINTAIN."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=15.0,
            roic_30d_ago=15.0,
            sales_trend_slope=0.0,
            days_since_last_sale=3
        )
        assert result.recommended_status == 'MAINTAIN'

    def test_harvest_declining_trend(self):
        """Good ROIC but falling = HARVEST."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=18.0,
            roic_30d_ago=25.0,
            sales_trend_slope=-0.15,
            days_since_last_sale=5
        )
        assert result.recommended_status == 'HARVEST'
        assert result.trend == 'FALLING'

    def test_harvest_declining_roic(self):
        """Good ROIC but declining significantly = HARVEST."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=15.0,
            roic_30d_ago=25.0,  # Dropped by 40%
            sales_trend_slope=0.0,
            days_since_last_sale=5
        )
        assert result.recommended_status == 'HARVEST'

    def test_kill_dead_stock(self):
        """No sales for 60+ days with low ROIC = KILL."""
        # Must have ROIC < 5% to be killed for dead stock
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=3.0,  # Low ROIC
            roic_30d_ago=5.0,
            sales_trend_slope=0.0,
            days_since_last_sale=90
        )
        assert result.recommended_status == 'KILL'
        assert 'Dead stock' in result.reason

    def test_kill_negative_roic(self):
        """Negative ROIC = KILL."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=-5.0,
            roic_30d_ago=2.0,
            sales_trend_slope=-0.20,
            days_since_last_sale=10
        )
        assert result.recommended_status == 'KILL'
        assert 'Negative ROIC' in result.reason

    def test_maintain_low_roic_improving(self):
        """Low ROIC but improving = MAINTAIN."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=7.0,
            roic_30d_ago=5.0,
            sales_trend_slope=0.10,  # Rising
            days_since_last_sale=2
        )
        assert result.recommended_status == 'MAINTAIN'
        assert result.trend == 'RISING'

    def test_harvest_low_roic_stable(self):
        """Low ROIC + stable = HARVEST."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=7.0,
            roic_30d_ago=7.0,
            sales_trend_slope=0.0,
            days_since_last_sale=5
        )
        assert result.recommended_status == 'HARVEST'

    def test_harvest_very_low_roic(self):
        """Very low ROIC (< 5%) with recent sales = HARVEST (not KILL)."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=3.0,
            roic_30d_ago=5.0,
            sales_trend_slope=0.0,
            days_since_last_sale=10
        )
        assert result.recommended_status == 'HARVEST'

    def test_action_recommendations(self):
        """Action recommendations should be meaningful."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=30.0,
            roic_30d_ago=25.0,
            sales_trend_slope=0.10,
            days_since_last_sale=1
        )
        assert 'Increase' in result.action

        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=2.0,
            roic_30d_ago=5.0,
            sales_trend_slope=-0.10,
            days_since_last_sale=70
        )
        assert 'Liquidate' in result.action

    def test_trend_classification(self):
        """Trend should be classified correctly."""
        # Rising
        result = classify_lifecycle('TEST', 20.0, None, 0.10, 1)
        assert result.trend == 'RISING'

        # Stable
        result = classify_lifecycle('TEST', 20.0, None, 0.02, 1)
        assert result.trend == 'STABLE'

        # Falling
        result = classify_lifecycle('TEST', 20.0, None, -0.10, 1)
        assert result.trend == 'FALLING'

    def test_none_roic_30d_ago(self):
        """Should handle None for roic_30d_ago."""
        result = classify_lifecycle(
            sku_key='TEST',
            roic_pct=15.0,
            roic_30d_ago=None,
            sales_trend_slope=0.0,
            days_since_last_sale=5
        )
        # Should not crash and should give a reasonable result
        assert result.recommended_status in ['GROW', 'MAINTAIN', 'HARVEST', 'KILL']
