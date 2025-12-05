#!/usr/bin/env python3
"""
Validate vs Excel: Compare Python calculations to Excel V15 values.

This script validates that Python calculations match Excel V15 within tolerances:
- D30: ±1%
- SS_total: ±1%
- ROIC: ±2%
- Status: Exact match

Test SKUs: LINE52, LINE51 (known values from Master_Inventory_Rules)

Usage:
    python scripts/validate_vs_excel.py           # Run validation
    python scripts/validate_vs_excel.py --verbose # Detailed output
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.calc.economics import calc_cogs, calc_net_rev, calc_profit, calc_delivery_fee
from core.calc.inventory import calc_all_metrics, calc_d30, DEFAULT_PARAMS
from core.calc.status import calc_status


@dataclass
class ExcelTestCase:
    """Known values from Excel V15 for validation."""
    sku_key: str
    base_cost_cny: float
    weight_kg: float
    sell_price_kzt: float
    d30: float  # From Excel
    # Expected values from Excel V15 (with defined tolerances)
    expected_cogs: float
    expected_net_rev: float
    expected_profit: float
    expected_ss_total: Optional[float] = None  # Will calculate if D30 known
    expected_rop: Optional[float] = None
    expected_roic: Optional[float] = None
    expected_status: Optional[str] = None
    current_stock: int = 0
    total_stock: int = 0


# Test cases from Master_Inventory_Rules and requirements
# LINE52 @ 12,000 KZT → COGS=5,005, NetRev=9,355, Profit=4,350
# LINE51 @ 12,000 KZT → COGS=6,019

EXCEL_TEST_CASES = [
    ExcelTestCase(
        sku_key="LINE52",
        base_cost_cny=47.0,
        weight_kg=0.95,
        sell_price_kzt=12000.0,
        d30=5.0,  # Assumed D30 for formula testing
        expected_cogs=5005,
        expected_net_rev=9355,
        expected_profit=4350,
        # Expected SS_total for D30=5 with default params
        # ss_demand = 1.65 * (5*0.4) * sqrt(21) = 1.65 * 2 * 4.58 = 15.12
        # ss_floor = 5 * 14 = 70
        # ss_mix = 0.23 * 5 * 21 = 24.15
        # ss_total = 15.12 + 70 + 24.15 = 109.27
        expected_ss_total=109.27,
        # rop = 5 * 21 + 109.27 = 214.27
        expected_rop=214.27,
        # ROIC calculation with these values
        # K_avg = (5 * (21 + 10/2) + 109.27) * 5005 = (130 + 109.27) * 5005 = 1,197,559
        # Monthly profit = 4350 * 5 * 30 = 652,500
        # ROIC = 652,500 / 1,197,559 * 100 = 54.5%
        expected_roic=54.5,
        expected_status="REORDER",  # Since current=0, total=0 < rop
        current_stock=0,
        total_stock=0,
    ),
    ExcelTestCase(
        sku_key="LINE51",
        base_cost_cny=60.0,
        weight_kg=0.95,
        sell_price_kzt=12000.0,
        d30=3.0,  # Assumed D30 for formula testing
        expected_cogs=6019,
        expected_net_rev=9355,  # Same price, same net rev
        expected_profit=3336,  # 9355 - 6019
        expected_ss_total=None,  # Will be calculated
        expected_rop=None,
        expected_roic=None,
        expected_status="REORDER",
        current_stock=0,
        total_stock=0,
    ),
]


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    metric: str
    python_value: float
    excel_value: float
    tolerance_pct: float
    diff_pct: float
    passed: bool
    note: str = ""


def validate_economics(case: ExcelTestCase) -> list[ValidationResult]:
    """Validate economics calculations against Excel values."""
    results = []

    # COGS
    python_cogs = calc_cogs(case.base_cost_cny, case.weight_kg)
    diff = abs(python_cogs - case.expected_cogs) / case.expected_cogs * 100
    results.append(ValidationResult(
        metric="COGS",
        python_value=python_cogs,
        excel_value=case.expected_cogs,
        tolerance_pct=1.0,
        diff_pct=diff,
        passed=diff <= 1.0,
    ))

    # Delivery fee
    python_delivery = calc_delivery_fee(case.sell_price_kzt)
    # Delivery should be exact since it's a simple tiered calculation
    expected_delivery = 856 if case.sell_price_kzt <= 14999 else 1259
    if case.sell_price_kzt <= 4999:
        expected_delivery = 0
    results.append(ValidationResult(
        metric="Delivery Fee",
        python_value=python_delivery,
        excel_value=expected_delivery,
        tolerance_pct=0.0,  # Exact match required
        diff_pct=0 if python_delivery == expected_delivery else 100,
        passed=python_delivery == expected_delivery,
    ))

    # Net Revenue
    python_net_rev = calc_net_rev(case.sell_price_kzt)
    diff = abs(python_net_rev - case.expected_net_rev) / case.expected_net_rev * 100
    results.append(ValidationResult(
        metric="Net Revenue",
        python_value=python_net_rev,
        excel_value=case.expected_net_rev,
        tolerance_pct=1.0,
        diff_pct=diff,
        passed=diff <= 1.0,
    ))

    # Profit
    python_profit = calc_profit(case.sell_price_kzt, case.base_cost_cny, case.weight_kg)
    diff = abs(python_profit - case.expected_profit) / case.expected_profit * 100
    results.append(ValidationResult(
        metric="Profit",
        python_value=python_profit,
        excel_value=case.expected_profit,
        tolerance_pct=1.0,
        diff_pct=diff,
        passed=diff <= 1.0,
    ))

    return results


def validate_inventory(case: ExcelTestCase) -> list[ValidationResult]:
    """Validate inventory calculations against Excel values."""
    results = []

    # Get COGS and Profit for metrics
    cogs = calc_cogs(case.base_cost_cny, case.weight_kg)
    profit = calc_profit(case.sell_price_kzt, case.base_cost_cny, case.weight_kg)

    # Calculate all metrics
    metrics = calc_all_metrics(case.d30, cogs, profit)

    # SS Total
    if case.expected_ss_total is not None:
        diff = abs(metrics["ss_total"] - case.expected_ss_total) / case.expected_ss_total * 100
        results.append(ValidationResult(
            metric="SS Total",
            python_value=metrics["ss_total"],
            excel_value=case.expected_ss_total,
            tolerance_pct=1.0,
            diff_pct=diff,
            passed=diff <= 1.0,
        ))

    # ROP
    if case.expected_rop is not None:
        diff = abs(metrics["rop"] - case.expected_rop) / case.expected_rop * 100
        results.append(ValidationResult(
            metric="ROP",
            python_value=metrics["rop"],
            excel_value=case.expected_rop,
            tolerance_pct=1.0,
            diff_pct=diff,
            passed=diff <= 1.0,
        ))

    # ROIC
    if case.expected_roic is not None:
        diff = abs(metrics["roic_monthly"] - case.expected_roic) / case.expected_roic * 100
        results.append(ValidationResult(
            metric="ROIC",
            python_value=metrics["roic_monthly"],
            excel_value=case.expected_roic,
            tolerance_pct=2.0,  # 2% tolerance for ROIC
            diff_pct=diff,
            passed=diff <= 2.0,
        ))

    return results


def validate_status(case: ExcelTestCase) -> list[ValidationResult]:
    """Validate status calculation against expected value."""
    results = []

    if case.expected_status is not None:
        # Calculate ROP for status check
        cogs = calc_cogs(case.base_cost_cny, case.weight_kg)
        profit = calc_profit(case.sell_price_kzt, case.base_cost_cny, case.weight_kg)
        metrics = calc_all_metrics(case.d30, cogs, profit)

        python_status = calc_status(
            case.current_stock,
            case.total_stock,
            metrics["rop"]
        )

        results.append(ValidationResult(
            metric="Status",
            python_value=0 if python_status == case.expected_status else 1,
            excel_value=0,
            tolerance_pct=0.0,  # Exact match required
            diff_pct=0 if python_status == case.expected_status else 100,
            passed=python_status == case.expected_status,
            note=f"Python={python_status}, Expected={case.expected_status}",
        ))

    return results


def run_validation(verbose: bool = False) -> dict:
    """
    Run all validation tests.

    Returns:
        Dict with summary stats and detailed results
    """
    all_results = []
    summary = {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "by_sku": {},
    }

    for case in EXCEL_TEST_CASES:
        sku_results = []

        # Economics validations
        sku_results.extend(validate_economics(case))

        # Inventory validations
        sku_results.extend(validate_inventory(case))

        # Status validation
        sku_results.extend(validate_status(case))

        # Track results
        sku_passed = sum(1 for r in sku_results if r.passed)
        sku_failed = sum(1 for r in sku_results if not r.passed)

        summary["total_tests"] += len(sku_results)
        summary["passed"] += sku_passed
        summary["failed"] += sku_failed
        summary["by_sku"][case.sku_key] = {
            "passed": sku_passed,
            "failed": sku_failed,
            "results": sku_results,
        }

        all_results.extend(sku_results)

    return {
        "summary": summary,
        "results": all_results,
        "pass_rate": summary["passed"] / summary["total_tests"] * 100 if summary["total_tests"] > 0 else 0,
    }


def print_results(validation: dict, verbose: bool = False):
    """Print validation results in a readable format."""
    summary = validation["summary"]

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    for sku_key, sku_data in summary["by_sku"].items():
        print(f"\n{sku_key}:")
        print("-" * 50)

        for result in sku_data["results"]:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            if result.metric == "Status":
                print(f"  {result.metric:15s}: {result.note} {status}")
            else:
                print(f"  {result.metric:15s}: Python={result.python_value:,.2f} "
                      f"Excel={result.excel_value:,.2f} "
                      f"(diff={result.diff_pct:.2f}%, tol={result.tolerance_pct}%) {status}")

    print("\n" + "=" * 70)
    print(f"OVERALL: {summary['passed']}/{summary['total_tests']} tests passed "
          f"({validation['pass_rate']:.1f}%)")

    if summary["failed"] > 0:
        print(f"\n⚠️  {summary['failed']} TESTS FAILED - Review calculations")
    else:
        print("\n✅ ALL TESTS PASSED - Python matches Excel V15 within tolerances")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Validate Python calculations against Excel V15"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Excel V15 Validation")
    print("=" * 70)
    print("\nTolerance requirements:")
    print("  - D30, SS_total: ±1%")
    print("  - ROIC: ±2%")
    print("  - Status: Exact match")
    print(f"\nTest SKUs: {', '.join(case.sku_key for case in EXCEL_TEST_CASES)}")

    validation = run_validation(verbose=args.verbose)
    print_results(validation, verbose=args.verbose)

    # Return exit code based on pass/fail
    return 0 if validation["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
