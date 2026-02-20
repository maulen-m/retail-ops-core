"""
Tests for core/capital/guardrails.py

Covers the unified capital guardrails:
- ROIC gate (3-tier)
- Concentration rule (20% max)
- Budget caps (global and per-draft)
- Unified check_all_guardrails()
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from core.capital.guardrails import (
    check_all_guardrails,
    check_roic_gate,
    check_concentration_rule,
    check_budget_cap,
    get_budget_caps,
    set_budget_caps,
    BudgetCaps,
    GuardrailResult,
    GuardrailStatus,
)
from core.calc.size_allocation import ROICAction


class TestROICGate:
    """Tests for ROIC gate (3-tier)."""

    def test_roic_order_full(self):
        """ROIC >= 20% should return ORDER_FULL."""
        action, reason = check_roic_gate(0.25)  # 25%
        assert action == ROICAction.ORDER_FULL
        assert "Auto-approved" in reason

    def test_roic_order_with_flag(self):
        """ROIC 10-20% should return ORDER_WITH_FLAG."""
        action, reason = check_roic_gate(0.15)  # 15%
        assert action == ROICAction.ORDER_WITH_FLAG
        assert "review flag" in reason

    def test_roic_review_required(self):
        """ROIC < 10% should return REVIEW_REQUIRED."""
        action, reason = check_roic_gate(0.05)  # 5%
        assert action == ROICAction.REVIEW_REQUIRED
        assert "Manual review" in reason

    def test_roic_boundary_20(self):
        """ROIC = 20% exactly should be ORDER_FULL."""
        action, _ = check_roic_gate(0.20)
        assert action == ROICAction.ORDER_FULL

    def test_roic_boundary_10(self):
        """ROIC = 10% exactly should be ORDER_WITH_FLAG."""
        action, _ = check_roic_gate(0.10)
        assert action == ROICAction.ORDER_WITH_FLAG


class TestConcentrationRule:
    """Tests for 20% concentration rule."""

    def test_concentration_passes_when_under_limit(self):
        """Should pass when all SKUs < 20%."""
        valid, reason, adj = check_concentration_rule(
            proposed_po={'SKU1': 10},
            current_inventory={'SKU1': 40, 'SKU2': 100, 'SKU3': 100},
            unit_costs={'SKU1': 1000, 'SKU2': 1000, 'SKU3': 1000},
        )
        assert valid is True
        assert "passed" in reason
        assert adj is None

    def test_concentration_fails_when_over_limit(self):
        """Should fail when SKU exceeds 20%."""
        valid, reason, adj = check_concentration_rule(
            proposed_po={'SKU1': 1000},
            current_inventory={'SKU1': 0, 'SKU2': 100},
            unit_costs={'SKU1': 1000, 'SKU2': 1000},
        )
        # SKU1 would be 1000*1000 / (1000*1000 + 100*1000) = 90.9%
        assert valid is False
        assert "violation" in reason.lower()
        assert adj is not None

    def test_concentration_provides_adjusted_po(self):
        """Should provide adjusted PO when violation occurs."""
        valid, reason, adj = check_concentration_rule(
            proposed_po={'SKU1': 500},
            current_inventory={'SKU1': 0, 'SKU2': 1000},
            unit_costs={'SKU1': 1000, 'SKU2': 1000},
        )
        if not valid:
            assert adj is not None
            assert 'SKU1' in adj
            # Adjusted quantity should be less than original
            assert adj['SKU1'] < 500


class TestBudgetCaps:
    """Tests for budget caps."""

    def test_budget_check_passes_when_no_caps(self):
        """Should pass when no caps are set."""
        caps = BudgetCaps()  # All zeros = unlimited
        valid, reason = check_budget_cap(1_000_000, caps)
        assert valid is True
        assert "passed" in reason.lower()

    def test_budget_check_fails_per_draft_cap(self):
        """Should fail when PO exceeds per-draft cap."""
        caps = BudgetCaps(per_draft_cap_kzt=500_000)
        valid, reason = check_budget_cap(600_000, caps)
        assert valid is False
        assert "per-draft cap" in reason.lower()

    def test_budget_check_fails_monthly_cap(self):
        """Should fail when PO would exceed monthly cap."""
        caps = BudgetCaps(
            global_monthly_cap_kzt=1_000_000,
            current_month_spend_kzt=800_000,
        )
        valid, reason = check_budget_cap(300_000, caps)
        assert valid is False
        assert "monthly cap" in reason.lower()

    def test_budget_check_passes_within_monthly_cap(self):
        """Should pass when within monthly cap."""
        caps = BudgetCaps(
            global_monthly_cap_kzt=1_000_000,
            current_month_spend_kzt=500_000,
        )
        valid, reason = check_budget_cap(400_000, caps)
        assert valid is True


class TestBudgetCapsDB:
    """Tests for budget caps database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.environ['DB_PATH'] = path
        yield path
        os.unlink(path)
        os.environ.pop('DB_PATH', None)

    def test_get_budget_caps_returns_empty_when_no_db(self):
        """Should return default caps when no DB."""
        os.environ.pop('DB_PATH', None)
        caps = get_budget_caps()
        assert caps.global_monthly_cap_kzt == 0.0
        assert caps.per_draft_cap_kzt == 0.0

    def test_set_and_get_budget_caps(self, temp_db):
        """Should save and retrieve budget caps."""
        set_budget_caps(
            global_monthly_cap_kzt=10_000_000,
            per_draft_cap_kzt=2_000_000,
        )

        caps = get_budget_caps()
        assert caps.global_monthly_cap_kzt == 10_000_000
        assert caps.per_draft_cap_kzt == 2_000_000

    def test_set_partial_budget_caps(self, temp_db):
        """Should update only specified caps."""
        # Set initial
        set_budget_caps(
            global_monthly_cap_kzt=10_000_000,
            per_draft_cap_kzt=2_000_000,
        )

        # Update only global
        set_budget_caps(global_monthly_cap_kzt=15_000_000)

        caps = get_budget_caps()
        assert caps.global_monthly_cap_kzt == 15_000_000
        assert caps.per_draft_cap_kzt == 2_000_000  # Unchanged


class TestCheckAllGuardrails:
    """Tests for unified guardrail check."""

    def test_all_pass(self):
        """Should PASS when all guardrails pass."""
        result = check_all_guardrails(
            roic=0.25,  # 25% - ORDER_FULL
            po_value_kzt=100_000,
            skip_concentration=True,  # Skip for simplicity
            skip_budget=True,
        )
        assert result.status == GuardrailStatus.PASS
        assert result.approved is True
        assert len(result.blockers) == 0
        assert len(result.warnings) == 0

    def test_warn_on_roic_flag(self):
        """Should WARN when ROIC triggers flag."""
        result = check_all_guardrails(
            roic=0.15,  # 15% - ORDER_WITH_FLAG
            skip_concentration=True,
            skip_budget=True,
        )
        assert result.status == GuardrailStatus.WARN
        assert result.approved is True
        assert len(result.warnings) > 0
        assert result.roic_action == ROICAction.ORDER_WITH_FLAG

    def test_block_on_low_roic(self):
        """Should BLOCK when ROIC too low."""
        result = check_all_guardrails(
            roic=0.05,  # 5% - REVIEW_REQUIRED
            skip_concentration=True,
            skip_budget=True,
        )
        assert result.status == GuardrailStatus.BLOCK
        assert result.approved is False
        assert len(result.blockers) > 0
        assert result.roic_action == ROICAction.REVIEW_REQUIRED

    def test_block_on_concentration_violation(self):
        """Should BLOCK on concentration violation."""
        result = check_all_guardrails(
            roic=0.25,  # ROIC OK
            proposed_po={'SKU1': 1000},
            current_inventory={'SKU1': 0, 'SKU2': 100},
            unit_costs={'SKU1': 1000, 'SKU2': 1000},
            skip_budget=True,
        )
        assert result.status == GuardrailStatus.BLOCK
        assert result.approved is False
        assert result.concentration_valid is False
        assert result.adjusted_po is not None

    def test_block_on_budget_violation(self):
        """Should BLOCK on budget cap violation."""
        caps = BudgetCaps(per_draft_cap_kzt=500_000)
        result = check_all_guardrails(
            roic=0.25,  # ROIC OK
            po_value_kzt=1_000_000,  # Over cap
            budget_caps=caps,
            skip_concentration=True,
        )
        assert result.status == GuardrailStatus.BLOCK
        assert result.approved is False
        assert result.budget_valid is False

    def test_multiple_blockers(self):
        """Should collect multiple blockers."""
        caps = BudgetCaps(per_draft_cap_kzt=500_000)
        result = check_all_guardrails(
            roic=0.05,  # ROIC blocker
            po_value_kzt=1_000_000,  # Budget blocker
            budget_caps=caps,
            skip_concentration=True,
        )
        assert result.status == GuardrailStatus.BLOCK
        assert result.approved is False
        assert len(result.blockers) >= 2

    def test_skip_flags(self):
        """Should respect skip flags."""
        result = check_all_guardrails(
            roic=0.05,  # Would block
            po_value_kzt=100_000_000,  # Would block with caps
            skip_roic=True,
            skip_concentration=True,
            skip_budget=True,
        )
        assert result.status == GuardrailStatus.PASS
        assert result.approved is True


class TestGuardrailResult:
    """Tests for GuardrailResult dataclass."""

    def test_has_warnings_property(self):
        """Should correctly report warnings."""
        result = GuardrailResult(
            status=GuardrailStatus.WARN,
            approved=True,
            warnings=["Test warning"],
        )
        assert result.has_warnings is True
        assert result.has_blockers is False

    def test_has_blockers_property(self):
        """Should correctly report blockers."""
        result = GuardrailResult(
            status=GuardrailStatus.BLOCK,
            approved=False,
            blockers=["Test blocker"],
        )
        assert result.has_blockers is True

    def test_empty_result(self):
        """Empty result should have no warnings or blockers."""
        result = GuardrailResult(
            status=GuardrailStatus.PASS,
            approved=True,
        )
        assert result.has_warnings is False
        assert result.has_blockers is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
