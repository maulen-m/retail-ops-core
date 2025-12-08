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
