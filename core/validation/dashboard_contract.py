"""Dashboard contract utilities for Phase 3 gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.calc.size_allocation import generate_po_draft, PODraft
from core.validation.tolerances import parse_po_contract_tolerances

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "po_golden" / "po_contract_cases.json"
DEFAULT_PO_CONTRACT = PROJECT_ROOT / "docs" / "validation" / "PO_CONTRACT.md"

DEFAULT_GENERATED_AT = "2026-01-01T00:00:00"
DEFAULT_CUTOFF_DATE = "2026-01-01"


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load deterministic fixture cases."""
    fixture_path = path or DEFAULT_FIXTURE
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return payload["cases"]


def build_drafts(cases: list[dict[str, Any]]) -> dict[str, PODraft]:
    """Build PODraft objects from fixture cases, keyed by sku_key."""
    drafts: dict[str, PODraft] = {}
    for case in cases:
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
        drafts[case["sku_key"]] = draft
    return drafts


def generate_dashboard_output(
    cases: list[dict[str, Any]],
    generated_at: str | None = None,
    cutoff_date: str | None = None,
) -> dict[str, Any]:
    """Generate a minimal dashboard output from fixture cases via production generator."""
    generated_at = generated_at or DEFAULT_GENERATED_AT
    cutoff_date = cutoff_date or DEFAULT_CUTOFF_DATE

    from scripts.generate_po_dashboard_data import generate_po_data

    po4 = generate_po_data(
        fixture_cases=cases,
        fixture_cutoff_date=cutoff_date,
        fixture_stock_date=cutoff_date,
        fixture_generated_at=generated_at,
    )

    summary = po4.get("summary", {})
    summary_min = {
        "total_skus": summary.get("total_skus", 0),
        "skus_with_orders": summary.get("skus_with_orders", 0),
        "total_units": summary.get("total_units", 0),
    }

    return {
        "generated_at": generated_at,
        "cutoff_date": cutoff_date,
        "summary": summary_min,
        "pos": {
            "PO-4": {
                "po_name": "PO-4",
                "summary": {
                    "total_skus": summary_min["total_skus"],
                    "total_units": summary_min["total_units"],
                },
                "sku_level": po4.get("sku_level", []),
            }
        },
    }


def _assert_within_pct(actual: float, expected: float, pct: float, label: str, errors: list[str]) -> None:
    if expected == 0:
        if abs(actual - expected) > 1e-9:
            errors.append(f"{label} expected 0, got {actual}")
        return
    delta = abs(actual - expected) / abs(expected)
    if delta > pct:
        errors.append(f"{label} drift {delta:.4f} > {pct:.4f} (actual={actual}, expected={expected})")


def validate_dashboard_output(
    output: dict[str, Any],
    drafts: dict[str, PODraft],
    tolerances: dict[str, float],
) -> list[str]:
    """Validate output against the dashboard contract invariants."""
    errors: list[str] = []

    for key in ("generated_at", "cutoff_date", "summary", "pos"):
        if key not in output:
            errors.append(f"Missing top-level key: {key}")

    summary = output.get("summary", {})
    for key in ("total_skus", "skus_with_orders", "total_units"):
        if key not in summary:
            errors.append(f"Missing summary key: {key}")

    pos = output.get("pos", {})
    if "PO-4" not in pos:
        errors.append("Missing PO-4 bucket in pos")
        return errors

    po4 = pos.get("PO-4", {})
    for key in ("po_name", "summary", "sku_level"):
        if key not in po4:
            errors.append(f"Missing PO-4 key: {key}")

    sku_level = po4.get("sku_level", [])
    if not isinstance(sku_level, list) or not sku_level:
        errors.append("PO-4 sku_level is empty or invalid")
        return errors

    total_units = 0
    skus_with_orders = 0

    for sku in sku_level:
        for key in ("sku_key", "d_sku", "po_qty_total", "size_orders", "roic_pct"):
            if key not in sku:
                errors.append(f"sku_level missing key: {key}")
                continue

        sku_key = sku.get("sku_key")
        if sku_key not in drafts:
            errors.append(f"sku_key not in fixture: {sku_key}")
            continue

        draft = drafts[sku_key]
        total_units += int(sku.get("po_qty_total", 0))
        if int(sku.get("po_qty_total", 0)) > 0:
            skus_with_orders += 1

        _assert_within_pct(
            sku.get("d_sku", 0.0),
            draft.d_sku,
            tolerances["d_30_ratio"],
            f"d_sku[{sku_key}]",
            errors,
        )
        _assert_within_pct(
            sku.get("roic_pct", 0.0),
            draft.roic_monthly * 100,
            tolerances["roic_ratio"],
            f"roic_pct[{sku_key}]",
            errors,
        )

        expected_qty = int(draft.total_qty)
        if int(sku.get("po_qty_total", 0)) != expected_qty:
            errors.append(f"po_qty_total[{sku_key}] {sku.get('po_qty_total')} != {expected_qty}")

        expected_sizes = {k: int(v.order_qty_adjusted) for k, v in draft.allocations.items()}
        if sku.get("size_orders") != expected_sizes:
            errors.append(f"size_orders mismatch for {sku_key}")

        if sum(sku.get("size_orders", {}).values()) != int(sku.get("po_qty_total", 0)):
            errors.append(f"size_orders sum != po_qty_total for {sku_key}")

    if summary.get("total_skus") != len(sku_level):
        errors.append("summary.total_skus does not match sku_level length")

    if summary.get("total_units") != total_units:
        errors.append("summary.total_units does not match sku_level total")

    if summary.get("skus_with_orders") != skus_with_orders:
        errors.append("summary.skus_with_orders does not match sku_level count")

    po_summary = po4.get("summary", {})
    if po_summary.get("total_skus") != len(sku_level):
        errors.append("PO-4 summary.total_skus mismatch")
    if po_summary.get("total_units") != total_units:
        errors.append("PO-4 summary.total_units mismatch")

    return errors


def canonicalize_output(output: dict[str, Any]) -> dict[str, Any]:
    """Canonical form for deterministic hashing."""
    return json.loads(json.dumps(output, sort_keys=True))


def hash_output(output: dict[str, Any]) -> str:
    """Stable SHA-256 of canonicalized output."""
    payload = json.dumps(canonicalize_output(output), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
