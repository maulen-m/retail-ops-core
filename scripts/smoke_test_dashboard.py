#!/usr/bin/env python3
"""
Smoke test for PO dashboard generation.

Runs the dashboard generator and validates:
1. fact_demand_estimates is populated
2. Row counts match
3. eligible_days <= good_days for all rows
4. No negative demand values

Usage:
    python scripts/smoke_test_dashboard.py
    python scripts/smoke_test_dashboard.py --skip-generate  # Just run validations
    python scripts/smoke_test_dashboard.py --fixture tests/fixtures/po_golden/po_contract_cases.json
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"

from core.validation.dashboard_contract import (
    DEFAULT_FIXTURE,
    DEFAULT_PO_CONTRACT,
    load_cases,
    build_drafts,
    generate_dashboard_output,
    validate_dashboard_output,
    hash_output,
)
from core.validation.tolerances import parse_po_contract_tolerances


def run_dashboard_generation():
    """Run the dashboard generation script."""
    print("=" * 60)
    print("STEP 1: Running dashboard generation...")
    print("=" * 60)

    # Import and run
    from scripts.generate_po_dashboard_data import generate_po_data

    try:
        result = generate_po_data()
        print(f"\n  Generated: {result['summary']['total_skus']} SKUs")
        print(f"  With orders: {result['summary']['skus_with_orders']}")
        print(f"  Total units: {result['summary']['total_units']}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_demand_estimates():
    """Validate fact_demand_estimates table."""
    print("\n" + "=" * 60)
    print("STEP 2: Validating fact_demand_estimates...")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    errors = []
    warnings = []

    # Check table exists
    table_check = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='fact_demand_estimates'
    """).fetchone()

    if not table_check:
        errors.append("Table fact_demand_estimates does not exist!")
        conn.close()
        return errors, warnings

    # Get row count
    row_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM fact_demand_estimates"
    ).fetchone()['cnt']
    print(f"  Row count: {row_count}")

    if row_count == 0:
        errors.append("fact_demand_estimates is empty!")
        conn.close()
        return errors, warnings

    # Get latest cutoff date
    latest_cutoff = conn.execute(
        "SELECT MAX(cutoff_date) as latest FROM fact_demand_estimates"
    ).fetchone()['latest']
    print(f"  Latest cutoff date: {latest_cutoff}")

    rows_at_cutoff = conn.execute(
        "SELECT COUNT(*) as cnt FROM fact_demand_estimates WHERE cutoff_date = ?",
        (latest_cutoff,)
    ).fetchone()['cnt']
    print(f"  Rows at latest cutoff: {rows_at_cutoff}")

    # Validate: eligible_days <= good_days
    print("\n  Checking eligible_days <= good_days...")
    violations = conn.execute("""
        SELECT sku_key, good_days, eligible_days
        FROM fact_demand_estimates
        WHERE eligible_days > good_days
        AND cutoff_date = ?
    """, (latest_cutoff,)).fetchall()

    if violations:
        for v in violations[:5]:  # Show first 5
            errors.append(
                f"eligible_days > good_days: {v['sku_key']} "
                f"(eligible={v['eligible_days']}, good={v['good_days']})"
            )
        if len(violations) > 5:
            errors.append(f"  ...and {len(violations) - 5} more violations")
    else:
        print("    PASS: All rows have eligible_days <= good_days")

    # Validate: no negative demand
    print("\n  Checking for negative demand values...")
    negative_demand = conn.execute("""
        SELECT sku_key, d_anchor, d_data, d_final, d_model
        FROM fact_demand_estimates
        WHERE (d_anchor < 0 OR d_data < 0 OR d_final < 0 OR d_model < 0)
        AND cutoff_date = ?
    """, (latest_cutoff,)).fetchall()

    if negative_demand:
        for v in negative_demand[:5]:
            errors.append(
                f"Negative demand: {v['sku_key']} "
                f"(anchor={v['d_anchor']}, data={v['d_data']}, final={v['d_final']})"
            )
    else:
        print("    PASS: No negative demand values")

    # Validate: d_final is reasonable (not too different from d_anchor or d_data)
    print("\n  Checking demand blending sanity...")
    suspicious_blend = conn.execute("""
        SELECT sku_key, d_anchor, d_data, d_final, anchor_weight
        FROM fact_demand_estimates
        WHERE d_final > 0
        AND d_anchor > 0
        AND d_data > 0
        AND (d_final < 0.3 * d_anchor AND d_final < 0.3 * d_data)
        AND cutoff_date = ?
        LIMIT 5
    """, (latest_cutoff,)).fetchall()

    if suspicious_blend:
        for v in suspicious_blend:
            warnings.append(
                f"Suspicious blend: {v['sku_key']} "
                f"(anchor={v['d_anchor']:.2f}, data={v['d_data']:.2f}, "
                f"final={v['d_final']:.2f}, weight={v['anchor_weight']:.2f})"
            )
    else:
        print("    PASS: Demand blending looks reasonable")

    # Stats summary
    print("\n  Summary stats:")
    stats = conn.execute("""
        SELECT
            AVG(d_final) as avg_d,
            AVG(good_days) as avg_good_days,
            AVG(eligible_days) as avg_eligible_days,
            AVG(availability_score) as avg_availability,
            COUNT(DISTINCT confidence) as confidence_levels
        FROM fact_demand_estimates
        WHERE cutoff_date = ?
    """, (latest_cutoff,)).fetchone()

    print(f"    Avg D_final: {stats['avg_d']:.2f}")
    print(f"    Avg good_days: {stats['avg_good_days']:.1f}")
    print(f"    Avg eligible_days: {stats['avg_eligible_days']:.1f}")
    print(f"    Avg availability: {stats['avg_availability']:.3f}")

    # Confidence distribution
    conf_dist = conn.execute("""
        SELECT confidence, COUNT(*) as cnt
        FROM fact_demand_estimates
        WHERE cutoff_date = ?
        GROUP BY confidence
        ORDER BY cnt DESC
    """, (latest_cutoff,)).fetchall()

    print("\n  Confidence distribution:")
    for row in conf_dist:
        print(f"    {row['confidence']}: {row['cnt']} SKUs")

    conn.close()
    return errors, warnings


def validate_consistency():
    """Validate consistency between demand estimates and dashboard output."""
    print("\n" + "=" * 60)
    print("STEP 3: Validating cross-table consistency...")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    errors = []
    warnings = []

    # Check that SKUs in dim_sku have matching demand estimates
    active_skus = conn.execute(
        "SELECT COUNT(*) as cnt FROM dim_sku WHERE active_flag = 1"
    ).fetchone()['cnt']

    demand_skus = conn.execute(
        "SELECT COUNT(DISTINCT sku_key) as cnt FROM fact_demand_estimates"
    ).fetchone()['cnt']

    print(f"  Active SKUs in dim_sku: {active_skus}")
    print(f"  SKUs with demand estimates: {demand_skus}")

    if demand_skus < active_skus * 0.5:
        warnings.append(
            f"Less than 50% of active SKUs have demand estimates "
            f"({demand_skus}/{active_skus})"
        )
    else:
        print(f"    Coverage: {demand_skus/active_skus*100:.1f}%")

    conn.close()
    return errors, warnings


def run_fixture_smoke_test(fixture_path: Path, contract_path: Path) -> bool:
    """Run deterministic dashboard contract validation on fixture input."""
    print("\n" + "=" * 60)
    print("FIXTURE DASHBOARD CONTRACT TEST")
    print("=" * 60)

    cases = load_cases(fixture_path)
    drafts = build_drafts(cases)
    output = generate_dashboard_output(cases)
    tolerances = parse_po_contract_tolerances(contract_path)

    errors = validate_dashboard_output(output, drafts, tolerances)
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for err in errors:
            print(f"  ❌ {err}")
        return False

    print("\n✅ FIXTURE CONTRACT PASSED")
    print(f"  Output hash: {hash_output(output)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Smoke test for PO dashboard")
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip generation, just run validations"
    )
    parser.add_argument(
        "--fixture",
        type=str,
        help="Run deterministic contract test using fixture JSON"
    )
    parser.add_argument(
        "--po-contract",
        type=str,
        help="Override PO_CONTRACT.md path for tolerances"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("PO Dashboard Smoke Test")
    print("=" * 60)

    if args.fixture:
        fixture_path = Path(args.fixture) if args.fixture else DEFAULT_FIXTURE
        contract_path = Path(args.po_contract) if args.po_contract else DEFAULT_PO_CONTRACT
        ok = run_fixture_smoke_test(fixture_path, contract_path)
        sys.exit(0 if ok else 1)

    all_errors = []
    all_warnings = []

    # Step 1: Generate dashboard (unless skipped)
    if not args.skip_generate:
        success = run_dashboard_generation()
        if not success:
            all_errors.append("Dashboard generation failed")
    else:
        print("\n[Skipping generation - using existing data]")

    # Step 2: Validate demand estimates
    errors, warnings = validate_demand_estimates()
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Step 3: Validate consistency
    errors, warnings = validate_consistency()
    all_errors.extend(errors)
    all_warnings.extend(warnings)

    # Final Report
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    if all_warnings:
        print(f"\nWARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  ⚠️  {w}")

    if all_errors:
        print(f"\nERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"  ❌ {e}")
        print("\n❌ SMOKE TEST FAILED")
        sys.exit(1)
    else:
        print("\n✅ SMOKE TEST PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
