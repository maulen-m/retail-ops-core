#!/usr/bin/env python3
"""
Validate parameter tables before running operations.

Part 3 requirement: Fail fast if missing/empty parameters that would
cause silent fallbacks.

Validates:
- dim_fx_rates: At least one row with current effective date
- dim_params: Core frozen parameters (L, R, B, z, TV)
- dim_budget_caps: At least one active row (can be 0 = unlimited)

Usage:
    python scripts/validate_params.py [--strict] [--db path]

    --strict: Fail on any warning (not just errors)

Exit codes:
    0: All validations passed
    1: Critical validation failed
    2: Warnings present (only with --strict)
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path
import sys
import json

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import init_db

DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Required frozen parameters
# Note: DB uses TV_mix_floor (not TV_factor) per dim_params seeding in bootstrap_db.py
REQUIRED_PARAMS = ["L_days", "R_days", "B_days", "z_factor", "TV_mix_floor"]

# Expected values for validation
FROZEN_VALUES = {
    "L_days": 21,
    "R_days": 10,
    "B_days": 14,
    "z_factor": 1.65,
    "TV_mix_floor": 0.23,
}


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> dict:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "status": "FAIL" if self.has_errors else ("WARN" if self.has_warnings else "PASS")
        }


def validate_fx_rates(conn: sqlite3.Connection, result: ValidationResult):
    """Validate dim_fx_rates has current effective data."""
    cursor = conn.cursor()

    today = date.today().isoformat()
    seed_cmd = (
        "python3 scripts/upsert_fx_rates.py "
        f"--effective-date {today} "
        "--usdt-kzt 510 --usdt-cny 6.80 "
        "--usd-kzt 514 --dlv-rate-usd-kg 2.66 "
        "--provider MANUAL "
        "--source \"Binance P2P + BestChange\""
    )

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='dim_fx_rates'
    """)
    if not cursor.fetchone():
        result.add_error(
            "dim_fx_rates table does not exist. Seed FX with:\n"
            f"  {seed_cmd}"
        )
        return

    # Check for any data
    cursor.execute("SELECT COUNT(*) FROM dim_fx_rates")
    count = cursor.fetchone()[0]

    if count == 0:
        result.add_error(
            "dim_fx_rates is empty - system will fall back to defaults. Seed FX with:\n"
            f"  {seed_cmd}"
        )
        return

    # Check for current effective date
    cursor.execute("""
        SELECT effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg, source
        FROM dim_fx_rates
        WHERE effective_date <= ?
        ORDER BY effective_date DESC
        LIMIT 1
    """, (today,))
    row = cursor.fetchone()

    if not row:
        result.add_error(
            f"No FX rates effective as of {today}. Seed FX with:\n  {seed_cmd}"
        )
        return

    eff_date, cny_kzt, usd_kzt, dlv_rate, source = row
    result.add_info(f"FX rates: CNY/KZT={cny_kzt}, USD/KZT={usd_kzt}, "
                   f"DLV={dlv_rate} (effective {eff_date}, source: {source})")

    # Validate reasonable ranges
    if cny_kzt < 50 or cny_kzt > 150:
        result.add_warning(f"CNY/KZT rate {cny_kzt} seems unusual (expected 50-150)")
    if usd_kzt < 300 or usd_kzt > 800:
        result.add_warning(f"USD/KZT rate {usd_kzt} seems unusual (expected 300-800)")


def validate_params(conn: sqlite3.Connection, result: ValidationResult):
    """Validate dim_params has required frozen parameters."""
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='dim_params'
    """)
    if not cursor.fetchone():
        result.add_error("dim_params table does not exist")
        return

    # Check for required parameters
    cursor.execute("SELECT param_key, param_value FROM dim_params WHERE product_type IS NULL")
    params = {row[0]: row[1] for row in cursor.fetchall()}

    missing = []
    mismatched = []
    for param_key in REQUIRED_PARAMS:
        if param_key not in params:
            missing.append(param_key)
        elif param_key in FROZEN_VALUES:
            expected = FROZEN_VALUES[param_key]
            actual = params[param_key]
            if abs(actual - expected) > 0.001:
                mismatched.append(f"{param_key}={actual} (expected {expected})")

    if missing:
        result.add_error(f"Missing required parameters: {', '.join(missing)}")

    if mismatched:
        result.add_warning(f"Parameters differ from frozen values: {', '.join(mismatched)}")

    if not missing:
        result.add_info(f"Frozen params: L={params.get('L_days')}, R={params.get('R_days')}, "
                       f"B={params.get('B_days')}, z={params.get('z_factor')}, TV={params.get('TV_mix_floor')}")


def validate_budget_caps(conn: sqlite3.Connection, result: ValidationResult):
    """Validate dim_budget_caps has at least one active row."""
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='dim_budget_caps'
    """)
    if not cursor.fetchone():
        result.add_warning("dim_budget_caps table does not exist - no budget limits enforced")
        return

    # Check for active caps
    cursor.execute("""
        SELECT global_monthly_cap_kzt, per_draft_cap_kzt
        FROM dim_budget_caps
        WHERE active_flag = 1
        ORDER BY effective_date DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    if not row:
        result.add_info("No active budget caps configured")
        return

    monthly_cap, draft_cap = row
    if monthly_cap and monthly_cap > 0:
        result.add_info(f"Monthly budget cap: {monthly_cap:,.0f} KZT")
    else:
        result.add_info("Monthly budget cap: unlimited")

    if draft_cap and draft_cap > 0:
        result.add_info(f"Per-draft budget cap: {draft_cap:,.0f} KZT")
    else:
        result.add_info("Per-draft budget cap: unlimited")


def validate_demand_overrides(conn: sqlite3.Connection, result: ValidationResult):
    """Report on active demand overrides (info only)."""
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='dim_demand_overrides'
    """)
    if not cursor.fetchone():
        result.add_info("dim_demand_overrides table does not exist - no overrides active")
        return

    # Count active overrides
    cursor.execute("""
        SELECT COUNT(*) FROM dim_demand_overrides WHERE active_flag = 1
    """)
    count = cursor.fetchone()[0]

    if count > 0:
        result.add_info(f"Active demand overrides: {count} SKUs")
    else:
        result.add_info("No active demand overrides")


def validate_runs_table(conn: sqlite3.Connection, result: ValidationResult):
    """Validate fact_runs table exists for run tracking."""
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='fact_runs'
    """)
    if not cursor.fetchone():
        result.add_warning("fact_runs table does not exist - run history won't be tracked")
        return

    # Get last run info
    cursor.execute("""
        SELECT run_date, run_type, status, completed_at
        FROM fact_runs
        ORDER BY run_id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    if row:
        run_date, run_type, status, completed_at = row
        result.add_info(f"Last run: {run_type} on {run_date} - {status}")
    else:
        result.add_info("No runs recorded yet")


def main():
    parser = argparse.ArgumentParser(description="Validate parameter tables")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings too")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Database path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        if args.json:
            print(json.dumps({"status": "FAIL", "errors": [f"Database not found: {db_path}"]}))
        else:
            print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    try:
        # Apply schema to prevent drift (idempotent; CREATE IF NOT EXISTS only)
        init_db(db_path=db_path)
    except Exception as exc:
        print(f"Error: Failed to apply schema.sql to {db_path}: {exc}")
        sys.exit(1)

    result = ValidationResult()

    conn = sqlite3.connect(str(db_path))
    try:
        validate_fx_rates(conn, result)
        validate_params(conn, result)
        validate_budget_caps(conn, result)
        validate_demand_overrides(conn, result)
        validate_runs_table(conn, result)
    finally:
        conn.close()

    # Output results
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Parameter Validation: {db_path}")
        print("=" * 60)

        if result.info:
            print("\nInfo:")
            for msg in result.info:
                print(f"  [i] {msg}")

        if result.warnings:
            print("\nWarnings:")
            for msg in result.warnings:
                print(f"  [!] {msg}")

        if result.errors:
            print("\nErrors:")
            for msg in result.errors:
                print(f"  [X] {msg}")

        print()
        print("=" * 60)
        status = result.to_dict()["status"]
        print(f"Status: {status}")

    # Exit code
    if result.has_errors:
        sys.exit(1)
    elif args.strict and result.has_warnings:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
