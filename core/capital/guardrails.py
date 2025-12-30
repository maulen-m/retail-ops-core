"""
Capital Guardrails — Unified Safety Controls for PO Approval

This module provides the canonical capital guardrails for PO approval.
All scripts should use these functions instead of implementing their own checks.

GUARDRAILS:

1. ROIC Gate (3-tier):
   - >= 20%: ORDER_FULL (auto-approve)
   - 10-20%: ORDER_WITH_FLAG (approve with review flag)
   - < 10%: REVIEW_REQUIRED (block order)

2. Concentration Rule (20% max):
   - No single SKU can exceed 20% of total portfolio capital
   - Proposed PO is validated before approval

3. Budget Caps:
   - Global monthly cap: Maximum spend across all POs
   - Per-draft cap: Maximum single PO value
   - Stored in DB (dim_budget_caps) for auditability

USAGE:
    from core.capital.guardrails import (
        check_all_guardrails,
        GuardrailResult,
    )

    result = check_all_guardrails(
        roic=0.18,
        po_value_kzt=500_000,
        proposed_po={'LINE52': 100},
        current_inventory={'LINE52': 500},
        unit_costs={'LINE52': 5000},
    )

    if result.approved:
        execute_po()
    else:
        handle_rejection(result.blockers)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import sqlite3
from pathlib import Path
import os

# Re-export from existing modules
from core.calc.size_allocation import (
    ROICAction,
    apply_roic_gate as _apply_roic_gate,
)
from core.calc.capital_optimizer import (
    check_concentration_rule as _check_concentration_rule,
)


class GuardrailStatus(Enum):
    """
    Overall guardrail check status.

    PASS: All guardrails passed
    WARN: Passed but with warnings (e.g., ROIC flag)
    BLOCK: Failed one or more guardrails
    """
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass
class BudgetCaps:
    """
    Budget cap configuration.

    Attributes:
        global_monthly_cap_kzt: Maximum monthly spend (0 = unlimited)
        per_draft_cap_kzt: Maximum single PO value (0 = unlimited)
        current_month_spend_kzt: Amount already spent this month
    """
    global_monthly_cap_kzt: float = 0.0  # 0 = unlimited
    per_draft_cap_kzt: float = 0.0  # 0 = unlimited
    current_month_spend_kzt: float = 0.0


@dataclass
class GuardrailResult:
    """
    Result of unified guardrail check.

    Attributes:
        status: Overall status (PASS, WARN, BLOCK)
        approved: Whether the PO can proceed
        blockers: List of blocking issues
        warnings: List of warning issues
        roic_action: ROIC gate result
        concentration_valid: 20% rule result
        budget_valid: Budget cap result
        adjusted_po: PO with any concentration adjustments
    """
    status: GuardrailStatus
    approved: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Individual check results
    roic_action: Optional[ROICAction] = None
    concentration_valid: bool = True
    budget_valid: bool = True

    # Adjustments
    adjusted_po: Optional[dict] = None

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_blockers(self) -> bool:
        return len(self.blockers) > 0


def get_db_path() -> Optional[Path]:
    """Get the database path from environment."""
    db_path = os.environ.get("DB_PATH")
    if db_path:
        return Path(db_path)
    return None


def get_budget_caps() -> BudgetCaps:
    """
    Get current budget caps from database.

    Returns:
        BudgetCaps with current configuration

    Example:
        >>> caps = get_budget_caps()
        >>> print(f"Monthly cap: {caps.global_monthly_cap_kzt:,.0f} KZT")
    """
    db_path = get_db_path()
    if not db_path or not db_path.exists():
        return BudgetCaps()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='dim_budget_caps'
        """)
        if not cursor.fetchone():
            conn.close()
            return BudgetCaps()

        # Get active caps
        cursor.execute("""
            SELECT global_monthly_cap_kzt, per_draft_cap_kzt
            FROM dim_budget_caps
            WHERE active_flag = 1
            ORDER BY effective_date DESC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if row:
            caps = BudgetCaps(
                global_monthly_cap_kzt=row[0] or 0.0,
                per_draft_cap_kzt=row[1] or 0.0,
            )
        else:
            caps = BudgetCaps()

        # Get current month spend
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='fact_po_spend'
        """)
        if cursor.fetchone():
            cursor.execute("""
                SELECT COALESCE(SUM(total_value_kzt), 0)
                FROM fact_po_spend
                WHERE strftime('%Y-%m', spend_date) = strftime('%Y-%m', 'now')
            """)
            spend_row = cursor.fetchone()
            caps.current_month_spend_kzt = spend_row[0] if spend_row else 0.0

        conn.close()
        return caps

    except sqlite3.Error:
        return BudgetCaps()


def set_budget_caps(
    global_monthly_cap_kzt: Optional[float] = None,
    per_draft_cap_kzt: Optional[float] = None,
) -> bool:
    """
    Set budget caps in database.

    Args:
        global_monthly_cap_kzt: Maximum monthly spend (None = keep current)
        per_draft_cap_kzt: Maximum single PO value (None = keep current)

    Returns:
        True if successful, False otherwise

    Example:
        >>> set_budget_caps(
        ...     global_monthly_cap_kzt=10_000_000,
        ...     per_draft_cap_kzt=2_000_000,
        ... )
    """
    db_path = get_db_path()
    if not db_path:
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_budget_caps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                global_monthly_cap_kzt REAL,
                per_draft_cap_kzt REAL,
                effective_date TEXT DEFAULT (date('now')),
                active_flag INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                notes TEXT
            )
        """)

        # Deactivate previous caps
        cursor.execute("UPDATE dim_budget_caps SET active_flag = 0")

        # Get current values for any not provided
        current = get_budget_caps()
        global_cap = global_monthly_cap_kzt if global_monthly_cap_kzt is not None else current.global_monthly_cap_kzt
        draft_cap = per_draft_cap_kzt if per_draft_cap_kzt is not None else current.per_draft_cap_kzt

        # Insert new caps
        cursor.execute("""
            INSERT INTO dim_budget_caps (global_monthly_cap_kzt, per_draft_cap_kzt)
            VALUES (?, ?)
        """, (global_cap, draft_cap))

        conn.commit()
        conn.close()
        return True

    except sqlite3.Error:
        return False


def check_roic_gate(
    roic: float,
    order_qty: int = 100,
) -> tuple[ROICAction, str]:
    """
    Check ROIC gate for PO approval.

    This is the canonical ROIC check. Re-exports from size_allocation.

    Args:
        roic: Monthly ROIC as a decimal (e.g., 0.18 = 18%)
        order_qty: Order quantity (for gating)

    Returns:
        Tuple of (ROICAction, explanation)

    Gates:
        >= 20%: ORDER_FULL (auto-approve)
        10-20%: ORDER_WITH_FLAG (approve with review flag)
        < 10%: REVIEW_REQUIRED (manual approval needed)
    """
    action, gated_qty = _apply_roic_gate(roic, order_qty)

    if action == ROICAction.ORDER_FULL:
        return action, f"ROIC {roic*100:.1f}% >= 20%: Auto-approved"
    elif action == ROICAction.ORDER_WITH_FLAG:
        return action, f"ROIC {roic*100:.1f}% in 10-20%: Approved with review flag"
    else:
        return action, f"ROIC {roic*100:.1f}% < 10%: Manual review required"


def check_concentration_rule(
    proposed_po: dict,
    current_inventory: dict,
    unit_costs: dict,
    max_concentration: float = 0.20,
) -> tuple[bool, str, Optional[dict]]:
    """
    Check 20% concentration rule.

    This is the canonical concentration check. Re-exports from capital_optimizer.

    Args:
        proposed_po: {sku_key: qty}
        current_inventory: {sku_key: units}
        unit_costs: {sku_key: cogs_kzt}
        max_concentration: Maximum share per SKU (default: 20%)

    Returns:
        Tuple of (valid, explanation, adjusted_po)
        - valid: True if no violations
        - explanation: Human-readable result
        - adjusted_po: PO with adjustments (None if valid)

    Example:
        >>> valid, reason, adj = check_concentration_rule(
        ...     proposed_po={'SKU1': 1000},
        ...     current_inventory={'SKU1': 500, 'SKU2': 2000},
        ...     unit_costs={'SKU1': 1000, 'SKU2': 1000},
        ... )
    """
    result = _check_concentration_rule(
        proposed_po=proposed_po,
        current_inventory=current_inventory,
        unit_costs=unit_costs,
        max_concentration=max_concentration,
    )

    if result['valid']:
        return True, "Concentration check passed (all SKUs < 20%)", None
    else:
        violations = result['violations']
        sku_list = ", ".join(v['sku_key'] for v in violations)
        return (
            False,
            f"Concentration violation: {sku_list} exceed {max_concentration*100:.0f}% cap",
            result['adjusted_po'],
        )


def check_budget_cap(
    po_value_kzt: float,
    caps: Optional[BudgetCaps] = None,
) -> tuple[bool, str]:
    """
    Check if PO value fits within budget caps.

    Args:
        po_value_kzt: Total PO value in KZT
        caps: Budget caps (default: load from DB)

    Returns:
        Tuple of (valid, explanation)

    Checks:
        1. Per-draft cap: Is this PO too large?
        2. Monthly cap: Would this exceed monthly budget?

    Example:
        >>> valid, reason = check_budget_cap(500_000)
    """
    if caps is None:
        caps = get_budget_caps()

    # Check per-draft cap
    if caps.per_draft_cap_kzt > 0 and po_value_kzt > caps.per_draft_cap_kzt:
        return (
            False,
            f"PO value {po_value_kzt:,.0f} KZT exceeds per-draft cap "
            f"({caps.per_draft_cap_kzt:,.0f} KZT)"
        )

    # Check monthly cap
    if caps.global_monthly_cap_kzt > 0:
        projected_spend = caps.current_month_spend_kzt + po_value_kzt
        if projected_spend > caps.global_monthly_cap_kzt:
            remaining = caps.global_monthly_cap_kzt - caps.current_month_spend_kzt
            return (
                False,
                f"PO value {po_value_kzt:,.0f} KZT would exceed monthly cap "
                f"(remaining: {remaining:,.0f} KZT)"
            )

    return True, "Budget check passed"


def check_all_guardrails(
    roic: float = 0.0,
    po_value_kzt: float = 0.0,
    proposed_po: Optional[dict] = None,
    current_inventory: Optional[dict] = None,
    unit_costs: Optional[dict] = None,
    order_qty: int = 100,
    budget_caps: Optional[BudgetCaps] = None,
    skip_roic: bool = False,
    skip_concentration: bool = False,
    skip_budget: bool = False,
    require_costs: bool = True,
) -> GuardrailResult:
    """
    Run all capital guardrails and return unified result.

    This is the main entry point for PO approval checks.

    IMPORTANT: Missing critical inputs now BLOCK by default (Part 3 requirement).
    Set require_costs=False to allow fallback behavior (not recommended for production).

    Args:
        roic: Monthly ROIC as a decimal
        po_value_kzt: Total PO value in KZT (can be computed from proposed_po + unit_costs)
        proposed_po: {sku_key: qty}
        current_inventory: {sku_key: units}
        unit_costs: {sku_key: cogs_kzt}
        order_qty: Order quantity for ROIC gate
        budget_caps: Budget caps (default: load from DB)
        skip_roic: Skip ROIC check
        skip_concentration: Skip concentration check
        skip_budget: Skip budget check
        require_costs: If True, BLOCK when unit_costs missing for concentration check

    Returns:
        GuardrailResult with overall status and details

    Example:
        >>> result = check_all_guardrails(
        ...     roic=0.18,
        ...     po_value_kzt=500_000,
        ...     proposed_po={'LINE52': 100},
        ...     current_inventory={'LINE52': 500, 'PRINT52': 1000},
        ...     unit_costs={'LINE52': 5000, 'PRINT52': 4000},
        ... )
        >>> if result.approved:
        ...     print("PO approved!")
        >>> else:
        ...     print(f"Blocked: {result.blockers}")
    """
    blockers = []
    warnings = []
    roic_action = None
    concentration_valid = True
    budget_valid = True
    adjusted_po = None

    # 1. ROIC Gate
    if not skip_roic:
        roic_action, roic_reason = check_roic_gate(roic, order_qty)

        if roic_action == ROICAction.REVIEW_REQUIRED:
            blockers.append(roic_reason)
        elif roic_action == ROICAction.ORDER_WITH_FLAG:
            warnings.append(roic_reason)

    # 2. Concentration Rule (20%)
    # Part 3 requirement: BLOCK if critical inputs are missing (not silently skip)
    if not skip_concentration:
        missing_inputs = []
        if not proposed_po:
            missing_inputs.append("proposed_po")
        if not current_inventory:
            missing_inputs.append("current_inventory")
        if not unit_costs:
            missing_inputs.append("unit_costs")

        if missing_inputs:
            if require_costs:
                blockers.append(
                    f"Concentration check BLOCKED: missing {', '.join(missing_inputs)}. "
                    "Cannot validate 20% rule without cost data."
                )
                concentration_valid = False
            else:
                warnings.append(
                    f"Concentration check SKIPPED: missing {', '.join(missing_inputs)}"
                )
        else:
            conc_valid, conc_reason, conc_adjusted = check_concentration_rule(
                proposed_po=proposed_po,
                current_inventory=current_inventory,
                unit_costs=unit_costs,
            )
            concentration_valid = conc_valid

            if not conc_valid:
                blockers.append(conc_reason)
                adjusted_po = conc_adjusted

    # 3. Budget Caps
    # Compute po_value_kzt from proposed_po + unit_costs if not provided
    effective_po_value = po_value_kzt
    if effective_po_value == 0 and proposed_po and unit_costs:
        effective_po_value = sum(
            qty * unit_costs.get(sku, 0)
            for sku, qty in proposed_po.items()
        )

    if not skip_budget and effective_po_value > 0:
        budget_valid, budget_reason = check_budget_cap(effective_po_value, budget_caps)

        if not budget_valid:
            blockers.append(budget_reason)

    # Determine overall status
    if blockers:
        status = GuardrailStatus.BLOCK
        approved = False
    elif warnings:
        status = GuardrailStatus.WARN
        approved = True
    else:
        status = GuardrailStatus.PASS
        approved = True

    return GuardrailResult(
        status=status,
        approved=approved,
        blockers=blockers,
        warnings=warnings,
        roic_action=roic_action,
        concentration_valid=concentration_valid,
        budget_valid=budget_valid,
        adjusted_po=adjusted_po,
    )


@dataclass
class SKUGuardrailResult:
    """
    Per-SKU guardrail check result for dashboard/auto-PO output.

    Attributes:
        sku_key: SKU identifier
        approved: Whether PO for this SKU can proceed
        guardrail_status: Overall status (PASS, WARN, BLOCK)
        roic_status: ROIC gate result string
        concentration_status: Concentration check result string
        budget_status: Budget check result string
        blockers: List of blocking reasons
        warnings: List of warning reasons
        adjusted_qty: Suggested quantity if concentration violated
    """
    sku_key: str
    approved: bool
    guardrail_status: str  # PASS, WARN, BLOCK
    roic_status: str
    concentration_status: str = "NOT_CHECKED"
    budget_status: str = "NOT_CHECKED"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adjusted_qty: Optional[int] = None


def check_sku_guardrails(
    sku_key: str,
    roic: float,
    order_qty: int,
    po_value_kzt: float = 0.0,
    unit_cost_kzt: float = 0.0,
    total_portfolio_value_kzt: float = 0.0,
    sku_share_pct: float = 0.0,
    budget_caps: Optional[BudgetCaps] = None,
    skip_concentration: bool = True,  # Default True for per-SKU (aggregated check at PO level)
) -> SKUGuardrailResult:
    """
    Check guardrails for a single SKU.

    Used by dashboard and auto-PO to generate per-SKU guardrail status.

    Args:
        sku_key: SKU identifier
        roic: Monthly ROIC for this SKU
        order_qty: Proposed order quantity
        po_value_kzt: PO value for this SKU in KZT
        unit_cost_kzt: Unit COGS in KZT (for value calculation)
        total_portfolio_value_kzt: Total portfolio value (for concentration)
        sku_share_pct: This SKU's share of portfolio (0-1)
        budget_caps: Budget caps (for per-draft cap check)
        skip_concentration: Skip concentration (usually done at PO level)

    Returns:
        SKUGuardrailResult with per-SKU guardrail status
    """
    blockers = []
    warnings = []

    # 1. ROIC Gate
    roic_action, roic_reason = check_roic_gate(roic, order_qty)

    if roic_action == ROICAction.ORDER_FULL:
        roic_status = "PASS"
    elif roic_action == ROICAction.ORDER_WITH_FLAG:
        roic_status = "WARN"
        warnings.append(roic_reason)
    else:
        roic_status = "BLOCK"
        blockers.append(roic_reason)

    # 2. Concentration (simple share check, full check at PO level)
    concentration_status = "NOT_CHECKED"
    adjusted_qty = None
    if not skip_concentration and total_portfolio_value_kzt > 0:
        if sku_share_pct > 0.20:
            concentration_status = "BLOCK"
            blockers.append(
                f"SKU {sku_key} would be {sku_share_pct*100:.1f}% of portfolio (max 20%)"
            )
            # Calculate adjusted quantity to fit under 20%
            max_value = total_portfolio_value_kzt * 0.20
            if unit_cost_kzt > 0:
                adjusted_qty = int(max_value / unit_cost_kzt)
        else:
            concentration_status = "PASS"

    # 3. Budget (per-SKU value check)
    budget_status = "NOT_CHECKED"
    if po_value_kzt > 0 or (order_qty > 0 and unit_cost_kzt > 0):
        effective_value = po_value_kzt or (order_qty * unit_cost_kzt)
        caps = budget_caps or get_budget_caps()

        # Only check per-draft cap at SKU level (monthly cap checked at PO level)
        if caps.per_draft_cap_kzt > 0 and effective_value > caps.per_draft_cap_kzt:
            budget_status = "BLOCK"
            blockers.append(
                f"SKU PO value {effective_value:,.0f} KZT exceeds per-draft cap "
                f"({caps.per_draft_cap_kzt:,.0f} KZT)"
            )
        else:
            budget_status = "PASS"

    # Determine overall status
    if blockers:
        guardrail_status = "BLOCK"
        approved = False
    elif warnings:
        guardrail_status = "WARN"
        approved = True
    else:
        guardrail_status = "PASS"
        approved = True

    return SKUGuardrailResult(
        sku_key=sku_key,
        approved=approved,
        guardrail_status=guardrail_status,
        roic_status=roic_status,
        concentration_status=concentration_status,
        budget_status=budget_status,
        blockers=blockers,
        warnings=warnings,
        adjusted_qty=adjusted_qty,
    )


@dataclass
class FallbackLog:
    """
    Track fallback usage for run summary/alerts.

    Attributes:
        fx_fallback: True if FX rates fell back to defaults
        vat_fallback: True if VAT rate fell back to default
        demand_override_count: Number of SKUs with demand overrides active
        budget_caps_active: True if budget caps are configured
        notes: Additional notes about fallbacks
    """
    fx_fallback: bool = False
    fx_source: str = "DB"
    vat_fallback: bool = False
    demand_override_count: int = 0
    budget_caps_active: bool = False
    notes: list[str] = field(default_factory=list)

    def to_summary(self) -> str:
        """Generate human-readable summary for logs/alerts."""
        lines = []
        if self.fx_fallback:
            lines.append(f"⚠️ FX rates using FALLBACK defaults (source: {self.fx_source})")
        if self.vat_fallback:
            lines.append("⚠️ VAT rate using FALLBACK default")
        if self.demand_override_count > 0:
            lines.append(f"📌 {self.demand_override_count} SKU demand override(s) active")
        if self.budget_caps_active:
            lines.append("💰 Budget caps are active")
        if self.notes:
            lines.extend(self.notes)
        return "\n".join(lines) if lines else "✅ All parameters from DB, no fallbacks"


def check_fallback_usage(db_path: Optional[Path] = None) -> FallbackLog:
    """
    Check if any parameters are using fallback defaults.

    Part 3 requirement: Log and surface fallback usage in run summary.

    Returns:
        FallbackLog with details about fallback usage
    """
    from core.config.business_params import get_fx_rates, get_demand_overrides

    log = FallbackLog()

    # Check FX rates
    fx_rates = get_fx_rates()
    if fx_rates.source == "FALLBACK":
        log.fx_fallback = True
        log.fx_source = "FALLBACK"
        log.notes.append(
            f"FX defaults: CNY/KZT={fx_rates.cny_kzt}, "
            f"USD/KZT={fx_rates.usd_kzt}, DLV={fx_rates.dlv_rate_usd_kg}"
        )
    else:
        log.fx_source = fx_rates.source

    # Check demand overrides
    overrides = get_demand_overrides()
    log.demand_override_count = len(overrides)

    # Check budget caps
    caps = get_budget_caps()
    if caps.global_monthly_cap_kzt > 0 or caps.per_draft_cap_kzt > 0:
        log.budget_caps_active = True
        log.notes.append(
            f"Budget caps: monthly={caps.global_monthly_cap_kzt:,.0f} KZT, "
            f"per-draft={caps.per_draft_cap_kzt:,.0f} KZT"
        )

    return log


if __name__ == "__main__":
    # Quick sanity check
    print("Capital Guardrails - Sanity Check")
    print("=" * 50)

    # Test ROIC gate
    print("\n1. ROIC Gate Tests:")
    for roic in [0.25, 0.15, 0.05]:
        action, reason = check_roic_gate(roic)
        print(f"   ROIC {roic*100:.0f}%: {action.value} - {reason}")

    # Test concentration rule
    print("\n2. Concentration Rule Test:")
    valid, reason, adj = check_concentration_rule(
        proposed_po={'SKU1': 100},
        current_inventory={'SKU1': 0, 'SKU2': 100},
        unit_costs={'SKU1': 1000, 'SKU2': 1000},
    )
    print(f"   Valid: {valid}, Reason: {reason}")

    # Test unified check
    print("\n3. Unified Check:")
    result = check_all_guardrails(
        roic=0.18,
        po_value_kzt=500_000,
        proposed_po={'SKU1': 100},
        current_inventory={'SKU1': 500, 'SKU2': 1000},
        unit_costs={'SKU1': 5000, 'SKU2': 4000},
    )
    print(f"   Status: {result.status.value}")
    print(f"   Approved: {result.approved}")
    if result.warnings:
        print(f"   Warnings: {result.warnings}")
    if result.blockers:
        print(f"   Blockers: {result.blockers}")
