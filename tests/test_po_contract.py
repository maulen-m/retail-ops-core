"""
Contract tests for PO outputs.

Validates size-aware PO engine outputs against deterministic golden fixtures and
contract tolerances defined in docs/validation/PO_CONTRACT.md.
"""

import hashlib
import json
from pathlib import Path

import pytest

from core.calc.size_allocation import generate_po_draft

PROJECT_ROOT = Path(__file__).parent.parent
CONTRACT_PATH = PROJECT_ROOT / "docs" / "validation" / "PO_CONTRACT.md"
CASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "po_golden" / "po_contract_cases.json"
EXPECTED_PATH = PROJECT_ROOT / "tests" / "fixtures" / "po_golden" / "po_contract_expected.json"


def load_tolerances() -> dict:
    """Parse tolerances from PO_CONTRACT.md (single source of truth)."""
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    tolerances = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("D_30_pct:"):
            tolerances["d_30_pct"] = float(line.split(":", 1)[1].strip()) / 100.0
        elif line.startswith("SS_total_pct:"):
            tolerances["ss_total_pct"] = float(line.split(":", 1)[1].strip()) / 100.0
        elif line.startswith("ROIC_pct:"):
            tolerances["roic_pct"] = float(line.split(":", 1)[1].strip()) / 100.0

    missing = [k for k in ("d_30_pct", "ss_total_pct", "roic_pct") if k not in tolerances]
    if missing:
        raise AssertionError(f"Missing tolerances in PO_CONTRACT.md: {missing}")
    return tolerances


def canonicalize(draft) -> dict:
    """Canonical output for hashing and golden comparison (exclude timestamps)."""
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


def hash_payload(payload: dict) -> str:
    """Deterministic SHA-256 hash of canonical payload."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def assert_within_pct(actual: float, expected: float, pct: float, label: str) -> None:
    if expected == 0:
        assert abs(actual - expected) < 1e-9, f"{label} expected 0, got {actual}"
        return
    delta = abs(actual - expected) / abs(expected)
    assert delta <= pct, f"{label} drift {delta:.4f} > {pct:.4f} (actual={actual}, expected={expected})"


@pytest.fixture(scope="module")
def tolerances():
    return load_tolerances()


@pytest.fixture(scope="module")
def cases():
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


@pytest.fixture(scope="module")
def expected_map():
    payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


@pytest.mark.parametrize("case", json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"])
def test_po_contract_against_golden(case, tolerances, expected_map):
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

    actual = canonicalize(draft)

    assert_within_pct(actual["d_sku"], expected_entry["d_sku"], tolerances["d_30_pct"], "d_sku")
    assert_within_pct(actual["ss_total_sku"], expected_entry["ss_total_sku"], tolerances["ss_total_pct"], "ss_total_sku")
    assert_within_pct(actual["roic_monthly"], expected_entry["roic_monthly"], tolerances["roic_pct"], "roic_monthly")

    assert actual["roic_action"] == expected_entry["roic_action"], "roic_action mismatch"
    assert actual["should_order"] == expected_entry["should_order"], "should_order mismatch"
    assert actual["total_qty"] == expected_entry["total_qty"], "total_qty mismatch"
    assert actual["allocations"] == expected_entry["allocations"], "allocations mismatch"


@pytest.mark.parametrize("case", json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"])
def test_po_contract_hashes(case, expected_map):
    case_id = case["case_id"]
    expected_hash = expected_map[case_id]["hash"]

    draft_a = generate_po_draft(
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
    draft_b = generate_po_draft(
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

    actual_hash_a = hash_payload(canonicalize(draft_a))
    actual_hash_b = hash_payload(canonicalize(draft_b))

    assert actual_hash_a == expected_hash, "hash mismatch vs golden"
    assert actual_hash_a == actual_hash_b, "non-deterministic output between runs"
