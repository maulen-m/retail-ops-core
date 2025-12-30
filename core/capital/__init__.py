"""
Capital management modules.

Provides:
- guardrails: Capital guardrails (20% rule, ROIC gate, budget caps)
"""

from .guardrails import (
    # Main unified check
    check_all_guardrails,
    GuardrailResult,
    # Individual checks
    check_roic_gate,
    check_concentration_rule,
    check_budget_cap,
    # Budget management
    get_budget_caps,
    set_budget_caps,
    BudgetCaps,
    # Enums
    GuardrailStatus,
)

__all__ = [
    # Main
    "check_all_guardrails",
    "GuardrailResult",
    # Individual checks
    "check_roic_gate",
    "check_concentration_rule",
    "check_budget_cap",
    # Budget
    "get_budget_caps",
    "set_budget_caps",
    "BudgetCaps",
    # Enums
    "GuardrailStatus",
]
