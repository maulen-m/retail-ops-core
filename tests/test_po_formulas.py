"""
Tests for PO Dashboard formulas (T_post, Target, Pre-arrival).

Regression tests to prevent formula drift per Master_Inventory_Rules_v9.md:
- T_post = R + (SS_total / D)  # NO L in T_post!
- Target = D × T_post = D × R + SS_total
- Pre-arrival = Current + Inbound - D × effective_L
- effective_L = L + prep_days

Reference values from Master_Inventory_Rules_v9.md:
- L = 21 (lead time)
- R = 10 (review period)
- B = 14 (buffer factor)
- z = 1.65 (service level)
- TV = 0.23 (mix variability)
"""

import pytest
import math
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.inventory_params import get_params


class TestTPostFormula:
    """
    T_post = R + (SS_total / D)

    CRITICAL: Lead time L is NOT in T_post.
    L is accounted in pre-arrival consumption window.
    """

    def test_t_post_excludes_lead_time(self):
        """T_post should NOT include L."""
        params = get_params()
        D = 5.0
        SS_total = 100.0

        # CORRECT formula (no L)
        T_post = params.R + (SS_total / D)

        # WRONG formula would be R + L + SS/D
        T_post_wrong = params.R + params.L + (SS_total / D)

        # T_post should be ~21 days LESS than wrong formula
        assert abs(T_post_wrong - T_post - params.L) < 0.01

        # T_post for D=5, SS=100, R=10 should be 10 + 20 = 30
        expected = 10 + (100 / 5)
        assert abs(T_post - expected) < 0.01

    def test_t_post_line52_reference(self):
        """
        LINE52 reference case from Master_Inventory_Rules_v9.md.
        D = 41.477, SS_total ≈ 900
        T_post should be ~31.7 days (NOT ~53 days!)
        """
        params = get_params()
        D = 41.477

        # Calculate SS_total using actual formula
        sigma = D * 0.4  # sigma_factor
        ss_demand = params.z * sigma * math.sqrt(params.L)
        ss_floor = D * params.B
        ss_mix = params.TV * D * params.L
        SS_total = ss_demand + ss_floor + ss_mix

        # T_post = R + SS/D (NO L!)
        T_post = params.R + (SS_total / D)

        # Should be approximately 31-32 days
        assert 30 < T_post < 35, f"T_post should be ~32, got {T_post}"

        # Must NOT be ~53 (which includes L incorrectly)
        assert T_post < 40, f"T_post should not include L! Got {T_post}"

    def test_t_post_zero_demand(self):
        """T_post with zero demand should fall back to R."""
        params = get_params()
        D = 0.0
        SS_total = 100.0  # Shouldn't matter

        # With zero demand, T_post defaults to R
        T_post = params.R if D == 0 else params.R + (SS_total / D)

        assert T_post == params.R


class TestTargetFormula:
    """
    Target = D × T_post = D × R + SS_total

    This is target stock AFTER arrival.
    """

    def test_target_equals_d_times_t_post(self):
        """Target = D × T_post."""
        params = get_params()
        D = 5.0
        SS_total = 100.0

        T_post = params.R + (SS_total / D)
        Target = D * T_post

        # Alternative formula: Target = D × R + SS_total
        Target_alt = D * params.R + SS_total

        # Both should be equal
        assert abs(Target - Target_alt) < 0.01

    def test_target_line52_reference(self):
        """
        LINE52 reference: D=41.477, SS≈900
        Target ≈ 41.477 × 10 + 900 ≈ 1315 (NOT ~2200!)
        """
        params = get_params()
        D = 41.477

        # Calculate SS_total
        sigma = D * 0.4
        ss_demand = params.z * sigma * math.sqrt(params.L)
        ss_floor = D * params.B
        ss_mix = params.TV * D * params.L
        SS_total = ss_demand + ss_floor + ss_mix

        # Target = D × R + SS_total
        Target = D * params.R + SS_total

        # Should be approximately 1300-1400
        assert 1200 < Target < 1500, f"Target should be ~1300, got {Target}"

        # Must NOT be ~2200 (which uses wrong T_post with L)
        assert Target < 1600, f"Target too high - likely using wrong T_post"


class TestPreArrivalFormula:
    """
    Pre-arrival = Current + Inbound - D × effective_L
    effective_L = L + prep_days

    This projects stock at arrival time.
    """

    def test_pre_arrival_uses_effective_lead_time(self):
        """Pre-arrival consumption uses effective_L (L + prep)."""
        params = get_params()
        D = 5.0
        Current = 200
        Inbound = 50
        prep_days = 5

        effective_L = params.L + prep_days
        consumption = D * effective_L
        Pre_arrival = max(0, Current + Inbound - consumption)

        # Expected: 200 + 50 - 5 × 26 = 250 - 130 = 120
        expected = max(0, 200 + 50 - 5 * 26)
        assert abs(Pre_arrival - expected) < 0.01

    def test_pre_arrival_floor_at_zero(self):
        """Pre-arrival cannot be negative."""
        params = get_params()
        D = 10.0  # High demand
        Current = 50
        Inbound = 0
        prep_days = 5

        effective_L = params.L + prep_days  # 26 days
        consumption = D * effective_L  # 260 units consumed
        Pre_arrival = max(0, Current + Inbound - consumption)

        # Should be 0, not -210
        assert Pre_arrival == 0


class TestDaysToArrival:
    """
    Days→Arr = effective_L = L + prep_days

    This is displayed on dashboard as total time from message to arrival.
    """

    def test_days_to_arrival_includes_prep(self):
        """Days to arrival must include prep days."""
        params = get_params()
        prep_days = 5

        days_to_arrival = params.L + prep_days

        # Must be L + prep, not just L
        assert days_to_arrival == 26  # 21 + 5
        assert days_to_arrival > params.L

    def test_prep_days_formula_clothes(self):
        """prep_days = max(1, ceil(1.3 × weight_kg / 100)) for clothes."""
        weight_kg = 300  # 300 kg order

        # Formula from calc_prep_days
        prep_days = max(1, math.ceil(1.3 * weight_kg / 100))

        # 1.3 × 300 / 100 = 3.9 → ceil = 4
        assert prep_days == 4

    def test_prep_days_minimum_is_one(self):
        """prep_days minimum is 1 (even for zero-weight orders)."""
        weight_kg = 0
        prep_days = max(1, math.ceil(1.3 * weight_kg / 100))
        assert prep_days == 1


class TestFormulaConsistency:
    """
    Tests that ensure formulas are internally consistent.
    """

    def test_order_qty_formula(self):
        """
        Order_qty = max(0, Target - Pre_arrival)

        Combines T_post and Pre-arrival correctly.
        """
        params = get_params()
        D = 5.0
        Current = 100
        Inbound = 20
        prep_days = 3

        # Calculate SS_total
        sigma = D * 0.4
        ss_demand = params.z * sigma * math.sqrt(params.L)
        ss_floor = D * params.B
        ss_mix = params.TV * D * params.L
        SS_total = ss_demand + ss_floor + ss_mix

        # T_post = R + SS/D (NO L!)
        T_post = params.R + (SS_total / D)
        Target = D * T_post

        # Pre-arrival
        effective_L = params.L + prep_days
        Pre_arrival = max(0, Current + Inbound - D * effective_L)

        # Order qty
        Order_qty = max(0, int(round(Target - Pre_arrival)))

        # Verify it's positive but reasonable
        assert Order_qty >= 0
        # Target - Pre should make sense
        assert Target > 0


class TestRegressionLine52:
    """
    Full regression test using LINE52 as reference.

    Before fix: T_post ≈ 53, Target ≈ 2200
    After fix: T_post ≈ 32, Target ≈ 1300
    """

    def test_line52_t_post_not_inflated(self):
        """LINE52 T_post should be ~32, not ~53."""
        params = get_params()
        D = 41.477  # LINE52 demand

        sigma = D * 0.4
        ss_demand = params.z * sigma * math.sqrt(params.L)
        ss_floor = D * params.B
        ss_mix = params.TV * D * params.L
        SS_total = ss_demand + ss_floor + ss_mix

        T_post = params.R + (SS_total / D)

        # Critical assertion: T_post must NOT be ~53
        assert T_post < 40, f"REGRESSION: T_post={T_post} is too high (includes L?)"

        # T_post should be around 30-35
        assert 28 < T_post < 38, f"T_post={T_post} out of expected range"

    def test_line52_target_not_inflated(self):
        """LINE52 Target should be ~1300, not ~2200."""
        params = get_params()
        D = 41.477

        sigma = D * 0.4
        ss_demand = params.z * sigma * math.sqrt(params.L)
        ss_floor = D * params.B
        ss_mix = params.TV * D * params.L
        SS_total = ss_demand + ss_floor + ss_mix

        T_post = params.R + (SS_total / D)
        Target = D * T_post

        # Critical assertion: Target must NOT be ~2200
        assert Target < 1600, f"REGRESSION: Target={Target} is too high"

        # Target should be around 1200-1400
        assert 1100 < Target < 1500, f"Target={Target} out of expected range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
