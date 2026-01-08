#!/usr/bin/env python3
"""
PO Draft Executor - Part 5: Partial Auto (ORDER_FULL only)
Part 6: Adds execution reconciliation artifact
Part 7: Adds rollout safety caps and SKU whitelist

Safely executes approved PO draft lines with full guardrail re-validation.

SAFETY REQUIREMENTS (Non-negotiables):
- BLOCKS on ANY guardrail blocker (capital protection first)
- Only executes ORDER_FULL lines (>=20% ROIC)
- Re-runs guardrails before execution (idempotent)
- Records all execution attempts in fact_run_steps
- Gate behind FOUR env vars (must ALL be enabled):
  - AUTONOMOUS_PO_ENABLED=true
  - PO_DRAFT_ONLY=false
  - AUTO_EXECUTE_MODE=ORDER_FULL_ONLY

Part 6 additions:
- Creates execution reconciliation CSV: exports/execution_reconciliation_YYYY-MM-DD.csv
- Shows draft spend vs executed spend, executed qty per SKU, skipped lines
- Persists artifact path to fact_run_steps

Part 7 additions:
- Optional spend caps (env vars):
  - MAX_EXECUTE_SPEND_PER_DAY_KZT: Max total spend per day across all drafts
  - MAX_EXECUTE_SPEND_PER_DRAFT_KZT: Max spend per single draft execution
- Optional SKU whitelist:
  - ROLLOUT_SKU_WHITELIST_PATH: Path to file with whitelisted SKU keys
  - Or via dim_rollout_whitelist table in database
- Rollback safety: caps are fail-safe (block execution if exceeded)

Usage:
    # Default dry-run (no writes)
    python scripts/execute_po_draft.py --draft-id 123

    # Execute approved ORDER_FULL lines (requires PO_WRITE_ENABLED=true)
    python scripts/execute_po_draft.py --draft-id 123 --execute

    # Execute with explicit approval ID
    python scripts/execute_po_draft.py --draft-id 123 --approval-id 456 --execute

    # Check rollout status (caps, whitelist, daily spend)
    python scripts/execute_po_draft.py --check-rollout
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.capital.guardrails import (
    check_sku_guardrails,
    check_all_guardrails,
    ROICAction,
    GuardrailResult,
)
from core.config.business_params import get_fx_rates
from core.tracking.run_tracker import RunTracker
from core.alerts.error_alerts import send_error_alert

DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXPORTS_DIR = PROJECT_ROOT / "exports"

# =============================================================================
# SAFETY GATES (Part 5 requirement)
# =============================================================================

# Kill switch for autonomy
AUTONOMOUS_PO_ENABLED = os.environ.get("AUTONOMOUS_PO_ENABLED", "false").lower() == "true"

# Draft-only mode (must be false to allow execution)
PO_DRAFT_ONLY = os.environ.get("PO_DRAFT_ONLY", "true").lower() == "true"

# Auto-execute mode: DISABLED, ORDER_FULL_ONLY, ASSISTED
AUTO_EXECUTE_MODE = os.environ.get("AUTO_EXECUTE_MODE", "DISABLED").upper()

# Explicit write enable (required for any live execution)
PO_WRITE_ENABLED = os.environ.get("PO_WRITE_ENABLED", "false").lower() == "true"

# =============================================================================
# PART 7: ROLLOUT SAFETY CAPS
# =============================================================================

# Optional spend caps (0 = no limit)
MAX_EXECUTE_SPEND_PER_DAY_KZT = float(os.environ.get("MAX_EXECUTE_SPEND_PER_DAY_KZT", "0"))
MAX_EXECUTE_SPEND_PER_DRAFT_KZT = float(os.environ.get("MAX_EXECUTE_SPEND_PER_DRAFT_KZT", "0"))

# Optional SKU whitelist file path
ROLLOUT_SKU_WHITELIST_PATH = os.environ.get("ROLLOUT_SKU_WHITELIST_PATH", "")


def get_daily_executed_spend(db_path: Path, execution_date: date = None) -> float:
    """
    Get total executed spend for a given day (Part 7).

    Used to enforce MAX_EXECUTE_SPEND_PER_DAY_KZT cap.

    Args:
        db_path: Path to database
        execution_date: Date to check (defaults to today)

    Returns:
        Total executed spend in KZT for the day
    """
    if execution_date is None:
        execution_date = date.today()

    date_str = execution_date.isoformat()

    conn = sqlite3.connect(str(db_path))

    # Check if table exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_executions'"
    ).fetchall()

    if not tables:
        conn.close()
        return 0.0

    row = conn.execute("""
        SELECT COALESCE(SUM(total_value_kzt), 0)
        FROM fact_po_executions
        WHERE date(executed_at) = ?
          AND status = 'SUCCESS'
    """, (date_str,)).fetchone()

    conn.close()
    return float(row[0]) if row else 0.0


def get_rollout_whitelist(db_path: Path) -> set[str]:
    """
    Get the set of whitelisted SKU keys for rollout (Part 7).

    Checks in order:
    1. ROLLOUT_SKU_WHITELIST_PATH env var (file path)
    2. dim_rollout_whitelist table in database

    Returns:
        Set of whitelisted sku_key values.
        Empty set means no whitelist active (all SKUs allowed).
    """
    whitelist = set()

    # 1. Check file path first
    if ROLLOUT_SKU_WHITELIST_PATH:
        whitelist_path = Path(ROLLOUT_SKU_WHITELIST_PATH)
        if not whitelist_path.is_absolute():
            whitelist_path = PROJECT_ROOT / whitelist_path

        if whitelist_path.exists():
            try:
                with open(whitelist_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            whitelist.add(line)
                return whitelist
            except Exception:
                pass

    # 2. Check database table
    try:
        conn = sqlite3.connect(str(db_path))

        # Check if table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_rollout_whitelist'"
        ).fetchall()

        if tables:
            rows = conn.execute("""
                SELECT sku_key FROM dim_rollout_whitelist
                WHERE active_flag = 1
            """).fetchall()
            whitelist = {row[0] for row in rows}

        conn.close()
    except Exception:
        pass

    return whitelist


def check_rollout_caps(
    db_path: Path,
    proposed_spend_kzt: float,
) -> tuple[bool, list[str]]:
    """
    Check rollout safety caps (Part 7).

    Args:
        db_path: Path to database
        proposed_spend_kzt: Total proposed spend for this execution

    Returns:
        (can_execute, blockers_list)
    """
    blockers = []

    # Check per-draft cap
    if MAX_EXECUTE_SPEND_PER_DRAFT_KZT > 0:
        if proposed_spend_kzt > MAX_EXECUTE_SPEND_PER_DRAFT_KZT:
            blockers.append(
                f"Draft spend {proposed_spend_kzt:,.0f} KZT exceeds MAX_EXECUTE_SPEND_PER_DRAFT_KZT ({MAX_EXECUTE_SPEND_PER_DRAFT_KZT:,.0f} KZT)"
            )

    # Check daily cap
    if MAX_EXECUTE_SPEND_PER_DAY_KZT > 0:
        daily_executed = get_daily_executed_spend(db_path)
        remaining = MAX_EXECUTE_SPEND_PER_DAY_KZT - daily_executed

        if proposed_spend_kzt > remaining:
            blockers.append(
                f"Daily cap: {daily_executed:,.0f} KZT already executed today. "
                f"Proposed {proposed_spend_kzt:,.0f} KZT would exceed MAX_EXECUTE_SPEND_PER_DAY_KZT ({MAX_EXECUTE_SPEND_PER_DAY_KZT:,.0f} KZT)"
            )

    return len(blockers) == 0, blockers


def filter_by_whitelist(
    lines: list[dict],
    whitelist: set[str],
) -> tuple[list[dict], list[dict]]:
    """
    Filter lines by SKU whitelist (Part 7).

    Args:
        lines: List of draft line dicts with 'sku_key'
        whitelist: Set of allowed SKU keys (empty = no filtering)

    Returns:
        (whitelisted_lines, non_whitelisted_lines)
    """
    if not whitelist:
        # No whitelist active - allow all
        return lines, []

    whitelisted = []
    filtered = []

    for line in lines:
        sku_key = line.get('sku_key', '')
        if sku_key in whitelist:
            whitelisted.append(line)
        else:
            filtered.append(line)

    return whitelisted, filtered


def get_rollout_status(db_path: Path) -> dict:
    """
    Get current rollout status for display (Part 7).

    Returns dict with:
        - caps_enabled: bool
        - daily_cap_kzt: float
        - draft_cap_kzt: float
        - daily_executed_kzt: float
        - daily_remaining_kzt: float
        - whitelist_enabled: bool
        - whitelist_count: int
    """
    daily_executed = get_daily_executed_spend(db_path)
    whitelist = get_rollout_whitelist(db_path)

    daily_remaining = 0.0
    if MAX_EXECUTE_SPEND_PER_DAY_KZT > 0:
        daily_remaining = max(0, MAX_EXECUTE_SPEND_PER_DAY_KZT - daily_executed)

    return {
        "caps_enabled": MAX_EXECUTE_SPEND_PER_DAY_KZT > 0 or MAX_EXECUTE_SPEND_PER_DRAFT_KZT > 0,
        "daily_cap_kzt": MAX_EXECUTE_SPEND_PER_DAY_KZT,
        "draft_cap_kzt": MAX_EXECUTE_SPEND_PER_DRAFT_KZT,
        "daily_executed_kzt": daily_executed,
        "daily_remaining_kzt": daily_remaining,
        "whitelist_enabled": len(whitelist) > 0,
        "whitelist_count": len(whitelist),
        "whitelist_path": ROLLOUT_SKU_WHITELIST_PATH or None,
    }


@dataclass
class ExecutionResult:
    """Result of PO execution attempt."""
    draft_id: int
    status: str  # SUCCESS, BLOCKED, DISABLED, ERROR, IDEMPOTENT
    executed_lines: int = 0
    skipped_lines: int = 0
    blocked_lines: int = 0
    total_value_kzt: float = 0.0
    draft_value_kzt: float = 0.0  # Part 6: Original draft total value
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    execution_id: Optional[int] = None
    # Part 6: Reconciliation data
    executed_sku_details: list = field(default_factory=list)  # [{sku_key, qty, value_kzt}]
    skipped_sku_details: list = field(default_factory=list)   # [{sku_key, qty, value_kzt, reason}]
    reconciliation_path: Optional[str] = None
    # Part 7: Rollout caps data
    whitelist_filtered_lines: int = 0  # Lines filtered by whitelist
    cap_blocked: bool = False  # True if blocked by spend caps
    # Part 4: Write audit metadata
    correlation_id: Optional[str] = None
    rollback_steps: list[str] = field(default_factory=list)


def check_execution_gates(require_write: bool = False) -> tuple[bool, list[str]]:
    """
    Check all execution safety gates.

    Args:
        require_write: If True, also require PO_WRITE_ENABLED=true.

    Returns:
        (can_execute, reasons_if_blocked)
    """
    blockers = []

    if not AUTONOMOUS_PO_ENABLED:
        blockers.append("AUTONOMOUS_PO_ENABLED is not set to 'true'")

    if PO_DRAFT_ONLY:
        blockers.append("PO_DRAFT_ONLY is 'true' (must be 'false' to execute)")

    if AUTO_EXECUTE_MODE not in ("ORDER_FULL_ONLY", "ASSISTED"):
        blockers.append(f"AUTO_EXECUTE_MODE is '{AUTO_EXECUTE_MODE}' (must be 'ORDER_FULL_ONLY' or 'ASSISTED')")

    if require_write and not PO_WRITE_ENABLED:
        blockers.append("PO_WRITE_ENABLED is not set to 'true'")

    return len(blockers) == 0, blockers


def get_draft_with_lines(db_path: Path, draft_id: int) -> Optional[dict]:
    """Load draft header and lines from database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get header
    row = conn.execute("""
        SELECT * FROM fact_po_drafts
        WHERE draft_id = ?
    """, (draft_id,)).fetchone()

    if not row:
        # Try alternate table name
        row = conn.execute("""
            SELECT * FROM fact_po_draft
            WHERE draft_id = ?
        """, (draft_id,)).fetchone()

    if not row:
        conn.close()
        return None

    draft = dict(row)

    # Get lines
    lines = conn.execute("""
        SELECT * FROM fact_po_draft_lines
        WHERE draft_id = ?
        ORDER BY sku_key, my_size
    """, (draft_id,)).fetchall()

    draft['lines'] = [dict(l) for l in lines]

    conn.close()
    return draft


def get_approval_for_draft(db_path: Path, draft_id: int) -> Optional[dict]:
    """Get approval record for a draft."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT * FROM fact_po_approvals
        WHERE draft_id = ?
          AND decision = 'APPROVE'
        ORDER BY approved_at DESC
        LIMIT 1
    """, (draft_id,)).fetchone()

    conn.close()
    return dict(row) if row else None


def check_already_executed(db_path: Path, draft_id: int) -> bool:
    """Check if draft has already been executed."""
    conn = sqlite3.connect(str(db_path))

    # Check fact_po_executions table
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_po_executions'"
    ).fetchall()

    if not tables:
        conn.close()
        return False

    row = conn.execute("""
        SELECT execution_id FROM fact_po_executions
        WHERE draft_id = ?
          AND status = 'SUCCESS'
        LIMIT 1
    """, (draft_id,)).fetchone()

    conn.close()
    return row is not None


def revalidate_line_guardrails(
    db_path: Path,
    draft_lines: list[dict],
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Re-run guardrails on all draft lines.

    Returns:
        (order_full_lines, skipped_lines, hard_blockers)

    Notes:
        - ORDER_FULL lines (>=20% ROIC, approved): returned in order_full_lines
        - ORDER_WITH_FLAG lines (WARN status): skipped but don't block execution
        - BLOCK-level issues (missing costs, budget exceeded): block everything
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get SKU costs for guardrail checks
    sku_costs = {}
    rows = conn.execute("SELECT sku_key, cogs_kzt FROM dim_sku WHERE cogs_kzt > 0").fetchall()
    for row in rows:
        sku_costs[row['sku_key']] = row['cogs_kzt']

    conn.close()

    order_full_lines = []
    skipped_lines = []
    hard_blockers = []  # Only BLOCK-level issues, not WARN

    for line in draft_lines:
        sku_key = line['sku_key']
        qty = line['quantity']
        roic_pct = line.get('roic_pct', 0) / 100  # Convert % to decimal
        unit_cost = sku_costs.get(sku_key, 0)
        po_value = qty * unit_cost

        # Re-run per-SKU guardrail check
        result = check_sku_guardrails(
            sku_key=sku_key,
            roic=roic_pct,
            order_qty=qty,
            po_value_kzt=po_value,
            unit_cost_kzt=unit_cost,
        )

        # Only allow ORDER_FULL lines through
        if result.roic_status == "PASS" and result.approved:
            # ORDER_FULL (>=20% ROIC)
            order_full_lines.append({
                **line,
                'guardrail_result': result,
                'unit_cost_kzt': unit_cost,
                'po_value_kzt': po_value,
            })
        else:
            skipped_lines.append({
                **line,
                'guardrail_result': result,
                'block_reason': "; ".join(result.blockers) if result.blockers else result.roic_status,
            })
            # Only add HARD blockers (not WARN/low ROIC)
            # WARN = order_with_flag (10-20% ROIC) - skip but don't block
            # BLOCK = missing data, budget exceeded, etc. - block everything
            if result.blockers:
                for blocker in result.blockers:
                    # Hard blockers are non-ROIC issues that should block execution
                    if any(keyword in blocker.lower() for keyword in
                           ['missing', 'budget', 'concentration', 'cost', 'data']):
                        hard_blockers.append(blocker)

    return order_full_lines, skipped_lines, hard_blockers


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def get_current_inventory(db_path: Path) -> dict[str, int]:
    """Get latest current inventory snapshot by SKU."""
    conn = sqlite3.connect(str(db_path))
    try:
        table = None
        if _table_exists(conn, "fact_inventory_snapshot_size"):
            row = conn.execute("SELECT COUNT(1) FROM fact_inventory_snapshot_size").fetchone()
            if row and row[0] > 0:
                table = "fact_inventory_snapshot_size"
        if table is None and _table_exists(conn, "fact_inventory_snapshot"):
            row = conn.execute("SELECT COUNT(1) FROM fact_inventory_snapshot").fetchone()
            if row and row[0] > 0:
                table = "fact_inventory_snapshot"
        if table is None:
            return {}

        snap_row = conn.execute(f"SELECT MAX(snapshot_date) FROM {table}").fetchone()
        if not snap_row or not snap_row[0]:
            return {}

        rows = conn.execute(
            f"""
            SELECT sku_key, SUM(current_stock) AS stock
            FROM {table}
            WHERE snapshot_date = ?
            GROUP BY sku_key
            """,
            (snap_row[0],),
        ).fetchall()
        return {row[0]: int(row[1] or 0) for row in rows}
    finally:
        conn.close()


def get_unit_costs(db_path: Path, sku_keys: set[str]) -> tuple[dict[str, float], list[str]]:
    """Fetch unit costs for the given SKU keys."""
    if not sku_keys:
        return {}, []

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dim_sku"):
            return {}, sorted(sku_keys)
        placeholders = ",".join(["?"] * len(sku_keys))
        rows = conn.execute(
            f"""
            SELECT sku_key, cogs_kzt
            FROM dim_sku
            WHERE sku_key IN ({placeholders})
              AND cogs_kzt > 0
            """,
            tuple(sku_keys),
        ).fetchall()
        unit_costs = {row[0]: float(row[1]) for row in rows}
        missing = sorted(sku_keys - set(unit_costs.keys()))
        return unit_costs, missing
    finally:
        conn.close()


def build_proposed_po(order_full_lines: list[dict]) -> dict[str, int]:
    """Aggregate draft lines into SKU-level proposed PO quantities."""
    proposed_po: dict[str, int] = {}
    for line in order_full_lines:
        sku_key = line.get("sku_key", "")
        if not sku_key:
            continue
        qty = int(line.get("quantity", 0) or 0)
        proposed_po[sku_key] = proposed_po.get(sku_key, 0) + qty
    return proposed_po


def run_capital_preflight(
    db_path: Path,
    order_full_lines: list[dict],
) -> tuple[bool, list[str], dict]:
    """
    Capital safety preflight before any write action.

    Enforces concentration + budget guardrails on the executable set.
    """
    blockers: list[str] = []

    proposed_po = build_proposed_po(order_full_lines)
    if not proposed_po:
        return False, ["No executable lines for capital preflight"], {}

    current_inventory = get_current_inventory(db_path)
    all_skus = set(proposed_po.keys()) | set(current_inventory.keys())
    unit_costs, missing_costs = get_unit_costs(db_path, all_skus)
    if missing_costs:
        blockers.append(f"Missing unit costs for SKUs: {', '.join(missing_costs[:5])}")

    po_value_kzt = sum(
        qty * unit_costs.get(sku, 0.0)
        for sku, qty in proposed_po.items()
    )
    portfolio_value_kzt = sum(
        current_inventory.get(sku, 0) * unit_costs.get(sku, 0.0)
        for sku in current_inventory.keys()
    )

    guardrail_result = check_all_guardrails(
        roic=0.0,
        po_value_kzt=po_value_kzt,
        proposed_po=proposed_po,
        current_inventory=current_inventory,
        unit_costs=unit_costs,
        skip_roic=True,
        skip_concentration=False,
        skip_budget=False,
        require_costs=True,
    )

    if guardrail_result.blockers:
        blockers.extend(guardrail_result.blockers)

    summary = {
        "po_value_kzt": po_value_kzt,
        "portfolio_value_kzt": portfolio_value_kzt,
        "concentration_valid": guardrail_result.concentration_valid,
        "budget_valid": guardrail_result.budget_valid,
        "status": guardrail_result.status.value,
        "roic_gate": "ORDER_FULL_ONLY",
    }

    return len(blockers) == 0, blockers, summary


def create_execution_record(
    db_path: Path,
    draft_id: int,
    approval_id: int,
    status: str,
    executed_lines: int,
    total_value_kzt: float,
    notes: str,
) -> int:
    """Create execution record in fact_po_executions."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_po_executions (
            execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL,
            approval_id INTEGER,
            executed_at TEXT DEFAULT (datetime('now')),
            status TEXT NOT NULL,
            executed_lines INTEGER DEFAULT 0,
            total_value_kzt REAL DEFAULT 0,
            notes TEXT,
            executed_by TEXT DEFAULT 'SYSTEM'
        )
    """)

    cursor.execute("""
        INSERT INTO fact_po_executions (
            draft_id, approval_id, status, executed_lines, total_value_kzt, notes
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (draft_id, approval_id, status, executed_lines, total_value_kzt, notes))

    execution_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return execution_id


def update_draft_status(db_path: Path, draft_id: int, status: str):
    """Update draft status after execution."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Try both table names
    cursor.execute("""
        UPDATE fact_po_drafts
        SET status = ?, updated_at = ?
        WHERE draft_id = ?
    """, (status, datetime.now().isoformat(), draft_id))

    if cursor.rowcount == 0:
        cursor.execute("""
            UPDATE fact_po_draft
            SET status = ?
            WHERE draft_id = ?
        """, (status, draft_id))

    conn.commit()
    conn.close()


# =============================================================================
# Part 6: Execution Reconciliation Artifact
# =============================================================================

def write_reconciliation_csv(
    result: ExecutionResult,
    output_dir: Path = None,
) -> Optional[Path]:
    """
    Write execution reconciliation CSV (Part 6 requirement).

    Creates: exports/execution_reconciliation_YYYY-MM-DD.csv

    Columns:
    - Section: SUMMARY | EXECUTED | SKIPPED
    - sku_key, sku_id, my_size
    - draft_qty, draft_value_kzt
    - executed_qty, executed_value_kzt
    - skipped_reason (for skipped lines)
    - idempotency_status

    Returns:
        Path to generated CSV or None if failed
    """
    if output_dir is None:
        output_dir = EXPORTS_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = date.today().isoformat()
    output_path = output_dir / f"execution_reconciliation_{today_str}.csv"

    try:
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(["EXECUTION RECONCILIATION", today_str, f"Draft #{result.draft_id}"])
            writer.writerow([])

            # Summary section
            writer.writerow(["SUMMARY"])
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Draft ID", result.draft_id])
            writer.writerow(["Execution Status", result.status])
            writer.writerow(["Execution ID", result.execution_id or "N/A"])
            writer.writerow(["Idempotency Status", "FIRST_RUN" if result.status == "SUCCESS" else result.status])
            writer.writerow([])
            writer.writerow(["Draft Total Spend (KZT)", f"{result.draft_value_kzt:,.0f}"])
            writer.writerow(["Executed Spend (KZT)", f"{result.total_value_kzt:,.0f}"])
            writer.writerow(["Skipped Spend (KZT)", f"{result.draft_value_kzt - result.total_value_kzt:,.0f}"])
            writer.writerow(["Execution Rate", f"{(result.total_value_kzt / result.draft_value_kzt * 100):.1f}%" if result.draft_value_kzt > 0 else "0%"])
            writer.writerow([])
            writer.writerow(["Lines Executed", result.executed_lines])
            writer.writerow(["Lines Skipped", result.skipped_lines])
            writer.writerow(["Lines Blocked", result.blocked_lines])
            writer.writerow([])

            # Blockers (if any)
            if result.blockers:
                writer.writerow(["BLOCKERS"])
                for blocker in result.blockers:
                    writer.writerow([blocker])
                writer.writerow([])

            # Executed lines section
            if result.executed_sku_details:
                writer.writerow(["EXECUTED LINES"])
                writer.writerow(["sku_key", "sku_id", "my_size", "quantity", "value_kzt", "roic_pct", "status"])
                for line in result.executed_sku_details:
                    writer.writerow([
                        line.get("sku_key", ""),
                        line.get("sku_id", ""),
                        line.get("my_size", ""),
                        line.get("quantity", 0),
                        f"{line.get('value_kzt', 0):,.0f}",
                        f"{line.get('roic_pct', 0):.1f}%",
                        "EXECUTED",
                    ])
                writer.writerow([])

            # Skipped lines section
            if result.skipped_sku_details:
                writer.writerow(["SKIPPED LINES"])
                writer.writerow(["sku_key", "sku_id", "my_size", "quantity", "value_kzt", "roic_pct", "skip_reason"])
                for line in result.skipped_sku_details:
                    writer.writerow([
                        line.get("sku_key", ""),
                        line.get("sku_id", ""),
                        line.get("my_size", ""),
                        line.get("quantity", 0),
                        f"{line.get('value_kzt', 0):,.0f}",
                        f"{line.get('roic_pct', 0):.1f}%",
                        line.get("reason", "LOW_ROIC"),
                    ])
                writer.writerow([])

            # Warnings
            if result.warnings:
                writer.writerow(["WARNINGS"])
                for warning in result.warnings:
                    writer.writerow([warning])

        return output_path

    except Exception as e:
        print(f"Failed to write reconciliation CSV: {e}")
        return None


def persist_reconciliation_artifact(
    db_path: Path,
    run_id: int,
    artifact_path: Path,
    step_name: str = "execution_reconciliation",
) -> bool:
    """
    Persist reconciliation artifact path to fact_run_steps.

    Part 6 requirement: Every artifact path must be recorded.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get max step order for this run
        row = cursor.execute("""
            SELECT COALESCE(MAX(step_order), 0) FROM fact_run_steps WHERE run_id = ?
        """, (run_id,)).fetchone()
        next_order = (row[0] if row else 0) + 1

        cursor.execute("""
            INSERT INTO fact_run_steps (
                run_id, step_name, step_order, status, started_at, completed_at,
                output_file, notes
            ) VALUES (?, ?, ?, 'SUCCESS', datetime('now'), datetime('now'), ?, ?)
        """, (
            run_id,
            step_name,
            next_order,
            str(artifact_path),
            f"Reconciliation artifact for execution"
        ))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Failed to persist artifact path: {e}")
        return False


def record_write_audit(
    db_path: Path,
    run_id: Optional[int],
    step_name: str,
    correlation_id: str,
    rollback_steps: list[str],
    status: str = "SUCCESS",
    details: Optional[str] = None,
) -> bool:
    """Record a write audit step with correlation ID and rollback steps."""
    if not run_id:
        return False

    notes = {
        "correlation_id": correlation_id,
        "rollback_steps": rollback_steps,
    }
    if details:
        notes["details"] = details

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        row = cursor.execute(
            "SELECT COALESCE(MAX(step_order), 0) FROM fact_run_steps WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        next_order = (row[0] if row else 0) + 1

        cursor.execute(
            """
            INSERT INTO fact_run_steps (
                run_id, step_name, step_order, status, started_at, completed_at, notes
            ) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)
            """,
            (run_id, step_name, next_order, status, json.dumps(notes)),
        )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Failed to record write audit step: {e}")
        return False


def execute_po_draft(
    db_path: Path,
    draft_id: int,
    approval_id: int = None,
    dry_run: bool = True,
    force: bool = False,
    run_id: Optional[int] = None,
) -> ExecutionResult:
    """
    Execute an approved PO draft (ORDER_FULL lines only).

    SAFETY: This is the critical function that gates all execution.

    Args:
        db_path: Path to database
        draft_id: Draft ID to execute
        approval_id: Optional approval ID (will look up if not provided)
        dry_run: If True, check but don't execute
        force: Skip some safety checks (NOT gate env vars)

    Returns:
        ExecutionResult with status and details
    """
    result = ExecutionResult(draft_id=draft_id, status="CHECKING")
    result.correlation_id = uuid.uuid4().hex

    # SAFETY GATE 1: Check env vars (NEVER skip these)
    can_execute, gate_blockers = check_execution_gates(require_write=not dry_run)
    if not can_execute:
        result.status = "DISABLED"
        result.blockers = gate_blockers
        result.notes.append("Execution disabled by env var gates")
        return result

    # SAFETY GATE 2: Check idempotency (already executed?)
    if not force and check_already_executed(db_path, draft_id):
        result.status = "IDEMPOTENT"
        result.notes.append(f"Draft {draft_id} has already been executed successfully")
        return result

    # Load draft
    draft = get_draft_with_lines(db_path, draft_id)
    if not draft:
        result.status = "ERROR"
        result.blockers.append(f"Draft {draft_id} not found")
        return result
    draft_status_before = draft.get("status")

    # Part 6: Record draft value for reconciliation
    result.draft_value_kzt = draft.get('total_po_value_kzt', 0) or 0

    if draft['status'] not in ('PENDING', 'APPROVED'):
        result.status = "BLOCKED"
        result.blockers.append(f"Draft status is '{draft['status']}' (expected PENDING or APPROVED)")
        return result

    if not draft['lines']:
        result.status = "ERROR"
        result.blockers.append("Draft has no lines")
        return result

    # Check approval exists (for Assisted mode)
    if approval_id is None:
        approval = get_approval_for_draft(db_path, draft_id)
        if approval:
            approval_id = approval['approval_id']
        elif AUTO_EXECUTE_MODE == "ASSISTED":
            result.status = "BLOCKED"
            result.blockers.append("No approval found for draft (required in ASSISTED mode)")
            result.notes.append("Run: python scripts/approve_po_draft.py --draft-id {} --approve".format(draft_id))
            return result

    # SAFETY GATE 3: Re-validate guardrails (idempotent)
    order_full_lines, skipped_lines, hard_blockers = revalidate_line_guardrails(
        db_path, draft['lines']
    )

    result.blocked_lines = len([l for l in skipped_lines if 'missing' in l.get('block_reason', '').lower() or 'budget' in l.get('block_reason', '').lower()])
    result.skipped_lines = len(skipped_lines)

    # Part 6: Populate SKU details for reconciliation
    for line in order_full_lines:
        result.executed_sku_details.append({
            "sku_key": line.get("sku_key", ""),
            "sku_id": line.get("sku_id", ""),
            "my_size": line.get("my_size", ""),
            "quantity": line.get("quantity", 0),
            "value_kzt": line.get("po_value_kzt", 0),
            "roic_pct": line.get("roic_pct", 0),
        })

    for line in skipped_lines:
        result.skipped_sku_details.append({
            "sku_key": line.get("sku_key", ""),
            "sku_id": line.get("sku_id", ""),
            "my_size": line.get("my_size", ""),
            "quantity": line.get("quantity", 0),
            "value_kzt": line.get("unit_cost_kzt", 0) * line.get("quantity", 0),
            "roic_pct": line.get("roic_pct", 0),
            "reason": line.get("block_reason", "LOW_ROIC"),
        })

    # CRITICAL: Block if ANY HARD blocker exists (missing data, budget, concentration)
    # NOTE: Low ROIC (WARN) lines are just skipped, not blocked
    if hard_blockers:
        result.status = "BLOCKED"
        result.blockers = list(set(hard_blockers))  # Dedupe
        result.notes.append(f"Blocked by {len(result.blockers)} critical guardrail violation(s)")

        # Record the blocked attempt
        if not dry_run:
            execution_id = create_execution_record(
                db_path, draft_id, approval_id, "BLOCKED",
                0, 0, f"Guardrails blocked: {'; '.join(result.blockers[:3])} (corr={result.correlation_id})"
            )
            result.execution_id = execution_id
            rollback_steps = [
                f"DELETE FROM fact_po_executions WHERE execution_id = {execution_id};"
            ]
            result.rollback_steps.extend(rollback_steps)
            record_write_audit(
                db_path,
                run_id,
                step_name="write_execution_blocked_guardrails",
                correlation_id=result.correlation_id,
                rollback_steps=rollback_steps,
            )
        return result

    if not order_full_lines:
        result.status = "BLOCKED"
        result.blockers.append("No ORDER_FULL lines available for execution")
        result.notes.append(f"All {len(draft['lines'])} lines were skipped (low ROIC) or require review")
        return result

    # PART 7: Apply SKU whitelist filtering (if enabled)
    whitelist = get_rollout_whitelist(db_path)
    if whitelist:
        order_full_lines, whitelist_filtered = filter_by_whitelist(order_full_lines, whitelist)
        result.whitelist_filtered_lines = len(whitelist_filtered)

        if whitelist_filtered:
            result.notes.append(f"{len(whitelist_filtered)} lines filtered by SKU whitelist")
            # Add whitelist-filtered lines to skipped details
            for line in whitelist_filtered:
                result.skipped_sku_details.append({
                    "sku_key": line.get("sku_key", ""),
                    "sku_id": line.get("sku_id", ""),
                    "my_size": line.get("my_size", ""),
                    "quantity": line.get("quantity", 0),
                    "value_kzt": line.get("po_value_kzt", 0),
                    "roic_pct": line.get("roic_pct", 0),
                    "reason": "NOT_IN_WHITELIST",
                })
            result.skipped_lines += len(whitelist_filtered)

        if not order_full_lines:
            result.status = "BLOCKED"
            result.blockers.append("No whitelisted ORDER_FULL lines available")
            result.notes.append(f"{len(whitelist_filtered)} lines were not in rollout whitelist")
            return result

    # Calculate execution totals
    result.executed_lines = len(order_full_lines)
    result.total_value_kzt = sum(l['po_value_kzt'] for l in order_full_lines)

    # PART 4: Capital safety preflight (concentration + budget)
    preflight_ok, preflight_blockers, preflight_summary = run_capital_preflight(
        db_path, order_full_lines
    )
    if preflight_summary:
        result.notes.append(
            "Capital preflight: "
            f"po_value={preflight_summary.get('po_value_kzt', 0):,.0f} KZT, "
            f"portfolio_value={preflight_summary.get('portfolio_value_kzt', 0):,.0f} KZT, "
            f"concentration_ok={preflight_summary.get('concentration_valid')}, "
            f"budget_ok={preflight_summary.get('budget_valid')}, "
            f"roic_gate={preflight_summary.get('roic_gate')}"
        )
    if not preflight_ok:
        result.status = "BLOCKED"
        result.blockers.extend(preflight_blockers)
        result.notes.append("Blocked by capital safety preflight (Part 4)")

        if not dry_run:
            execution_id = create_execution_record(
                db_path, draft_id, approval_id, "BLOCKED",
                0, 0, f"Capital preflight blocked: {'; '.join(preflight_blockers[:3])} (corr={result.correlation_id})"
            )
            result.execution_id = execution_id
            rollback_steps = [
                f"DELETE FROM fact_po_executions WHERE execution_id = {execution_id};"
            ]
            result.rollback_steps.extend(rollback_steps)
            record_write_audit(
                db_path,
                run_id,
                step_name="write_execution_blocked_preflight",
                correlation_id=result.correlation_id,
                rollback_steps=rollback_steps,
            )
        return result

    # PART 7: Check rollout spend caps AFTER calculating totals
    cap_ok, cap_blockers = check_rollout_caps(db_path, result.total_value_kzt)
    if not cap_ok:
        result.status = "BLOCKED"
        result.cap_blocked = True
        result.blockers.extend(cap_blockers)
        result.notes.append("Blocked by rollout spend caps (Part 7)")

        # Record the cap-blocked attempt
        if not dry_run:
            execution_id = create_execution_record(
                db_path, draft_id, approval_id, "BLOCKED",
                0, 0, f"Rollout caps exceeded: {'; '.join(cap_blockers[:2])} (corr={result.correlation_id})"
            )
            result.execution_id = execution_id
            rollback_steps = [
                f"DELETE FROM fact_po_executions WHERE execution_id = {execution_id};"
            ]
            result.rollback_steps.extend(rollback_steps)
            record_write_audit(
                db_path,
                run_id,
                step_name="write_execution_blocked_caps",
                correlation_id=result.correlation_id,
                rollback_steps=rollback_steps,
            )
        return result

    # DRY RUN: Return what would execute
    if dry_run:
        result.status = "DRY_RUN"
        result.notes.append(f"Would execute {result.executed_lines} ORDER_FULL lines")
        result.notes.append(f"Total value: {result.total_value_kzt:,.0f} KZT")
        if skipped_lines:
            result.warnings.append(f"{len(skipped_lines)} lines would be skipped (not ORDER_FULL)")
        return result

    # EXECUTE: Record and update status
    # In production, this is where we would call Kaspi API or supplier API
    # For now, we just record the execution intent

    execution_id = create_execution_record(
        db_path, draft_id, approval_id, "SUCCESS",
        result.executed_lines, result.total_value_kzt,
        f"Executed {result.executed_lines} ORDER_FULL lines, skipped {result.skipped_lines} (corr={result.correlation_id})"
    )

    result.execution_id = execution_id
    result.status = "SUCCESS"
    result.notes.append(f"Execution recorded (execution_id={execution_id})")

    rollback_steps_exec = [
        f"DELETE FROM fact_po_executions WHERE execution_id = {execution_id};"
    ]
    result.rollback_steps.extend(rollback_steps_exec)
    record_write_audit(
        db_path,
        run_id,
        step_name="write_execution_record",
        correlation_id=result.correlation_id,
        rollback_steps=rollback_steps_exec,
    )

    # Update draft status
    update_draft_status(db_path, draft_id, "EXECUTED")
    result.notes.append(f"Draft status updated to EXECUTED")
    rollback_status = draft_status_before or "PENDING"
    rollback_steps_status = [
        f"UPDATE fact_po_drafts SET status = '{rollback_status}' WHERE draft_id = {draft_id};",
        f"UPDATE fact_po_draft SET status = '{rollback_status}' WHERE draft_id = {draft_id};",
    ]
    result.rollback_steps.extend(rollback_steps_status)
    record_write_audit(
        db_path,
        run_id,
        step_name="write_draft_status_update",
        correlation_id=result.correlation_id,
        rollback_steps=rollback_steps_status,
    )

    if skipped_lines:
        result.warnings.append(f"{len(skipped_lines)} lines skipped (not ORDER_FULL)")

    # Part 6: Generate reconciliation artifact
    recon_path = write_reconciliation_csv(result)
    if recon_path:
        result.reconciliation_path = str(recon_path)
        result.notes.append(f"Reconciliation artifact: {recon_path}")
        rollback_steps_file = [f"rm '{recon_path}'"]
        result.rollback_steps.extend(rollback_steps_file)
        record_write_audit(
            db_path,
            run_id,
            step_name="write_reconciliation_csv",
            correlation_id=result.correlation_id,
            rollback_steps=rollback_steps_file,
            details=str(recon_path),
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="PO Draft Executor (Part 5: Partial Auto, Part 7: Rollout Caps)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
SAFETY REQUIREMENTS:
  All four env vars must be set to enable execution:
  - AUTONOMOUS_PO_ENABLED=true
  - PO_DRAFT_ONLY=false
  - AUTO_EXECUTE_MODE=ORDER_FULL_ONLY
  - PO_WRITE_ENABLED=true

  Even with all gates enabled, ONLY ORDER_FULL lines (>=20% ROIC) execute.
  Any guardrail blocker will prevent ALL execution.

PART 7 ROLLOUT CAPS (optional):
  - MAX_EXECUTE_SPEND_PER_DAY_KZT: Cap total daily execution spend
  - MAX_EXECUTE_SPEND_PER_DRAFT_KZT: Cap per-draft execution spend
  - ROLLOUT_SKU_WHITELIST_PATH: Path to SKU whitelist file

Examples:
    # Check current gate status
    python scripts/execute_po_draft.py --check-gates

    # Check rollout status (caps, whitelist, daily spend)
    python scripts/execute_po_draft.py --check-rollout

    # Dry-run to see what would execute
    python scripts/execute_po_draft.py --draft-id 123 --dry-run

    # Execute (requires all gates enabled)
    python scripts/execute_po_draft.py --draft-id 123 --execute

    # Execute with rollout caps
    MAX_EXECUTE_SPEND_PER_DAY_KZT=1000000 python scripts/execute_po_draft.py --draft-id 123 --execute
        """
    )

    parser.add_argument("--draft-id", type=int, help="Draft ID to execute")
    parser.add_argument("--approval-id", type=int, help="Optional approval ID")
    exec_mode = parser.add_mutually_exclusive_group()
    exec_mode.add_argument(
        "--execute",
        action="store_true",
        help="Execute writes (requires PO_WRITE_ENABLED=true)",
    )
    exec_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run (default)",
    )
    parser.add_argument("--force", action="store_true", help="Skip idempotency check")
    parser.add_argument("--check-gates", action="store_true", help="Check env var gates only")
    parser.add_argument("--check-rollout", action="store_true", help="Check rollout status (caps, whitelist)")
    parser.add_argument("--db", type=str, help="Database path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH

    # Part 7: Check rollout status mode
    if args.check_rollout:
        print("=" * 60)
        print("ROLLOUT STATUS (Part 7)")
        print("=" * 60)

        status = get_rollout_status(db_path)

        print("\nSPEND CAPS:")
        if status["caps_enabled"]:
            if status["daily_cap_kzt"] > 0:
                print(f"  Daily Cap: {status['daily_cap_kzt']:,.0f} KZT")
                print(f"  Executed Today: {status['daily_executed_kzt']:,.0f} KZT")
                print(f"  Remaining: {status['daily_remaining_kzt']:,.0f} KZT")
            if status["draft_cap_kzt"] > 0:
                print(f"  Per-Draft Cap: {status['draft_cap_kzt']:,.0f} KZT")
        else:
            print("  No spend caps configured (unlimited)")

        print("\nSKU WHITELIST:")
        if status["whitelist_enabled"]:
            print(f"  Status: ENABLED ({status['whitelist_count']} SKUs)")
            if status["whitelist_path"]:
                print(f"  Source: {status['whitelist_path']}")
            else:
                print("  Source: dim_rollout_whitelist table")
        else:
            print("  Status: DISABLED (all SKUs allowed)")

        print("\nTo configure rollout caps:")
        print("  export MAX_EXECUTE_SPEND_PER_DAY_KZT=1000000")
        print("  export MAX_EXECUTE_SPEND_PER_DRAFT_KZT=500000")
        print("  export ROLLOUT_SKU_WHITELIST_PATH=config/rollout_whitelist.txt")

        return 0

    # Check gates mode
    if args.check_gates:
        print("=" * 60)
        print("EXECUTION GATE STATUS")
        print("=" * 60)
        print(f"\nAUTONOMOUS_PO_ENABLED: {AUTONOMOUS_PO_ENABLED}")
        print(f"PO_DRAFT_ONLY: {PO_DRAFT_ONLY}")
        print(f"AUTO_EXECUTE_MODE: {AUTO_EXECUTE_MODE}")
        print(f"PO_WRITE_ENABLED: {PO_WRITE_ENABLED}")
        print()

        can_execute_dry, dry_blockers = check_execution_gates(require_write=False)
        can_execute_live, live_blockers = check_execution_gates(require_write=True)

        if can_execute_live:
            print("STATUS: READY TO EXECUTE (LIVE)")
            print("  All gates are enabled. ORDER_FULL lines can execute.")
        elif can_execute_dry:
            print("STATUS: DRY-RUN READY (WRITE FLAG DISABLED)")
            print("\nLive blockers:")
            for b in live_blockers:
                print(f"  - {b}")
            print("\nTo enable live execution, set:")
            print("  export PO_WRITE_ENABLED=true")
        else:
            print("STATUS: EXECUTION BLOCKED")
            print("\nBlockers:")
            for b in dry_blockers:
                print(f"  - {b}")
            print("\nTo enable execution, set:")
            print("  export AUTONOMOUS_PO_ENABLED=true")
            print("  export PO_DRAFT_ONLY=false")
            print("  export AUTO_EXECUTE_MODE=ORDER_FULL_ONLY")
            print("  export PO_WRITE_ENABLED=true")
        return 0

    # Require draft-id for execution
    if not args.draft_id:
        parser.print_help()
        return 1

    print("=" * 60)
    print(f"PO DRAFT EXECUTOR - Draft #{args.draft_id}")
    print("=" * 60)
    dry_run = not args.execute
    mode_label = "LIVE" if not dry_run else ("DRY-RUN" if args.dry_run else "DRY-RUN (default)")
    print(f"Mode: {mode_label}")
    print(f"Database: {db_path}")
    print()

    # Track execution with RunTracker
    with RunTracker("PO_EXECUTION", db_path) as tracker:
        tracker.start_step("check_gates")

        # Execute
        result = execute_po_draft(
            db_path=db_path,
            draft_id=args.draft_id,
            approval_id=args.approval_id,
            dry_run=dry_run,
            force=args.force,
            run_id=tracker.run_id,
        )

        tracker.complete_step()

        # Report result
        print(f"Status: {result.status}")
        print()

        if result.blockers:
            print("BLOCKERS:")
            for b in result.blockers:
                print(f"  ❌ {b}")
            print()

        if result.warnings:
            print("WARNINGS:")
            for w in result.warnings:
                print(f"  ⚠️  {w}")
            print()

        if result.notes:
            print("NOTES:")
            for n in result.notes:
                print(f"  • {n}")
            print()

        print("-" * 60)
        print(f"Lines Executed: {result.executed_lines}")
        print(f"Lines Skipped: {result.skipped_lines}")
        if result.whitelist_filtered_lines > 0:
            print(f"Lines Filtered by Whitelist: {result.whitelist_filtered_lines}")
        print(f"Draft Value: {result.draft_value_kzt:,.0f} KZT")
        print(f"Executed Value: {result.total_value_kzt:,.0f} KZT")
        if result.cap_blocked:
            print("Cap Blocked: YES (rollout spend cap exceeded)")
        if result.execution_id:
            print(f"Execution ID: {result.execution_id}")

        # Part 6: Report reconciliation artifact
        if result.reconciliation_path:
            print(f"Reconciliation: {result.reconciliation_path}")
            # Persist artifact to fact_run_steps
            if tracker.run_id:
                persist_reconciliation_artifact(
                    db_path, tracker.run_id, Path(result.reconciliation_path)
                )
                tracker.add_output_file(result.reconciliation_path)

        # Update tracker metrics
        tracker.set_metrics(
            skus_processed=result.executed_lines,
            guardrails_blocked=result.blocked_lines,
        )

        # Alert on failure (non-dry-run)
        if result.status == "BLOCKED" and not dry_run:
            send_error_alert(
                error_message="; ".join(result.blockers[:3]),
                script_name="execute_po_draft",
                context=f"Draft #{args.draft_id}"
            )

    # Return exit code based on result
    if result.status in ("SUCCESS", "DRY_RUN", "IDEMPOTENT"):
        return 0
    elif result.status == "DISABLED":
        return 2  # Expected when gates disabled
    else:
        return 1  # Blocked or error


if __name__ == "__main__":
    sys.exit(main())
