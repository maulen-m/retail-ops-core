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
