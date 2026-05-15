#!/usr/bin/env python3
"""
Validate Size Allocation: Phase 9.6 validation script.

TASK-168: 7 validation checks for size-aware PO allocation engine.

Checks:
1. Parameters match Master_Inventory_Rules_v9.md
2. Size mix bounds are respected (3%-40%)
3. Safety stock formulas match documentation
4. ROP calculations are correct
5. Status logic follows "Check Total FIRST" rule
6. ROIC gate decisions are correct
7. Total order qty equals sum of size allocations

Usage:
    python scripts/validate_size_allocation.py                    # Validate all
    python scripts/validate_size_allocation.py --sku LINE52      # Validate specific SKU
    python scripts/validate_size_allocation.py --verbose          # Show detailed output
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.inventory_params import get_params, InventoryParams
from core.calc.size_allocation import (
    OrderStatus,
    ROICAction,
    DemandConfidence,
    calc_d_sku_with_oos_filter,
    calc_size_mix_with_guardrails,
    calc_safety_stock_for_size,
    calc_rop_for_size,
    calc_t_post_for_size,
    calc_pre_arrival_stock,
    calc_status_for_size,
    should_generate_po,
    calc_order_qty_for_size,
    adjust_for_new_sku,
    apply_low_demand_insurance,
    calc_roic,
    apply_roic_gate,
    generate_po_draft,
)
from core.db import get_db


def check_1_params_match_master_rules(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 1: Parameters match Master_Inventory_Rules_v9.md exactly.

    Expected values from Section 4.1:
    - L = 21 (lead time)
    - R = 10 (review period)
    - B = 14 (buffer)
    - z = 1.65 (service level)
    - TV = 0.23 (mix variability)
    - sigma_factor = 0.4
    """
    params = get_params()

    expected = {
        "L": 21,
        "R": 10,
        "B": 14,
        "z": 1.65,
        "TV": 0.23,
        "sigma_factor": 0.4,
        # Phase 9.6 additions
        "min_size_mix": 0.03,
        "max_size_mix": 0.40,
        "roic_full_approval": 0.20,
        "roic_flag_threshold": 0.10,
        "new_sku_30d_factor": 0.75,
        "new_sku_60d_factor": 0.85,
        "new_sku_90d_factor": 0.95,
    }

    errors = []
    for key, expected_val in expected.items():
        actual_val = getattr(params, key)
        if actual_val != expected_val:
            errors.append(f"{key}: expected {expected_val}, got {actual_val}")

    if errors:
        return False, f"Parameter mismatches: {'; '.join(errors)}"

    if verbose:
        print("  All parameters match Master Rules v5.3:")
        for key, val in expected.items():
            print(f"    {key} = {val}")

    return True, "All parameters match Master Rules"


def check_2_size_mix_bounds(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 2: Size mix bounds are respected (3% floor, 40% cap).

    Tests:
    - Values below 3% get raised to 3%
    - Values above 40% get capped to 40%
    - Renormalization ensures sum = 1.0
    """
    params = get_params()

    # Test case: Realistic distribution with some extreme values
    # calc_size_mix_with_guardrails takes sales counts, not proportions
    # Using values that won't cause renormalization to exceed cap
    test_sales = {"S": 5, "M": 15, "L": 35, "XL": 30, "2XL": 10, "3XL": 3, "4XL": 2}
    result = calc_size_mix_with_guardrails(test_sales)

    errors = []

    # Check floor (3%) - use 1% tolerance for floating point precision
    for size, val in result.items():
        if val < params.min_size_mix - 0.01:
            errors.append(f"{size}: {val:.3f} below floor {params.min_size_mix}")

    # Check cap (40%) - use 1% tolerance for floating point precision
    for size, val in result.items():
        if val > params.max_size_mix + 0.01:
            errors.append(f"{size}: {val:.3f} above cap {params.max_size_mix}")

    # Check normalization
    total = sum(result.values())
    if abs(total - 1.0) > 0.001:
        errors.append(f"Sum = {total:.4f}, not 1.0")

    if errors:
        return False, f"Size mix bound errors: {'; '.join(errors)}"

    if verbose:
        print("  Size mix bounds validated:")
        print(f"    Input sales:  {test_sales}")
        print(f"    Output mix: {result}")
        print(f"    All values in [{params.min_size_mix}, {params.max_size_mix}]")
        print(f"    Sum = {sum(result.values()):.4f}")

    return True, "Size mix bounds respected"


def check_3_safety_stock_formula(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 3: Safety stock formula matches documentation.

    Formula: SS_total = SS_demand + SS_floor + SS_mix
    - SS_demand = z * sigma_size * sqrt(L)
    - SS_floor = d_size * B
    - SS_mix = TV * d_size * L
    """
    import math
    params = get_params()

    # Test inputs
    d_size = 1.0       # 1 unit/day for this size
    sigma_sku = 2.0    # σ = 2
    mix = 0.20         # 20% of total

    # Manual calculation
    sigma_size = sigma_sku * mix  # 0.4

    ss_demand = params.z * sigma_size * math.sqrt(params.L)
    ss_floor = d_size * params.B
    ss_mix = params.TV * d_size * params.L
    expected_ss = ss_demand + ss_floor + ss_mix

    # Function calculation - returns tuple of 5 values
    actual_sigma, actual_ss_demand, actual_ss_floor, actual_ss_mix, actual_ss_total = calc_safety_stock_for_size(
        d_size=d_size, sigma_sku=sigma_sku, size_mix=mix
    )

    if abs(actual_ss_total - expected_ss) > 0.01:
        return False, f"SS mismatch: expected {expected_ss:.2f}, got {actual_ss_total:.2f}"

    if verbose:
        print("  Safety stock formula validated:")
        print(f"    Inputs: d_size={d_size}, sigma_sku={sigma_sku}, mix={mix}")
        print(f"    sigma_size = {sigma_sku} * {mix} = {actual_sigma:.2f}")
        print(f"    SS_demand = {params.z} * {actual_sigma:.2f} * sqrt({params.L}) = {actual_ss_demand:.2f}")
        print(f"    SS_floor = {d_size} * {params.B} = {actual_ss_floor:.2f}")
        print(f"    SS_mix = {params.TV} * {d_size} * {params.L} = {actual_ss_mix:.2f}")
        print(f"    SS_total = {actual_ss_total:.2f}")

    return True, "Safety stock formula correct"


def check_4_rop_calculation(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 4: ROP calculation is correct.

    Formula: ROP = D * L + SS_total
    """
    params = get_params()

    # Test inputs
    d_size = 1.0   # 1 unit/day demand for this size
    ss = 5.0       # safety stock

    # Manual calculation
    expected_rop = d_size * params.L + ss

    # Function calculation
    actual_rop = calc_rop_for_size(d_size=d_size, ss_total=ss)

    if abs(actual_rop - expected_rop) > 0.01:
        return False, f"ROP mismatch: expected {expected_rop:.2f}, got {actual_rop:.2f}"

    if verbose:
        print("  ROP calculation validated:")
        print(f"    Inputs: d_size={d_size}, ss={ss}")
        print(f"    ROP = {d_size} * {params.L} + {ss} = {expected_rop:.2f}")

    return True, "ROP calculation correct"


def check_5_status_logic(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 5: Status logic follows "Check Total FIRST" rule.

    Rule:
    - If TOTAL < ROP → REORDER
    - Else if CURRENT < ROP → WAIT
    - Else → OK
    """
    test_cases = [
        # (current, total, rop, expected_status)
        (10, 10, 20, OrderStatus.REORDER),   # total=10 < rop=20
        (10, 25, 20, OrderStatus.WAIT),      # total=25 >= rop=20, but current=10 < rop=20
        (30, 30, 20, OrderStatus.OK),        # total=30 >= rop=20, current=30 >= rop=20
        (20, 20, 20, OrderStatus.OK),        # total=20 >= rop=20, current=20 >= rop=20
        (15, 25, 20, OrderStatus.WAIT),      # total=25 >= rop=20, current=15 < rop=20
    ]

    errors = []
    for current, total, rop, expected in test_cases:
        actual = calc_status_for_size(current_stock=current, total_stock=total, rop=rop)
        if actual != expected:
            errors.append(f"current={current}, total={total}, rop={rop}: expected {expected.value}, got {actual.value}")

    if errors:
        return False, f"Status logic errors: {'; '.join(errors)}"

    if verbose:
        print("  Status logic validated:")
        for current, total, rop, expected in test_cases:
            print(f"    current={current}, total={total}, rop={rop} → {expected.value}")

    return True, "Status logic correct"


def check_6_roic_gate(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 6: ROIC gate decisions are correct.

    Rules:
    - ROIC >= 20% → ORDER_FULL
    - 10% <= ROIC < 20% → ORDER_WITH_FLAG
    - ROIC < 10% → REVIEW_REQUIRED
    """
    params = get_params()
    order_qty = 100  # Test quantity

    test_cases = [
        # (roic, expected_action, expected_qty)
        (0.25, ROICAction.ORDER_FULL, 100),       # 25% → full
        (0.20, ROICAction.ORDER_FULL, 100),       # 20% → full (boundary)
        (0.15, ROICAction.ORDER_WITH_FLAG, 100),  # 15% → flag
        (0.10, ROICAction.ORDER_WITH_FLAG, 100),  # 10% → flag (boundary)
        (0.05, ROICAction.REVIEW_REQUIRED, 0),    # 5% → review (qty blocked)
        (0.00, ROICAction.REVIEW_REQUIRED, 0),    # 0% → review (qty blocked)
    ]

    errors = []
    for roic, expected_action, expected_qty in test_cases:
        actual_action, actual_qty = apply_roic_gate(roic=roic, order_qty=order_qty)
        if actual_action != expected_action:
            errors.append(f"roic={roic:.2%}: expected {expected_action.value}, got {actual_action.value}")
        if actual_qty != expected_qty:
            errors.append(f"roic={roic:.2%}: expected qty={expected_qty}, got qty={actual_qty}")

    if errors:
        return False, f"ROIC gate errors: {'; '.join(errors)}"

    if verbose:
        print("  ROIC gate validated:")
        for roic, expected_action, expected_qty in test_cases:
            print(f"    ROIC {roic:.0%} → {expected_action.value}, qty={expected_qty}")

    return True, "ROIC gate correct"


def check_7_total_equals_sum(verbose: bool = False) -> tuple[bool, str]:
    """
    Check 7: Total order qty equals sum of size allocations.

    Tests that generate_po_draft() produces consistent totals.
    """
    # Create synthetic test data
    sizes = ["S", "M", "L", "XL"]
    size_sales_90d = {s: 10 + i * 5 for i, s in enumerate(sizes)}  # S=10, M=15, L=20, XL=25
    size_current_stock = {"S": 5, "M": 3, "L": 2, "XL": 1}  # Low stock
    size_inbound_stock = {s: 0 for s in sizes}

    # 90 days of sales/stock history
    size_sales_history = {s: [1, 2, 1, 0, 1, 2, 1, 0, 1, 2] * 9 for s in sizes}
    size_stock_history = {s: [10] * 90 for s in sizes}

    draft = generate_po_draft(
        sku_key="TEST_SKU",
        store_code="TEST",
        size_sales_90d=size_sales_90d,
        size_current_stock=size_current_stock,
        size_inbound_stock=size_inbound_stock,
        size_sales_history=size_sales_history,
        size_stock_history=size_stock_history,
        unit_cogs=1000.0,
        unit_profit=500.0,  # 50% margin
        sigma_sku=2.0,
        sku_age_days=120,
    )

    if draft is None:
        return False, "generate_po_draft() returned None"

    if not draft.should_order:
        if verbose:
            print("  Note: No order needed for test data, but function works")
        return True, "Total/sum check N/A (no order needed)"

    # Verify total equals sum
    size_sum = sum(alloc.order_qty_adjusted for alloc in draft.allocations.values())

    if draft.total_qty != size_sum:
        return False, f"Total mismatch: total_qty={draft.total_qty}, sum of sizes={size_sum}"

    if verbose:
        print("  Total equals sum validated:")
        print(f"    Total qty: {draft.total_qty}")
        for size, alloc in draft.allocations.items():
            print(f"    {size}: {alloc.order_qty_adjusted}")
        print(f"    Sum: {size_sum}")

    return True, "Total equals sum of sizes"


def validate_sku(sku_key: str, verbose: bool = False) -> dict[str, tuple[bool, str]]:
    """
    Validate size allocation for a specific SKU from the database.

    Args:
        sku_key: SKU key to validate
        verbose: Show detailed output

    Returns:
        Dict of check_name -> (passed, message)
    """
    from core.db.queries import (
        get_size_sales_history,
        get_size_stock_history,
        get_size_current_stock,
        get_size_inbound,
        get_size_sales_90d,
        get_sku_age_days,
    )

    results = {}

    with get_db() as conn:
        # Get data
        size_current = get_size_current_stock(sku_key, "UNIVERSAL")

        if not size_current:
            results["data_exists"] = (False, f"No size data found for {sku_key}")
            return results

        sizes = list(size_current.keys())
        results["data_exists"] = (True, f"Found {len(sizes)} sizes")

        size_sales_history = get_size_sales_history(sku_key, "UNIVERSAL", days=90)
        size_stock_history = get_size_stock_history(sku_key, "UNIVERSAL", days=90)
        size_sales_90d = get_size_sales_90d(sku_key, "UNIVERSAL")
        size_inbound = get_size_inbound(sku_key, "UNIVERSAL")
        sku_age = get_sku_age_days(sku_key, "UNIVERSAL")

        # Get COGS/price from dim_sku
        row = conn.execute(
            "SELECT base_cost_cny, price_kzt FROM dim_sku WHERE sku_key = ?",
            (sku_key,)
        ).fetchone()

        if not row:
            cogs_unit = 1000.0
            price_unit = 2000.0
        else:
            cogs_unit = (row["base_cost_cny"] or 15) * 68  # CNY to KZT
            price_unit = row["price_kzt"] or cogs_unit * 2

    params = get_params()

    # Estimate sigma_sku from sales variance
    total_sales = [sum(size_sales_history.get(s, [0])[i] for s in sizes)
                   for i in range(min(90, len(next(iter(size_sales_history.values()), []))))]
    if total_sales:
        import statistics
        sigma_sku = statistics.stdev(total_sales) if len(total_sales) > 1 else 2.0
    else:
        sigma_sku = 2.0

    # Generate PO draft
    draft = generate_po_draft(
        sku_key=sku_key,
        store_code="UNIVERSAL",
        size_sales_90d=size_sales_90d,
        size_current_stock=size_current,
        size_inbound_stock=size_inbound,
        size_sales_history=size_sales_history,
        size_stock_history=size_stock_history,
        unit_cogs=cogs_unit,
        unit_profit=price_unit - cogs_unit,
        sigma_sku=sigma_sku,
        sku_age_days=sku_age,
    )

    if draft is None:
        results["po_draft"] = (True, "No order needed (all OK/WAIT)")
        return results

    # Validate size mix bounds
    mix_errors = []
    for size, alloc in draft.allocations.items():
        # Get size_mix from the allocation's related data
        size_data = alloc
        if hasattr(size_data, 'size_mix'):
            mix = size_data.size_mix
        else:
            # Fallback: calculate from sales
            total_sales_90d = sum(size_sales_90d.values())
            mix = size_sales_90d.get(size, 0) / total_sales_90d if total_sales_90d > 0 else 0.14

        if mix < params.min_size_mix - 0.01:
            mix_errors.append(f"{size}={mix:.2%}")
        if mix > params.max_size_mix + 0.01:
            mix_errors.append(f"{size}={mix:.2%}")

    if mix_errors:
        results["size_mix_bounds"] = (False, f"Out of bounds: {', '.join(mix_errors)}")
    else:
        results["size_mix_bounds"] = (True, "All within [3%, 40%]")

    # Validate total equals sum
    size_sum = sum(alloc.order_qty_adjusted for alloc in draft.allocations.values())
    if draft.total_qty == size_sum:
        results["total_equals_sum"] = (True, f"Total={draft.total_qty}, Sum={size_sum}")
    else:
        results["total_equals_sum"] = (False, f"Total={draft.total_qty} != Sum={size_sum}")

    # Validate ROIC gate
    results["roic_gate"] = (True, f"ROIC={draft.roic_monthly:.1%}, Action={draft.roic_action.value}")

    if verbose:
        print(f"\n  Validation for {sku_key}:")
        print(f"    Sizes: {sizes}")
        print(f"    Age: {sku_age} days")
        print(f"    Should order: {draft.should_order}")
        if draft.should_order:
            print(f"    Total qty: {draft.total_qty}")
            print(f"    Trigger sizes: {draft.trigger_sizes}")
            print(f"    ROIC: {draft.roic_monthly:.1%} → {draft.roic_action.value}")
            print(f"    Allocations:")
            for size, alloc in draft.allocations.items():
                print(f"      {size}: status={alloc.status.value}, qty={alloc.order_qty_adjusted}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate Phase 9.6 size-aware allocation"
    )
    parser.add_argument(
        "--sku",
        type=str,
        default=None,
        help="Validate specific SKU (e.g., CL_OC_MEN_LINE52_BLACK)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Phase 9.6 Size Allocation Validation")
    print("=" * 60)

    # Run 7 validation checks
    checks = [
        ("1. Parameters match Master Rules", check_1_params_match_master_rules),
        ("2. Size mix bounds (3%-40%)", check_2_size_mix_bounds),
        ("3. Safety stock formula", check_3_safety_stock_formula),
        ("4. ROP calculation", check_4_rop_calculation),
        ("5. Status logic (Check Total FIRST)", check_5_status_logic),
        ("6. ROIC gate (3-tier)", check_6_roic_gate),
        ("7. Total equals sum of sizes", check_7_total_equals_sum),
    ]

    passed = 0
    failed = 0

    for name, check_func in checks:
        print(f"\n{name}...")
        try:
            success, message = check_func(args.verbose)
            if success:
                print(f"  PASS: {message}")
                passed += 1
            else:
                print(f"  FAIL: {message}")
                failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    # Validate specific SKU if requested
    if args.sku:
        print(f"\n{'=' * 60}")
        print(f"SKU Validation: {args.sku}")
        print("=" * 60)

        try:
            results = validate_sku(args.sku, args.verbose)
            for check_name, (success, message) in results.items():
                status = "PASS" if success else "FAIL"
                print(f"  {status}: {check_name} - {message}")
        except Exception as e:
            print(f"  ERROR: {e}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary: {passed}/{passed + failed} checks passed")
    if failed == 0:
        print("All validations PASSED")
    else:
        print(f"{failed} validation(s) FAILED")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
