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
import os

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_schema import validate_schema
from scripts.validate_single_truth_system import (
    validate_system as validate_single_truth_system,
    DEFAULT_DASHBOARD as DEFAULT_SINGLE_TRUTH_DASHBOARD,
)
from scripts.validate_inbound_sheet_consistency import validate_inbound_sheet_consistency
from scripts.validate_astana_totals_alignment import validate_astana_totals_alignment
from scripts.validate_on_delivery_freeze import validate_on_delivery_freeze
from scripts.validate_business_insides import validate_business_insides
from scripts.validate_sales_truth_reconciliation import reconcile_sales_truth
from scripts.validate_sales_vs_workbook_anchor import (
    validate_sales_vs_workbook_anchor,
    DEFAULT_SHEET as DEFAULT_SALES_ANCHOR_SHEET,
)
from scripts.validate_sales_truth_consumers import validate_sales_truth_consumers
from scripts.validate_cogs_integrity import validate_cogs_integrity
from scripts.validate_profit_publication_integrity import validate_profit_publication_integrity
from scripts.validate_offer_linkage import validate_offer_linkage
from scripts.validate_dim_sku_light_alignment import (
    validate_dim_sku_light_alignment,
    DEFAULT_WORKBOOK as DEFAULT_DIM_SKU_LIGHT_WORKBOOK,
    DEFAULT_SHEET as DEFAULT_DIM_SKU_LIGHT_SHEET,
)
from scripts.migrate_025_dim_sku_weight_guard import validate_dim_sku_weight_guard_schema
from scripts.validate_write_side_gating import (
    validate_manifest as validate_write_side_manifest,
    DEFAULT_MANIFEST as DEFAULT_WRITE_SIDE_MANIFEST,
)
from scripts.resolve_as_of_date import resolve_as_of_date

DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_INBOUND_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"

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


def resolve_single_truth_workbook_path(*, project_root: Path = PROJECT_ROOT) -> Path:
    env_raw = os.environ.get("AB_INBOUND_WORKBOOK_PATH", "").strip()
    if env_raw:
        return Path(env_raw).expanduser()
    return project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"


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


def validate_fx_rates(conn: sqlite3.Connection, result: ValidationResult, *, as_of: str | None = None):
    """Validate dim_fx_rates has current effective data."""
    cursor = conn.cursor()

    today = as_of or date.today().isoformat()
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


def validate_demand_overrides(conn: sqlite3.Connection, result: ValidationResult, *, as_of: str | None = None):
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

    cursor.execute("PRAGMA table_info(dim_demand_overrides)")
    columns = {row[1] for row in cursor.fetchall()}
    today = as_of or date.today().isoformat()

    if "start_date" in columns and "end_date" in columns:
        cursor.execute("""
            SELECT COUNT(*) FROM dim_demand_overrides
            WHERE active_flag = 1
              AND (start_date IS NULL OR start_date <= ?)
              AND (end_date IS NULL OR end_date > ?)
        """, (today, today))
    else:
        cursor.execute("""
            SELECT COUNT(*) FROM dim_demand_overrides WHERE active_flag = 1
        """)
    count = cursor.fetchone()[0]

    if count > 0:
        result.add_info(f"Active demand overrides (as of {today}): {count} SKUs")
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
    parser.add_argument("--as-of", type=str, default=None, help="As-of date YYYY-MM-DD (default: today)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.as_of:
        as_of_iso = args.as_of
        as_of_source = "explicit"
    else:
        try:
            resolution = resolve_as_of_date(
                project_root=PROJECT_ROOT,
                explicit_as_of=None,
                strict=False,
                daily_root=PROJECT_ROOT / "exports" / "daily",
            )
            as_of_iso = resolution.as_of
            as_of_source = resolution.source
        except Exception:
            as_of_iso = date.today().isoformat()
            as_of_source = "today_fallback"
    try:
        date.fromisoformat(as_of_iso)
    except Exception:
        if args.json:
            print(json.dumps({"status": "FAIL", "errors": [f"Invalid --as-of date: {as_of_iso}"]}))
        else:
            print(f"Error: Invalid --as-of date: {as_of_iso}")
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.exists():
        if args.json:
            print(json.dumps({"status": "FAIL", "errors": [f"Database not found: {db_path}"]}))
        else:
            print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    result = ValidationResult()
    result.add_info(f"as_of_resolved: {as_of_iso} (source={as_of_source})")
    schema_errors = validate_schema(db_path)
    for err in schema_errors:
        result.add_error(f"schema: {err}")

    conn = sqlite3.connect(str(db_path))
    try:
        validate_fx_rates(conn, result, as_of=as_of_iso)
        validate_params(conn, result)
        validate_budget_caps(conn, result)
        validate_demand_overrides(conn, result, as_of=as_of_iso)
        validate_runs_table(conn, result)
    finally:
        conn.close()

    if args.strict:
        try:
            single_truth_workbook = resolve_single_truth_workbook_path(project_root=PROJECT_ROOT)
            if not single_truth_workbook.exists():
                result.add_error(
                    "single_truth_system: inbound workbook not found "
                    f"(set AB_INBOUND_WORKBOOK_PATH or provide anchor at {DEFAULT_INBOUND_ANCHOR})"
                )
            else:
                result.add_info(f"single_truth_system workbook: {single_truth_workbook}")
                inbound_consistency = validate_inbound_sheet_consistency(
                    workbook_path=single_truth_workbook,
                    tolerance=0.0,
                )
                if not inbound_consistency["ok"]:
                    for mismatch in inbound_consistency.get("mismatches", []):
                        result.add_error(
                            "inbound_sheet_consistency: "
                            f"{mismatch.get('type')} "
                            f"po_part_id={mismatch.get('po_part_id')} "
                            f"sku_key={mismatch.get('sku_key')} "
                            f"expected={mismatch.get('expected_qty')} "
                            f"observed={mismatch.get('observed_qty')}"
                        )
                else:
                    result.add_info("inbound_sheet_consistency: OK")

                astana_alignment = validate_astana_totals_alignment(
                    workbook_path=single_truth_workbook,
                )
                if not astana_alignment["ok"]:
                    for err in astana_alignment.get("errors", []):
                        result.add_error(f"astana_totals_alignment: {err}")
                else:
                    result.add_info("astana_totals_alignment: OK")
                for warn in astana_alignment.get("warnings", []):
                    result.add_info(f"astana_totals_alignment warning: {warn}")

                system_errors = validate_single_truth_system(
                    db_path=db_path,
                    workbook_path=single_truth_workbook,
                    dashboard_path=DEFAULT_SINGLE_TRUTH_DASHBOARD,
                )
                if system_errors:
                    for err in system_errors:
                        result.add_error(f"single_truth_system: {err}")
                else:
                    result.add_info("single_truth_system: OK")
        except Exception as exc:
            result.add_error(f"single_truth_system error: {exc}")

        try:
            freeze_errors = validate_on_delivery_freeze(
                db_path=db_path,
                until=date.fromisoformat(as_of_iso),
            )
            if freeze_errors:
                for err in freeze_errors:
                    result.add_error(f"on_delivery_freeze: {err}")
            else:
                result.add_info("on_delivery_freeze: OK")
        except Exception as exc:
            result.add_error(f"on_delivery_freeze error: {exc}")

        try:
            business_errors = validate_business_insides(
                db_path=db_path,
                as_of=as_of_iso,
            )
            if business_errors:
                for err in business_errors:
                    result.add_error(f"business_insides: {err}")
            else:
                result.add_info("business_insides: OK")
        except Exception as exc:
            result.add_error(f"business_insides error: {exc}")

        try:
            sales_truth = reconcile_sales_truth(
                db_path=db_path,
                days=30,
                as_of=as_of_iso,
            )
            result.add_info(
                "sales_truth_reconciliation: "
                f"mismatch_days={sales_truth.get('daily_mismatch_count', 0)}, "
                f"v2_cogs_coverage={sales_truth.get('sales_fact_v2', {}).get('cogs_coverage_pct', 0)}%, "
                f"fact_cogs_coverage={sales_truth.get('fact_sales', {}).get('cogs_coverage_pct', 0)}%"
            )
        except Exception as exc:
            result.add_error(f"sales_truth_reconciliation error: {exc}")

        try:
            consumer_gate = validate_sales_truth_consumers(
                project_root=PROJECT_ROOT,
                contract_path=PROJECT_ROOT / "config" / "sales_truth_consumer_contract.yaml",
            )
            if not consumer_gate["ok"]:
                for err in consumer_gate["errors"]:
                    result.add_error(f"sales_truth_consumers: {err}")
            else:
                result.add_info(
                    "sales_truth_consumers: "
                    f"OK (checked={len(consumer_gate['checked_scripts'])})"
                )
        except Exception as exc:
            result.add_error(f"sales_truth_consumers error: {exc}")

        try:
            offer_linkage = validate_offer_linkage(db_path=db_path)
            require_offer_linkage = (
                os.environ.get("AB_REQUIRE_OFFER_LINKAGE_STRICT", "").strip().lower()
                in {"1", "true", "yes", "y"}
            )
            if not offer_linkage["ok"]:
                if require_offer_linkage:
                    for err in offer_linkage["errors"]:
                        result.add_error(f"offer_linkage: {err}")
                else:
                    result.add_info(
                        "offer_linkage: non-blocking by default "
                        "(set AB_REQUIRE_OFFER_LINKAGE_STRICT=1 to fail closed)"
                    )
                    for err in offer_linkage["errors"]:
                        result.add_info(f"offer_linkage detail: {err}")
            else:
                metrics = offer_linkage.get("metrics", {})
                result.add_info(
                    "offer_linkage: "
                    f"OK (resolved={metrics.get('resolved_rows', 0)}, "
                    f"unresolved={metrics.get('unresolved_rows', 0)}, "
                    f"ambiguous={metrics.get('ambiguous_rows', 0)})"
                )
        except Exception as exc:
            result.add_error(f"offer_linkage error: {exc}")

        try:
            workbook_anchor_raw = os.environ.get("AB_CRM_WORKBOOK_PATH", "").strip()
            if workbook_anchor_raw:
                workbook_anchor = Path(workbook_anchor_raw).expanduser()
                if not workbook_anchor.exists():
                    result.add_error(
                        f"sales_workbook_anchor: AB_CRM_WORKBOOK_PATH does not exist: {workbook_anchor}"
                    )
                else:
                    workbook_sheet = os.environ.get("AB_CRM_WORKBOOK_SHEET", DEFAULT_SALES_ANCHOR_SHEET)
                    workbook_max_lag_days = int(os.environ.get("AB_CRM_WORKBOOK_MAX_LAG_DAYS", "1"))
                    workbook_gate = validate_sales_vs_workbook_anchor(
                        db_path=db_path,
                        workbook_path=workbook_anchor,
                        sheet_name=workbook_sheet,
                        days=14,
                        tol_pct=5.0,
                        as_of=as_of_iso,
                        min_overlap_days=7,
                        max_lag_days=workbook_max_lag_days,
                    )
                    if not workbook_gate["ok"]:
                        for err in workbook_gate["errors"]:
                            result.add_error(f"sales_workbook_anchor: {err}")
                    else:
                        result.add_info(
                            "sales_workbook_anchor: "
                            f"OK (window={workbook_gate['window_start']}..{workbook_gate['window_end']}, "
                            f"overlap_days={workbook_gate['overlap_days']})"
                        )
            else:
                result.add_info("sales_workbook_anchor: skipped (AB_CRM_WORKBOOK_PATH not set)")
        except Exception as exc:
            result.add_error(f"sales_workbook_anchor error: {exc}")

        try:
            cogs_report = validate_cogs_integrity(
                db_path=db_path,
                as_of=as_of_iso,
                days=30,
                max_unresolved_rows=0,
                max_unresolved_skus=0,
            )
            if not cogs_report["ok"]:
                for err in cogs_report["errors"]:
                    result.add_error(f"cogs_integrity: {err}")
            else:
                result.add_info(
                    "cogs_integrity: "
                    f"OK (window={cogs_report['window_start']}..{cogs_report['window_end']}, "
                    f"rows={cogs_report['total_rows']})"
                )
        except Exception as exc:
            result.add_error(f"cogs_integrity error: {exc}")

        try:
            profit_publication = validate_profit_publication_integrity(
                db_path=db_path,
                as_of=as_of_iso,
                days=30,
            )
            if not profit_publication["ok"]:
                for err in profit_publication["errors"]:
                    result.add_error(f"profit_publication_integrity: {err}")
            else:
                result.add_info(
                    "profit_publication_integrity: "
                    f"OK (window={profit_publication['window_start']}..{profit_publication['window_end']})"
                )
        except Exception as exc:
            result.add_error(f"profit_publication_integrity error: {exc}")

        try:
            workbook_light = Path(
                os.environ.get("DIM_SKU_LIGHT_WORKBOOK_PATH", str(DEFAULT_DIM_SKU_LIGHT_WORKBOOK))
            ).expanduser()
            workbook_light_sheet = os.environ.get("DIM_SKU_LIGHT_SHEET", DEFAULT_DIM_SKU_LIGHT_SHEET)
            light_report = validate_dim_sku_light_alignment(
                db_path=db_path,
                workbook_path=workbook_light,
                sheet_name=workbook_light_sheet,
                weight_tol_kg=0.01,
                base_tol_cny=0.01,
                enforce_base_cost=False,
            )
            if not light_report["ok"]:
                for err in light_report["errors"]:
                    result.add_error(f"dim_sku_light_alignment: {err}")
            else:
                result.add_info(
                    "dim_sku_light_alignment: "
                    f"OK (compared={light_report['compared_count']}, "
                    f"base_drift={light_report['base_mismatch_count']})"
                )
            for warn in light_report.get("warnings", []):
                if "base-cost reference drift" in warn:
                    result.add_info(f"dim_sku_light_alignment: non-blocking {warn}")
                else:
                    result.add_warning(f"dim_sku_light_alignment: {warn}")
        except Exception as exc:
            result.add_error(f"dim_sku_light_alignment error: {exc}")

        try:
            guard_errors = validate_dim_sku_weight_guard_schema(db_path)
            if guard_errors:
                for err in guard_errors:
                    result.add_error(f"dim_sku_weight_guard: {err}")
            else:
                result.add_info("dim_sku_weight_guard: OK")
        except Exception as exc:
            result.add_error(f"dim_sku_weight_guard error: {exc}")

        try:
            write_side_report = validate_write_side_manifest(
                manifest_path=DEFAULT_WRITE_SIDE_MANIFEST,
                project_root=PROJECT_ROOT,
            )
            if not write_side_report["ok"]:
                for err in write_side_report["errors"]:
                    result.add_error(f"write_side_gating: {err}")
            else:
                result.add_info(
                    "write_side_gating: "
                    f"OK (checked={write_side_report['checked_count']})"
                )
        except Exception as exc:
            result.add_error(f"write_side_gating error: {exc}")

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
