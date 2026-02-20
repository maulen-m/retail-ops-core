#!/usr/bin/env python3
"""Validate PO contract against golden fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from core.calc.size_allocation import generate_po_draft
from core.validation.tolerances import parse_po_contract_tolerances

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONTRACT = PROJECT_ROOT / "docs" / "validation" / "PO_CONTRACT.md"
FIXTURE_BASE = PROJECT_ROOT / "tests" / "fixtures" / "po_golden"
DEFAULT_CASES = FIXTURE_BASE / "po_contract_cases.json"
DEFAULT_EXPECTED = FIXTURE_BASE / "po_contract_expected.json"


def resolve_fixture_paths(
    fixture: str | None,
    cases_path: Path | None = None,
    expected_path: Path | None = None,
) -> tuple[Path, Path]:
    if cases_path is not None or expected_path is not None:
        return (cases_path or DEFAULT_CASES, expected_path or DEFAULT_EXPECTED)

    if fixture in (None, "", "small"):
        return DEFAULT_CASES, DEFAULT_EXPECTED

    fixture_dir = FIXTURE_BASE / fixture
    cases = fixture_dir / "po_contract_cases.json"
    expected = fixture_dir / "po_contract_expected.json"
    if not cases.exists() or not expected.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_dir}")
    return cases, expected


def _canonicalize(draft) -> dict:
    return {
        "d_sku": round(draft.d_sku, 6),
        "ss_total_sku": round(draft.ss_total_sku, 6),
        "rop_sku": round(draft.rop_sku, 6),
        "roic_monthly": round(draft.roic_monthly, 6),
        "roic_action": draft.roic_action.value,
        "should_order": bool(draft.should_order),
        "total_qty": int(draft.total_qty),
        "allocations": {k: int(v.order_qty_adjusted) for k, v in draft.allocations.items()},
    }


def _hash_payload(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def run_contract(
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    cases_path: Path = DEFAULT_CASES,
    expected_path: Path = DEFAULT_EXPECTED,
) -> dict:
    tolerances = parse_po_contract_tolerances(contract_path)
    cases_payload = json.loads(cases_path.read_text(encoding="utf-8"))
    expected_payload = json.loads(expected_path.read_text(encoding="utf-8"))

    failures = []
    expected_map = expected_payload["cases"]

    for case in cases_payload["cases"]:
        case_id = case["case_id"]
        expected_entry = expected_map[case_id]["expected"]

        draft = generate_po_draft(
            sku_key=case["sku_key"],
            store_code=case["store_code"],
            size_sales_90d=case["size_sales_90d"],
            size_current_stock=case["size_current_stock"],
            size_inbound_stock=case["size_inbound_stock"],
            size_sales_history=case["size_sales_history"],
            size_stock_history=case["size_stock_history"],
            unit_cogs=case["unit_cogs"],
            unit_profit=case["unit_profit"],
            sigma_sku=case["sigma_sku"],
            sku_age_days=case["sku_age_days"],
        )

        actual = _canonicalize(draft)

        def check_pct(field: str, actual_val: float, expected_val: float, pct: float) -> None:
            if expected_val == 0:
                ok = abs(actual_val - expected_val) < 1e-9
            else:
                ok = abs(actual_val - expected_val) / abs(expected_val) <= pct
            if not ok:
                failures.append(
                    {
                        "case_id": case_id,
                        "field": field,
                        "expected": expected_val,
                        "actual": actual_val,
                        "tolerance": pct,
                    }
                )

        check_pct("d_sku", actual["d_sku"], expected_entry["d_sku"], tolerances["d_30_ratio"])
        check_pct(
            "ss_total_sku",
            actual["ss_total_sku"],
            expected_entry["ss_total_sku"],
            tolerances["ss_total_ratio"],
        )
        check_pct(
            "roic_monthly",
            actual["roic_monthly"],
            expected_entry["roic_monthly"],
            tolerances["roic_ratio"],
        )

        if actual["roic_action"] != expected_entry["roic_action"]:
            failures.append(
                {
                    "case_id": case_id,
                    "field": "roic_action",
                    "expected": expected_entry["roic_action"],
                    "actual": actual["roic_action"],
                }
            )
        if actual["should_order"] != expected_entry["should_order"]:
            failures.append(
                {
                    "case_id": case_id,
                    "field": "should_order",
                    "expected": expected_entry["should_order"],
                    "actual": actual["should_order"],
                }
            )
        if actual["total_qty"] != expected_entry["total_qty"]:
            failures.append(
                {
                    "case_id": case_id,
                    "field": "total_qty",
                    "expected": expected_entry["total_qty"],
                    "actual": actual["total_qty"],
                }
            )
        if actual["allocations"] != expected_entry["allocations"]:
            failures.append(
                {
                    "case_id": case_id,
                    "field": "allocations",
                    "expected": expected_entry["allocations"],
                    "actual": actual["allocations"],
                }
            )

        expected_hash = expected_map[case_id]["hash"]
        actual_hash = _hash_payload(actual)
        if actual_hash != expected_hash:
            failures.append(
                {
                    "case_id": case_id,
                    "field": "hash",
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )

    return {"ok": len(failures) == 0, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PO contract fixtures")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--fixture", type=str, default="small", help="Fixture set name")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--expected", type=Path, default=None)
    args = parser.parse_args()

    cases_path, expected_path = resolve_fixture_paths(
        args.fixture,
        args.cases,
        args.expected,
    )

    result = run_contract(
        contract_path=args.contract,
        cases_path=cases_path,
        expected_path=expected_path,
    )

    if result["ok"]:
        print("PO contract: PASS")
        return 0

    print("PO contract: FAIL")
    for failure in result["failures"][:20]:
        print(f"- {failure}")
    if len(result["failures"]) > 20:
        print(f"... ({len(result['failures']) - 20} more)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
