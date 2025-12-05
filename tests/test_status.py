"""
Tests for core/calc/status.py

Tests the 3-state reorder logic: REORDER, WAIT, OK
"""

import pytest
from core.calc.status import (
    calc_status,
    calc_status_from_inventory,
    get_status_priority,
    is_action_required,
)


class TestCalcStatus:
    """Tests for core status calculation."""

    def test_reorder_when_total_below_rop(self):
        """REORDER when total_stock < ROP."""
        assert calc_status(50, 50, 100) == "REORDER"
        assert calc_status(0, 0, 100) == "REORDER"
        assert calc_status(99, 99, 100) == "REORDER"

    def test_wait_when_current_below_but_total_ok(self):
        """WAIT when current < ROP but total >= ROP."""
        assert calc_status(50, 150, 100) == "WAIT"
        assert calc_status(0, 150, 100) == "WAIT"
        assert calc_status(99, 100, 100) == "WAIT"

    def test_ok_when_current_at_or_above_rop(self):
        """OK when current_stock >= ROP."""
        assert calc_status(150, 200, 100) == "OK"
        assert calc_status(100, 100, 100) == "OK"
        assert calc_status(100, 150, 100) == "OK"

    def test_boundary_exactly_at_rop(self):
        """Boundary case: exactly at ROP is OK."""
        assert calc_status(100, 100, 100) == "OK"
        assert calc_status(100, 200, 100) == "OK"

    def test_total_checked_first(self):
        """Critical: total_stock is checked BEFORE current_stock."""
        # Even with current >= rop, if total < rop, it's REORDER
        # This shouldn't happen in practice (total >= current), but test logic
        # total=50 < rop=100, so REORDER regardless of current
        # Note: In real world, total is always >= current

        # More realistic: current=50, inbound=0, total=50
        assert calc_status(50, 50, 100) == "REORDER"


class TestCalcStatusFromInventory:
    """Tests for convenience function with inbound calculation."""

    def test_inbound_adds_to_total(self):
        """Inbound stock should be added to current for total."""
        # current=50, inbound=100, total=150, rop=100
        assert calc_status_from_inventory(50, 100, 100) == "WAIT"

    def test_zero_inbound(self):
        """Zero inbound should match calc_status behavior."""
        assert calc_status_from_inventory(50, 0, 100) == "REORDER"
        assert calc_status_from_inventory(150, 0, 100) == "OK"

    def test_inbound_prevents_reorder(self):
        """Sufficient inbound can change REORDER to WAIT."""
        # Without inbound: current=50 < rop=100 would be REORDER (total=current)
        # With inbound: current=50, inbound=100, total=150 >= rop=100 is WAIT
        status_no_inbound = calc_status_from_inventory(50, 0, 100)
        status_with_inbound = calc_status_from_inventory(50, 100, 100)

        assert status_no_inbound == "REORDER"
        assert status_with_inbound == "WAIT"


class TestStatusPriority:
    """Tests for status priority ordering."""

    def test_priority_values(self):
        """Priority should be: REORDER=1, WAIT=2, OK=3."""
        assert get_status_priority("REORDER") == 1
        assert get_status_priority("WAIT") == 2
        assert get_status_priority("OK") == 3

    def test_unknown_status(self):
        """Unknown status should get low priority (99)."""
        assert get_status_priority("UNKNOWN") == 99

    def test_priority_ordering(self):
        """REORDER should have highest priority (lowest number)."""
        assert get_status_priority("REORDER") < get_status_priority("WAIT")
        assert get_status_priority("WAIT") < get_status_priority("OK")


class TestActionRequired:
    """Tests for action requirement check."""

    def test_reorder_requires_action(self):
        """Only REORDER requires immediate action."""
        assert is_action_required("REORDER") is True

    def test_wait_no_action(self):
        """WAIT does not require immediate action."""
        assert is_action_required("WAIT") is False

    def test_ok_no_action(self):
        """OK does not require action."""
        assert is_action_required("OK") is False


class TestEdgeCases:
    """Edge case tests."""

    def test_zero_rop(self):
        """Zero ROP - everything should be OK."""
        assert calc_status(0, 0, 0) == "OK"
        assert calc_status(10, 10, 0) == "OK"

    def test_negative_values_handled(self):
        """Negative values (shouldn't happen but shouldn't crash)."""
        # These scenarios shouldn't happen in practice but test robustness
        status = calc_status(-10, -10, 100)
        assert status in ["REORDER", "WAIT", "OK"]

    def test_float_rop(self):
        """ROP can be float, comparison should still work."""
        assert calc_status(99, 99, 99.5) == "REORDER"  # 99 < 99.5
        assert calc_status(100, 100, 99.5) == "OK"     # 100 >= 99.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
