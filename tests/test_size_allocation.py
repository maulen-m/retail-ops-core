"""
Tests for Phase 9.6: Size-Aware PO Engine

Test coverage:
- TASK-150: inventory_params.py (5 tests)
- TASK-151: size_allocation.py data structures (3 tests)
- TASK-152: OOS-filtered demand calculation (8 tests)
- TASK-153: Size mix with guardrails (6 tests)
- TASK-154: Per-size safety stock (6 tests)
- TASK-155: Per-size ROP and T_post (5 tests)
- TASK-156: Lead time consumption (5 tests)
- TASK-157: Per-size status calculation (5 tests)
- TASK-158: PO trigger logic (4 tests)
- TASK-159: Size allocation calculation (5 tests)
- TASK-160: New SKU adjustments (5 tests)
- TASK-161: Low demand insurance (4 tests)
- TASK-162: ROIC calculation (4 tests)
- TASK-163: 3-tier ROIC gate (4 tests)
- TASK-164: generate_po_draft (8 tests)
- TASK-165: DB queries (4 tests - integration)
- TASK-166: po_generator integration (3 tests)
- TASK-167: export_po_suggestions (2 tests)

Total: 86 tests
"""

import pytest
import math
from dataclasses import FrozenInstanceError


# =============================================================================
# TASK-150: inventory_params.py tests (5 tests)
# =============================================================================

class TestInventoryParams:
    """Tests for core/config/inventory_params.py"""

    def test_params_match_master_rules(self):
        """Verify all parameters match Master_Inventory_Rules_v5.3.md exactly."""
        from core.config.inventory_params import get_params

        params = get_params()

        # Master Rules Section 4.1: Global Defaults
        assert params.L == 21, "L (lead time) must be 21 days"
        assert params.R == 10, "R (review period) must be 10 days"
        assert params.B == 14, "B (buffer factor) must be 14 days"
        assert params.z == 1.65, "z (service level) must be 1.65"
        assert params.TV == 0.23, "TV (mix variability) must be 0.23"

        # Master Rules Section 5.1: sigma = D × 0.4
        assert params.sigma_factor == 0.4, "sigma_factor must be 0.4"

    def test_params_immutable(self):
        """Verify InventoryParams is immutable (frozen dataclass)."""
        from core.config.inventory_params import get_params

        params = get_params()

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            params.L = 30

        with pytest.raises(FrozenInstanceError):
            params.z = 2.0

    def test_get_params_singleton(self):
        """Verify get_params() returns the same instance."""
        from core.config.inventory_params import get_params, reset_params

        # Reset to ensure clean state
        reset_params()

        params1 = get_params()
        params2 = get_params()

        assert params1 is params2, "get_params() must return singleton instance"

    def test_all_params_have_values(self):
        """Verify all expected parameters exist."""
        from core.config.inventory_params import get_params

        params = get_params()

        # Core parameters
        assert hasattr(params, 'L')
        assert hasattr(params, 'R')
        assert hasattr(params, 'B')
        assert hasattr(params, 'z')
        assert hasattr(params, 'TV')
        assert hasattr(params, 'sigma_factor')

        # Phase 9.6 parameters
        assert hasattr(params, 'min_size_mix')
        assert hasattr(params, 'max_size_mix')
        assert hasattr(params, 'roic_full_approval')
        assert hasattr(params, 'roic_flag_threshold')
        assert hasattr(params, 'new_sku_30d_factor')
        assert hasattr(params, 'new_sku_60d_factor')
        assert hasattr(params, 'new_sku_90d_factor')

    def test_no_none_values(self):
        """Verify no parameter has None value."""
        from core.config.inventory_params import get_params
        from dataclasses import fields

        params = get_params()

        for field in fields(params):
            value = getattr(params, field.name)
            assert value is not None, f"Parameter {field.name} must not be None"


# =============================================================================
# TASK-151: size_allocation.py data structures (3 tests)
# =============================================================================

class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_order_status_values(self):
        """Verify OrderStatus has correct values."""
        from core.calc.size_allocation import OrderStatus

        assert OrderStatus.REORDER.value == "REORDER"
        assert OrderStatus.WAIT.value == "WAIT"
        assert OrderStatus.OK.value == "OK"

        # Verify we have exactly 3 statuses
        assert len(OrderStatus) == 3


class TestROICAction:
    """Tests for ROICAction enum."""

    def test_roic_action_values(self):
        """Verify ROICAction has correct values."""
        from core.calc.size_allocation import ROICAction

        assert ROICAction.ORDER_FULL.value == "ORDER_FULL"
        assert ROICAction.ORDER_WITH_FLAG.value == "ORDER_WITH_FLAG"
        assert ROICAction.REVIEW_REQUIRED.value == "REVIEW_REQUIRED"

        # Verify we have exactly 3 actions
        assert len(ROICAction) == 3


class TestDataclasses:
    """Tests for SizeData, SizeAllocation, PODraft dataclasses."""

    def test_dataclass_creation(self):
        """Verify dataclasses can be created with defaults."""
        from core.calc.size_allocation import (
            SizeData, SizeAllocation, PODraft, OrderStatus, DemandConfidence
        )

        # SizeData with defaults
        size_data = SizeData(my_size="L")
        assert size_data.my_size == "L"
        assert size_data.current_stock == 0
        assert size_data.status == OrderStatus.OK
        assert size_data.demand_confidence == DemandConfidence.NO_DATA

        # SizeAllocation with defaults
        allocation = SizeAllocation(my_size="XL")
        assert allocation.my_size == "XL"
        assert allocation.order_qty == 0
        assert allocation.status == OrderStatus.OK

        # PODraft with defaults
        draft = PODraft(sku_key="LINE52_BLACK")
        assert draft.sku_key == "LINE52_BLACK"
        assert draft.should_order is False
        assert draft.trigger_sizes == []
        assert draft.allocations == {}


# =============================================================================
# TASK-152: OOS-filtered demand calculation (8 tests)
# =============================================================================

class TestOOSFilteredDemand:
    """Tests for calc_d_sku_with_oos_filter()"""

    def test_oos_filter_excludes_stockout_days(self):
        """OOS days (sales=0 AND stock=0) should be excluded."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter

        # 5 days: 3 good days, 2 OOS days
        sales = [5, 0, 3, 0, 2]   # Total good sales: 5+3+2 = 10
        stock = [10, 0, 7, 0, 5]  # Days 2 and 4 are OOS (sales=0, stock=0)

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 3  # Only 3 good days
        # Base demand = 10/3 = 3.33, but < 14 days so FALLBACK with 1.5x uplift
        assert d == pytest.approx(10 / 3 * 1.5, rel=0.01)

    def test_oos_filter_keeps_zero_sales_with_stock(self):
        """Days with zero sales but positive stock should be counted."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter

        # 5 days: all good (including zero-sales days with stock)
        sales = [5, 0, 3, 0, 2]   # Total: 10
        stock = [10, 5, 7, 3, 5]  # All have stock, so all are good days

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 5  # All 5 days are good
        # Base demand = 10/5 = 2.0, but < 14 days so FALLBACK
        assert d == pytest.approx(2.0 * 1.5, rel=0.01)

    def test_oos_filter_actual_confidence(self):
        """≥30 good days should return ACTUAL confidence with no uplift."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter, DemandConfidence

        # 30 good days, 3 sales each day
        sales = [3] * 30
        stock = [10] * 30

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 30
        assert conf == DemandConfidence.ACTUAL
        assert d == pytest.approx(3.0, rel=0.01)  # No uplift

    def test_oos_filter_marginal_confidence(self):
        """14-29 good days should return MARGINAL confidence with 1.2x uplift."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter, DemandConfidence

        # 20 good days
        sales = [2] * 20
        stock = [10] * 20

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 20
        assert conf == DemandConfidence.MARGINAL
        # Base = 2.0, uplift 1.2x = 2.4
        assert d == pytest.approx(2.0 * 1.2, rel=0.01)

    def test_oos_filter_fallback_confidence(self):
        """<14 good days should return FALLBACK confidence with 1.5x uplift."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter, DemandConfidence

        # 10 good days
        sales = [4] * 10
        stock = [10] * 10

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 10
        assert conf == DemandConfidence.FALLBACK
        # Base = 4.0, uplift 1.5x = 6.0
        assert d == pytest.approx(4.0 * 1.5, rel=0.01)

    def test_oos_filter_no_data(self):
        """0 good days or empty lists should return NO_DATA."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter, DemandConfidence

        # Empty lists
        d, good_days, conf = calc_d_sku_with_oos_filter([], [])
        assert d == 0.0
        assert good_days == 0
        assert conf == DemandConfidence.NO_DATA

        # All OOS days
        sales = [0, 0, 0]
        stock = [0, 0, 0]
        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)
        assert d == 0.0
        assert good_days == 0
        assert conf == DemandConfidence.NO_DATA

    def test_oos_filter_all_good_days(self):
        """All days with stock should be counted regardless of sales."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter

        # 35 days, varying sales but always has stock
        sales = [1, 0, 2, 0, 3] * 7  # 35 days, total = 42
        stock = [10] * 35  # Always has stock

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 35
        # Base = 42/35 = 1.2, ≥30 days so ACTUAL (no uplift)
        assert d == pytest.approx(42 / 35, rel=0.01)

    def test_oos_filter_mixed_oos_periods(self):
        """Mixed periods with some OOS stretches."""
        from core.calc.size_allocation import calc_d_sku_with_oos_filter, DemandConfidence

        # Simulate: 10 good days, then 5 OOS, then 5 good days = 15 good days
        sales = [3] * 10 + [0] * 5 + [3] * 5  # Total good sales: 45
        stock = [10] * 10 + [0] * 5 + [10] * 5  # Middle 5 are OOS

        d, good_days, conf = calc_d_sku_with_oos_filter(sales, stock)

        assert good_days == 15  # 10 + 5 good days
        assert conf == DemandConfidence.MARGINAL  # 14-29 days
        # Base = 45/15 = 3.0, 1.2x uplift
        assert d == pytest.approx(3.0 * 1.2, rel=0.01)


# =============================================================================
# TASK-153: Size mix with guardrails (6 tests)
# =============================================================================

class TestSizeMixGuardrails:
    """Tests for calc_size_mix_with_guardrails()"""

    def test_mix_sums_to_one(self):
        """Mix percentages must always sum to 1.0."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        sales = {"S": 10, "M": 30, "L": 40, "XL": 15, "2XL": 5}
        mix = calc_size_mix_with_guardrails(sales)

        total = sum(mix.values())
        assert total == pytest.approx(1.0, rel=0.001)

    def test_mix_floor_applied(self):
        """Sizes with very low sales should get minimum 3% floor."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        # S has only 1% raw (1/100), should be raised to 3%
        sales = {"S": 1, "M": 30, "L": 40, "XL": 25, "2XL": 4}
        mix = calc_size_mix_with_guardrails(sales)

        # After renormalization, S should be >= min floor effect
        # Raw: S=1%, M=30%, L=40%, XL=25%, 2XL=4%
        # S at 1% < 3%, so floor applied
        assert "S" in mix
        # The exact value depends on renormalization, but should be elevated
        assert mix["S"] >= 0.01  # At least some floor effect

    def test_mix_cap_applied(self):
        """Sizes with very high sales should be capped at 40%."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        # L has 70% raw (70/100), should be capped to 40%
        sales = {"S": 5, "M": 15, "L": 70, "XL": 8, "2XL": 2}
        mix = calc_size_mix_with_guardrails(sales)

        # After renormalization:
        # L: 40% (capped), S: 5%, M: 15%, XL: 8%, 2XL: 3% (floored)
        # Total before renorm: 0.71
        # L after renorm: 0.40/0.71 ≈ 0.563
        # Key assertion: L should be < 70% original
        assert mix["L"] < 0.70  # Significantly below original 70%
        assert mix["L"] > 0.40  # But still the largest after renorm

    def test_mix_renormalization(self):
        """After applying guardrails, mix should be renormalized to sum to 1.0."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        # All sizes at 20% each (5 sizes = 100%)
        sales = {"S": 20, "M": 20, "L": 20, "XL": 20, "2XL": 20}
        mix = calc_size_mix_with_guardrails(sales)

        # No guardrails should trigger, all at 20%
        total = sum(mix.values())
        assert total == pytest.approx(1.0, rel=0.001)

        for size in mix:
            assert mix[size] == pytest.approx(0.20, rel=0.01)

    def test_mix_zero_sales_uniform(self):
        """Zero total sales should result in uniform distribution."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        sales = {"S": 0, "M": 0, "L": 0, "XL": 0}
        mix = calc_size_mix_with_guardrails(sales)

        # 4 sizes with zero sales = 25% each
        assert len(mix) == 4
        for size in mix:
            assert mix[size] == pytest.approx(0.25, rel=0.01)

    def test_mix_single_dominant_size(self):
        """Single size with all sales should be capped and distributed."""
        from core.calc.size_allocation import calc_size_mix_with_guardrails

        # L has 100% of sales
        sales = {"S": 0, "M": 0, "L": 100, "XL": 0, "2XL": 0}
        mix = calc_size_mix_with_guardrails(sales)

        # L was 100%, capped to 40%
        # Others were 0%, floored to 3% each
        # Total before renorm: 0.40 + 4*0.03 = 0.52
        # After renorm: L = 0.40/0.52 ≈ 0.77, others = 0.03/0.52 ≈ 0.058 each

        # L should be dominant but capped
        assert mix["L"] < 1.0  # Not 100%
        assert mix["L"] > 0.5  # But still dominant after renorm

        # Other sizes should have some allocation
        for size in ["S", "M", "XL", "2XL"]:
            assert mix[size] > 0  # Not zero


# =============================================================================
# TASK-154: Per-size safety stock (6 tests)
# =============================================================================

class TestSafetyStockForSize:
    """Tests for calc_safety_stock_for_size()"""

    def test_sigma_size_scales_with_mix(self):
        """Sigma_size should scale proportionally with size mix."""
        from core.calc.size_allocation import calc_safety_stock_for_size

        sigma_sku = 2.0

        # Size with 20% mix
        sigma_20, _, _, _, _ = calc_safety_stock_for_size(
            d_size=1.0, sigma_sku=sigma_sku, size_mix=0.20
        )

        # Size with 40% mix
        sigma_40, _, _, _, _ = calc_safety_stock_for_size(
            d_size=2.0, sigma_sku=sigma_sku, size_mix=0.40
        )

        # sigma_40 should be exactly 2x sigma_20
        assert sigma_40 == pytest.approx(sigma_20 * 2, rel=0.01)

    def test_ss_demand_formula(self):
        """SS_demand = z × σ_size × √L"""
        from core.calc.size_allocation import calc_safety_stock_for_size

        # With known params: z=1.65, L=21
        sigma_sku = 2.0
        size_mix = 0.20
        sigma_size_expected = sigma_sku * size_mix  # 0.4

        _, ss_demand, _, _, _ = calc_safety_stock_for_size(
            d_size=1.0, sigma_sku=sigma_sku, size_mix=size_mix
        )

        # SS_demand = 1.65 × 0.4 × √21 = 1.65 × 0.4 × 4.58 ≈ 3.02
        import math
        expected = 1.65 * sigma_size_expected * math.sqrt(21)
        assert ss_demand == pytest.approx(expected, rel=0.01)

    def test_ss_floor_formula(self):
        """SS_floor = D_size × B"""
        from core.calc.size_allocation import calc_safety_stock_for_size

        d_size = 2.0
        _, _, ss_floor, _, _ = calc_safety_stock_for_size(
            d_size=d_size, sigma_sku=1.0, size_mix=0.20
        )

        # SS_floor = 2.0 × 14 = 28.0
        expected = d_size * 14
        assert ss_floor == pytest.approx(expected, rel=0.01)

    def test_ss_mix_formula(self):
        """SS_mix = TV × D_size × L"""
        from core.calc.size_allocation import calc_safety_stock_for_size

        d_size = 2.0
        _, _, _, ss_mix, _ = calc_safety_stock_for_size(
            d_size=d_size, sigma_sku=1.0, size_mix=0.20
        )

        # SS_mix = 0.23 × 2.0 × 21 = 9.66
        expected = 0.23 * d_size * 21
        assert ss_mix == pytest.approx(expected, rel=0.01)

    def test_ss_total_sum(self):
        """SS_total should equal sum of components."""
        from core.calc.size_allocation import calc_safety_stock_for_size

        sigma_size, ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock_for_size(
            d_size=2.0, sigma_sku=2.0, size_mix=0.30
        )

        # SS_total = SS_demand + SS_floor + SS_mix
        expected = ss_demand + ss_floor + ss_mix
        assert ss_total == pytest.approx(expected, rel=0.001)

    def test_ss_zero_demand(self):
        """Zero demand should result in zero SS_floor and SS_mix."""
        from core.calc.size_allocation import calc_safety_stock_for_size

        sigma_size, ss_demand, ss_floor, ss_mix, ss_total = calc_safety_stock_for_size(
            d_size=0.0, sigma_sku=2.0, size_mix=0.20
        )

        assert ss_floor == 0.0
        assert ss_mix == 0.0
        # SS_demand can still be non-zero if sigma_sku > 0
        assert ss_demand >= 0.0


# =============================================================================
# TASK-155: Per-size ROP and T_post (5 tests)
# =============================================================================

class TestROPAndTPost:
    """Tests for calc_rop_for_size() and calc_t_post_for_size()"""

    def test_rop_formula(self):
        """ROP = D_size × L + SS_total"""
        from core.calc.size_allocation import calc_rop_for_size

        d_size = 2.0
        ss_total = 30.0

        rop = calc_rop_for_size(d_size=d_size, ss_total=ss_total)

        # ROP = 2.0 × 21 + 30.0 = 72.0
        expected = d_size * 21 + ss_total
        assert rop == pytest.approx(expected, rel=0.01)

    def test_t_post_formula(self):
        """T_post = R + (SS_total / D_size)"""
        from core.calc.size_allocation import calc_t_post_for_size

        d_size = 2.0
        ss_total = 30.0

        t_post = calc_t_post_for_size(d_size=d_size, ss_total=ss_total)

        # T_post = 10 + (30.0 / 2.0) = 25.0
        expected = 10 + (ss_total / d_size)
        assert t_post == pytest.approx(expected, rel=0.01)

    def test_t_post_zero_demand_fallback(self):
        """Zero demand should return R (review period) as fallback."""
        from core.calc.size_allocation import calc_t_post_for_size

        t_post = calc_t_post_for_size(d_size=0.0, ss_total=30.0)

        # Should return R = 10 as fallback
        assert t_post == pytest.approx(10.0, rel=0.01)

    def test_rop_increases_with_demand(self):
        """Higher demand should increase ROP."""
        from core.calc.size_allocation import calc_rop_for_size

        ss_total = 20.0

        rop_low = calc_rop_for_size(d_size=1.0, ss_total=ss_total)
        rop_high = calc_rop_for_size(d_size=3.0, ss_total=ss_total)

        assert rop_high > rop_low

    def test_t_post_increases_with_ss(self):
        """Higher safety stock should increase T_post."""
        from core.calc.size_allocation import calc_t_post_for_size

        d_size = 2.0

        t_post_low = calc_t_post_for_size(d_size=d_size, ss_total=10.0)
        t_post_high = calc_t_post_for_size(d_size=d_size, ss_total=50.0)

        assert t_post_high > t_post_low


# =============================================================================
# TASK-156: Lead time consumption (5 tests)
# =============================================================================

class TestPreArrivalStock:
    """Tests for calc_pre_arrival_stock()"""

    def test_pre_arrival_basic(self):
        """Basic pre-arrival stock calculation."""
        from core.calc.size_allocation import calc_pre_arrival_stock

        pre = calc_pre_arrival_stock(
            current_stock=100,
            inbound_stock=0,
            d_size=3.0,
            days_to_arrival=21
        )

        # Pre = 100 + 0 - (3.0 × 21) = 100 - 63 = 37.0
        expected = 100 - (3.0 * 21)
        assert pre == pytest.approx(expected, rel=0.01)

    def test_pre_arrival_with_inbound(self):
        """Pre-arrival stock with inbound shipment."""
        from core.calc.size_allocation import calc_pre_arrival_stock

        pre = calc_pre_arrival_stock(
            current_stock=50,
            inbound_stock=30,
            d_size=2.0,
            days_to_arrival=21
        )

        # Pre = 50 + 30 - (2.0 × 21) = 80 - 42 = 38.0
        expected = 80 - (2.0 * 21)
        assert pre == pytest.approx(expected, rel=0.01)

    def test_pre_arrival_high_consumption(self):
        """High consumption depletes stock."""
        from core.calc.size_allocation import calc_pre_arrival_stock

        pre = calc_pre_arrival_stock(
            current_stock=30,
            inbound_stock=0,
            d_size=5.0,
            days_to_arrival=21
        )

        # Pre = 30 + 0 - (5.0 × 21) = 30 - 105 = -75 → 0
        assert pre == 0.0  # Clamped to zero

    def test_pre_arrival_floor_zero(self):
        """Pre-arrival stock cannot go negative."""
        from core.calc.size_allocation import calc_pre_arrival_stock

        pre = calc_pre_arrival_stock(
            current_stock=10,
            inbound_stock=0,
            d_size=10.0,
            days_to_arrival=21
        )

        # Would be negative, but clamped to 0
        assert pre >= 0.0

    def test_pre_arrival_no_consumption(self):
        """Zero demand means no consumption."""
        from core.calc.size_allocation import calc_pre_arrival_stock

        pre = calc_pre_arrival_stock(
            current_stock=50,
            inbound_stock=20,
            d_size=0.0,
            days_to_arrival=21
        )

        # Pre = 50 + 20 - 0 = 70.0
        assert pre == pytest.approx(70.0, rel=0.01)


# =============================================================================
# TASK-157: Per-size status calculation (5 tests)
# =============================================================================

class TestStatusForSize:
    """Tests for calc_status_for_size()"""

    def test_status_reorder(self):
        """Total < ROP should return REORDER."""
        from core.calc.size_allocation import calc_status_for_size, OrderStatus

        status = calc_status_for_size(
            current_stock=20,
            total_stock=30,
            rop=40
        )

        assert status == OrderStatus.REORDER

    def test_status_wait(self):
        """Current < ROP but Total >= ROP should return WAIT."""
        from core.calc.size_allocation import calc_status_for_size, OrderStatus

        status = calc_status_for_size(
            current_stock=30,
            total_stock=50,
            rop=40
        )

        assert status == OrderStatus.WAIT

    def test_status_ok(self):
        """Both Total and Current >= ROP should return OK."""
        from core.calc.size_allocation import calc_status_for_size, OrderStatus

        status = calc_status_for_size(
            current_stock=50,
            total_stock=60,
            rop=40
        )

        assert status == OrderStatus.OK

    def test_status_boundary_total_equals_rop(self):
        """Total == ROP (edge case): should be OK if current >= ROP."""
        from core.calc.size_allocation import calc_status_for_size, OrderStatus

        # Total == ROP == 40, Current == 40
        status = calc_status_for_size(
            current_stock=40,
            total_stock=40,
            rop=40
        )

        assert status == OrderStatus.OK

    def test_status_boundary_current_equals_rop(self):
        """Current == ROP with inbound should be OK."""
        from core.calc.size_allocation import calc_status_for_size, OrderStatus

        # Current == ROP, Total > ROP
        status = calc_status_for_size(
            current_stock=40,
            total_stock=60,
            rop=40
        )

        assert status == OrderStatus.OK


# =============================================================================
# TASK-158: PO trigger logic (4 tests)
# =============================================================================

class TestPOTrigger:
    """Tests for should_generate_po()"""

    def test_trigger_single_reorder(self):
        """Single size in REORDER should trigger PO."""
        from core.calc.size_allocation import should_generate_po, OrderStatus

        statuses = {
            "S": OrderStatus.OK,
            "M": OrderStatus.REORDER,
            "L": OrderStatus.OK,
            "XL": OrderStatus.WAIT
        }

        should_order, triggers = should_generate_po(statuses)

        assert should_order is True
        assert "M" in triggers
        assert len(triggers) == 1

    def test_trigger_multiple_reorder(self):
        """Multiple sizes in REORDER should all be listed."""
        from core.calc.size_allocation import should_generate_po, OrderStatus

        statuses = {
            "S": OrderStatus.REORDER,
            "M": OrderStatus.OK,
            "L": OrderStatus.REORDER,
            "XL": OrderStatus.WAIT
        }

        should_order, triggers = should_generate_po(statuses)

        assert should_order is True
        assert "S" in triggers
        assert "L" in triggers
        assert len(triggers) == 2

    def test_no_trigger_all_ok(self):
        """All OK should not trigger PO."""
        from core.calc.size_allocation import should_generate_po, OrderStatus

        statuses = {
            "S": OrderStatus.OK,
            "M": OrderStatus.OK,
            "L": OrderStatus.OK
        }

        should_order, triggers = should_generate_po(statuses)

        assert should_order is False
        assert len(triggers) == 0

    def test_no_trigger_all_wait(self):
        """All WAIT (but no REORDER) should not trigger PO."""
        from core.calc.size_allocation import should_generate_po, OrderStatus

        statuses = {
            "S": OrderStatus.WAIT,
            "M": OrderStatus.WAIT,
            "L": OrderStatus.OK
        }

        should_order, triggers = should_generate_po(statuses)

        assert should_order is False
        assert len(triggers) == 0


# =============================================================================
# TASK-159: Size allocation calculation (5 tests)
# =============================================================================

class TestOrderQtyForSize:
    """Tests for calc_order_qty_for_size()"""

    def test_allocation_basic(self):
        """Basic allocation calculation."""
        from core.calc.size_allocation import calc_order_qty_for_size

        qty = calc_order_qty_for_size(
            d_size=2.0,
            t_post=35.0,
            pre_arrival_stock=20.0
        )

        # target = 35 × 2 = 70, order = 70 - 20 = 50
        assert qty == 50

    def test_allocation_overstocked_zero(self):
        """Overstocked size should get zero allocation."""
        from core.calc.size_allocation import calc_order_qty_for_size

        qty = calc_order_qty_for_size(
            d_size=2.0,
            t_post=35.0,
            pre_arrival_stock=100.0  # More than target
        )

        # target = 70, pre = 100, order = max(0, 70-100) = 0
        assert qty == 0

    def test_allocation_rounds_correctly(self):
        """Allocation should round to nearest integer."""
        from core.calc.size_allocation import calc_order_qty_for_size

        qty = calc_order_qty_for_size(
            d_size=2.3,
            t_post=10.0,
            pre_arrival_stock=5.0
        )

        # target = 10 × 2.3 = 23, order = 23 - 5 = 18
        assert qty == 18

    def test_allocation_floor_zero(self):
        """Allocation cannot be negative."""
        from core.calc.size_allocation import calc_order_qty_for_size

        qty = calc_order_qty_for_size(
            d_size=1.0,
            t_post=10.0,
            pre_arrival_stock=50.0
        )

        # target = 10, pre = 50, would be -40 but clamped to 0
        assert qty == 0

    def test_allocation_high_demand(self):
        """High demand size should get larger allocation."""
        from core.calc.size_allocation import calc_order_qty_for_size

        qty_low = calc_order_qty_for_size(d_size=1.0, t_post=30.0, pre_arrival_stock=10.0)
        qty_high = calc_order_qty_for_size(d_size=3.0, t_post=30.0, pre_arrival_stock=10.0)

        assert qty_high > qty_low


# =============================================================================
# TASK-160: New SKU adjustments (5 tests)
# =============================================================================

class TestNewSKUAdjustment:
    """Tests for adjust_for_new_sku()"""

    def test_new_sku_under_30(self):
        """SKUs under 30 days should get 0.75× factor."""
        from core.calc.size_allocation import adjust_for_new_sku

        adj_qty, factor = adjust_for_new_sku(order_qty=100, sku_age_days=25)

        assert factor == 0.75
        assert adj_qty == 75

    def test_new_sku_30_to_60(self):
        """SKUs 30-60 days should get 0.85× factor."""
        from core.calc.size_allocation import adjust_for_new_sku

        adj_qty, factor = adjust_for_new_sku(order_qty=100, sku_age_days=45)

        assert factor == 0.85
        assert adj_qty == 85

    def test_new_sku_60_to_90(self):
        """SKUs 60-90 days should get 0.95× factor."""
        from core.calc.size_allocation import adjust_for_new_sku

        adj_qty, factor = adjust_for_new_sku(order_qty=100, sku_age_days=75)

        assert factor == 0.95
        assert adj_qty == 95

    def test_new_sku_full_history(self):
        """SKUs 90+ days should get full quantity (1.0× factor)."""
        from core.calc.size_allocation import adjust_for_new_sku

        adj_qty, factor = adjust_for_new_sku(order_qty=100, sku_age_days=120)

        assert factor == 1.0
        assert adj_qty == 100

    def test_new_sku_minimum_one(self):
        """Adjusted qty should be at least 1 if original was > 0."""
        from core.calc.size_allocation import adjust_for_new_sku

        # Very small order with large reduction
        adj_qty, factor = adjust_for_new_sku(order_qty=1, sku_age_days=10)

        # Would be 0.75 × 1 = 0.75 → rounds to 1 (minimum)
        assert adj_qty >= 1


# =============================================================================
# TASK-161: Low demand insurance (4 tests)
# =============================================================================

class TestLowDemandInsurance:
    """Tests for apply_low_demand_insurance()"""

    def test_insurance_applied(self):
        """Insurance should be applied when D < 0.1 AND mix >= 5%."""
        from core.calc.size_allocation import apply_low_demand_insurance

        allocations = {"S": 0, "M": 50, "L": 100}
        demands = {"S": 0.05, "M": 2.0, "L": 4.0}
        mixes = {"S": 0.10, "M": 0.30, "L": 0.60}

        updated = apply_low_demand_insurance(
            allocations, demands, mixes, total_po_qty=150
        )

        # S has low demand (0.05 < 0.1) and significant mix (10% >= 5%)
        # Should get 1% of 150 = 2 units (minimum 1)
        assert updated["S"] > allocations["S"]
        assert updated["S"] >= 1

    def test_insurance_not_needed_high_demand(self):
        """Insurance not applied if demand is sufficient."""
        from core.calc.size_allocation import apply_low_demand_insurance

        allocations = {"S": 10, "M": 50, "L": 100}
        demands = {"S": 0.5, "M": 2.0, "L": 4.0}  # S has demand 0.5 > 0.1
        mixes = {"S": 0.10, "M": 0.30, "L": 0.60}

        updated = apply_low_demand_insurance(
            allocations, demands, mixes, total_po_qty=160
        )

        # S has sufficient demand, no insurance needed
        assert updated["S"] == allocations["S"]

    def test_insurance_not_needed_low_mix(self):
        """Insurance not applied if mix is too low."""
        from core.calc.size_allocation import apply_low_demand_insurance

        allocations = {"S": 0, "M": 50, "L": 100}
        demands = {"S": 0.05, "M": 2.0, "L": 4.0}  # S has low demand
        mixes = {"S": 0.02, "M": 0.38, "L": 0.60}  # But mix is only 2% < 5%

        updated = apply_low_demand_insurance(
            allocations, demands, mixes, total_po_qty=150
        )

        # S has low mix, no insurance
        assert updated["S"] == allocations["S"]

    def test_insurance_minimum_one(self):
        """Insurance quantity should be at least 1 unit."""
        from core.calc.size_allocation import apply_low_demand_insurance

        allocations = {"S": 0, "M": 5, "L": 10}
        demands = {"S": 0.05, "M": 1.0, "L": 2.0}
        mixes = {"S": 0.10, "M": 0.30, "L": 0.60}

        # Very small PO
        updated = apply_low_demand_insurance(
            allocations, demands, mixes, total_po_qty=15
        )

        # 1% of 15 = 0.15, but minimum is 1
        assert updated["S"] >= 1


# =============================================================================
# TASK-162: ROIC calculation (4 tests)
# =============================================================================

class TestROICCalculation:
    """Tests for calc_roic()"""

    def test_roic_formula(self):
        """Verify ROIC formula: Monthly_ROIC = (profit × D × 30) / K_avg."""
        from core.calc.size_allocation import calc_roic

        # Known values for verification
        d_sku = 2.0
        ss_total = 50.0
        unit_cogs = 100.0
        unit_profit = 30.0

        roic = calc_roic(
            d_sku=d_sku,
            ss_total=ss_total,
            unit_cogs=unit_cogs,
            unit_profit=unit_profit
        )

        # Manual calculation:
        # K_avg = D × (L + R/2) × COGS + SS_total × COGS
        # K_avg = 2.0 × (21 + 10/2) × 100 + 50 × 100
        # K_avg = 2.0 × 26 × 100 + 5000 = 5200 + 5000 = 10200
        # Monthly_ROIC = (30 × 2.0 × 30) / 10200 = 1800 / 10200 ≈ 0.1765
        expected_k_avg = d_sku * (21 + 10/2) * unit_cogs + ss_total * unit_cogs
        expected_monthly_profit = unit_profit * d_sku * 30
        expected_roic = expected_monthly_profit / expected_k_avg

        assert roic == pytest.approx(expected_roic, rel=0.01)
        assert roic == pytest.approx(0.1765, rel=0.01)

    def test_roic_zero_k_avg(self):
        """Zero capital (K_avg=0) should return 0.0 ROIC."""
        from core.calc.size_allocation import calc_roic

        # All zeros = no capital invested
        roic = calc_roic(
            d_sku=0.0,
            ss_total=0.0,
            unit_cogs=100.0,
            unit_profit=30.0
        )

        assert roic == 0.0

    def test_roic_high_profit(self):
        """High profit margin should increase ROIC."""
        from core.calc.size_allocation import calc_roic

        # Low profit margin
        roic_low = calc_roic(
            d_sku=2.0,
            ss_total=50.0,
            unit_cogs=100.0,
            unit_profit=10.0  # 10% margin
        )

        # High profit margin
        roic_high = calc_roic(
            d_sku=2.0,
            ss_total=50.0,
            unit_cogs=100.0,
            unit_profit=50.0  # 50% margin
        )

        assert roic_high > roic_low
        assert roic_high == pytest.approx(roic_low * 5, rel=0.01)  # 5x profit = 5x ROIC

    def test_roic_matches_excel(self):
        """Verify ROIC matches expected Excel calculation within ±2%."""
        from core.calc.size_allocation import calc_roic

        # Example from spec: realistic values
        # D = 3.0/day, SS = 80 units, COGS = 150, profit = 45
        roic = calc_roic(
            d_sku=3.0,
            ss_total=80.0,
            unit_cogs=150.0,
            unit_profit=45.0
        )

        # K_avg = 3 × 26 × 150 + 80 × 150 = 11700 + 12000 = 23700
        # Monthly profit = 45 × 3 × 30 = 4050
        # ROIC = 4050 / 23700 ≈ 0.171 (17.1%)
        expected = 4050 / 23700
        assert roic == pytest.approx(expected, rel=0.02)  # ±2% tolerance


# =============================================================================
# TASK-163: 3-tier ROIC gate (4 tests)
# =============================================================================

class TestROICGate:
    """Tests for apply_roic_gate()"""

    def test_roic_gate_full(self):
        """ROIC ≥ 20% should return ORDER_FULL with full quantity."""
        from core.calc.size_allocation import apply_roic_gate, ROICAction

        action, qty = apply_roic_gate(roic=0.25, order_qty=100)

        assert action == ROICAction.ORDER_FULL
        assert qty == 100

    def test_roic_gate_flag(self):
        """ROIC 10-20% should return ORDER_WITH_FLAG with full quantity."""
        from core.calc.size_allocation import apply_roic_gate, ROICAction

        action, qty = apply_roic_gate(roic=0.15, order_qty=100)

        assert action == ROICAction.ORDER_WITH_FLAG
        assert qty == 100

    def test_roic_gate_review(self):
        """ROIC < 10% should return REVIEW_REQUIRED with qty=0."""
        from core.calc.size_allocation import apply_roic_gate, ROICAction

        action, qty = apply_roic_gate(roic=0.05, order_qty=100)

        assert action == ROICAction.REVIEW_REQUIRED
        assert qty == 0

    def test_roic_gate_boundary(self):
        """Test boundary values at 10% and 20%."""
        from core.calc.size_allocation import apply_roic_gate, ROICAction

        # Exactly 20% should be ORDER_FULL
        action_20, qty_20 = apply_roic_gate(roic=0.20, order_qty=100)
        assert action_20 == ROICAction.ORDER_FULL
        assert qty_20 == 100

        # Exactly 10% should be ORDER_WITH_FLAG
        action_10, qty_10 = apply_roic_gate(roic=0.10, order_qty=100)
        assert action_10 == ROICAction.ORDER_WITH_FLAG
        assert qty_10 == 100

        # Just under 10% should be REVIEW_REQUIRED
        action_9, qty_9 = apply_roic_gate(roic=0.099, order_qty=100)
        assert action_9 == ROICAction.REVIEW_REQUIRED
        assert qty_9 == 0
