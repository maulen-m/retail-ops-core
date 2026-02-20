#!/usr/bin/env python3
"""
Audit script for PO Dashboard output.

Validates that:
1. LINE52 and LINE51 exist in PLAN-0 (either in sku_level or skipped_skus)
2. Demand overrides are applied (LINE52 D=40 or D=30 depending on window, LINE51 D=12)
3. No silent skipping (all SKUs accounted for)

Exit codes:
  0 - All checks passed
  1 - LINE52 missing everywhere
  2 - LINE52 exists but D_override not applied (d_sku != expected)
  3 - LINE51 exists but D_override not applied (d_sku != 12)
  4 - LINE51 missing everywhere
  5 - Other validation error
"""

import json
import sys
import re
import sqlite3
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HTML_PATH = PROJECT_ROOT / "exports" / "po_dashboard.html"
JSON_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Required demand overrides (time-boxed)
REQUIRED_OVERRIDES = {
    "CL_OC_MEN_LINE52_BLACK": [
        {
            "d_override": 30.0,
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
            "reason": "CNY slowdown window 1; PO-5 readiness",
        },
        {
            "d_override": 30.0,
            "start_date": "2026-03-01",
            "end_date": "2026-06-01",
            "reason": "CNY slowdown window 2; post-blackout normalization",
        },
    ],
    "CL_OC_MEN_LINE51_WHITE": [
        {
            "d_override": 12.0,
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
            "reason": "Marketing uplift + new Kaspi images",
        }
    ],
}

REQUIRED_SKUS = list(REQUIRED_OVERRIDES.keys())


def load_data_from_html(html_path: Path) -> dict | None:
    """Extract embedded DATA from HTML file."""
    if not html_path.exists():
        return None

    content = html_path.read_text()

    # Look for const DATA = {...}
    match = re.search(r'const\s+DATA\s*=\s*(\{.*?\});', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def load_data_from_json(json_path: Path) -> dict | None:
    """Load data from JSON file."""
    if not json_path.exists():
        return None

    with open(json_path) as f:
        return json.load(f)


def _normalize_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def required_overrides_for_date(as_of_date: date) -> dict:
    required = {}
    for sku_key, windows in REQUIRED_OVERRIDES.items():
        for meta in windows:
            start = _normalize_date(meta.get("start_date"))
            end = _normalize_date(meta.get("end_date"))
            if start and end and start <= as_of_date < end:
                required[sku_key] = meta
                break
    return required


def load_active_overrides(
    conn: sqlite3.Connection,
    as_of_date: date,
    sku_keys: list[str]
) -> dict[str, float]:
    if not sku_keys:
        return {}
    as_of = as_of_date.isoformat()
    cursor = conn.execute("""
        SELECT sku_key, d_override, start_date
        FROM dim_demand_overrides
        WHERE active_flag = 1
          AND (start_date IS NULL OR start_date <= ?)
          AND (end_date IS NULL OR end_date > ?)
          AND sku_key IN ({placeholders})
        ORDER BY start_date DESC
    """.format(placeholders=",".join(["?"] * len(sku_keys))), [as_of, as_of, *sku_keys])
    overrides = {}
    for sku_key, d_override, _ in cursor.fetchall():
        if sku_key not in overrides:
            overrides[sku_key] = d_override
    return overrides


def find_sku_in_po(po_data: dict, sku_key: str) -> tuple[dict | None, bool]:
    """
    Find SKU in PO data.
    Returns: (sku_data, found_in_skipped)
    """
    # Check sku_level
    for sku in po_data.get('sku_level', []):
        if sku.get('sku_key') == sku_key:
            return sku, False

    # Check skipped_skus
    skipped = po_data.get('skipped_skus', [])
    if isinstance(skipped, list):
        for skip in skipped:
            if isinstance(skip, dict) and skip.get('sku_key') == sku_key:
                return skip, True
            elif isinstance(skip, str) and skip == sku_key:
                return {'sku_key': sku_key, 'reason': 'unknown'}, True
    elif isinstance(skipped, dict):
        if sku_key in skipped:
            return {'sku_key': sku_key, 'reason': skipped[sku_key]}, True

    return None, False


def audit_plan0(data: dict, required_overrides: dict) -> tuple[bool, list[str]]:
    """
    Audit PLAN-0 specifically.
    Returns: (success, messages)
    """
    messages = []
    success = True

    # Get PLAN-0 data
    pos = data.get('pos', {})
    plan0 = pos.get('PLAN-0')

    if not plan0:
        # Maybe it's directly the PO data (old format)
        if 'sku_level' in data:
            plan0 = data
        else:
            messages.append("ERROR: PLAN-0 not found in data")
            return False, messages

    messages.append(f"PLAN-0 found: {plan0.get('summary', {}).get('total_skus', 0)} total SKUs")

    # Check each required SKU
    for sku_key in REQUIRED_SKUS:
        expected_d = required_overrides.get(sku_key, {}).get("d_override")
        sku_data, in_skipped = find_sku_in_po(plan0, sku_key)

        if sku_data is None:
            messages.append(f"FAIL: {sku_key} MISSING from both sku_level and skipped_skus")
            success = False
            continue

        location = "skipped_skus" if in_skipped else "sku_level"
        messages.append(f"FOUND: {sku_key} in {location}")

        # Check demand override
        actual_d = sku_data.get('d_sku', 0)
        po_qty = sku_data.get('po_qty_total', 0)
        notes = sku_data.get('notes', '')

        messages.append(f"  d_sku={actual_d}, po_qty_total={po_qty}")
        messages.append(f"  notes: {notes}")

        # Verify demand override (only if required for this date)
        if expected_d is not None:
            if abs(actual_d - expected_d) > 0.01:
                messages.append(f"FAIL: {sku_key} d_sku={actual_d}, expected={expected_d}")
                success = False
            else:
                messages.append(f"OK: {sku_key} demand override applied (d_sku={actual_d})")

        # Check D_OVERRIDE note
        if 'D_OVERRIDE' not in notes:
            messages.append(f"WARN: {sku_key} missing D_OVERRIDE in notes")

    return success, messages


def audit_prep_model(data: dict) -> tuple[bool, list[str]]:
    """
    Audit Model B prep days.
    - All CL SKUs in a PO should have the same prep_days
    - All ELS SKUs should have prep_days=1
    """
    messages = []
    success = True

    pos = data.get('pos', {})

    for po_name, po_data in pos.items():
        if not isinstance(po_data, dict):
            continue

        sku_level = po_data.get('sku_level', [])

        # Group by product type
        cl_prep_days = set()
        els_prep_days = set()

        for sku in sku_level:
            sku_key = sku.get('sku_key', '')
            prep = sku.get('prep_days', 0)
            qty = sku.get('po_qty_total', 0)

            if qty == 0:
                continue  # Skip SKUs with no order

            if sku_key.startswith('ELS_'):
                els_prep_days.add(prep)
                if prep != 1:
                    messages.append(f"FAIL: {po_name} {sku_key} ELS prep_days={prep}, expected=1")
                    success = False
            elif sku_key.startswith('CL_'):
                cl_prep_days.add(prep)

        # All CL SKUs should have same prep_days
        if len(cl_prep_days) > 1:
            messages.append(f"WARN: {po_name} has multiple CL prep_days values: {cl_prep_days}")
        elif cl_prep_days:
            messages.append(f"OK: {po_name} all CL SKUs have prep_days={list(cl_prep_days)[0]}")

        # All ELS should have prep_days=1
        if els_prep_days and els_prep_days != {1}:
            messages.append(f"FAIL: {po_name} ELS prep_days should be 1, got: {els_prep_days}")
            success = False
        elif els_prep_days:
            messages.append(f"OK: {po_name} all ELS SKUs have prep_days=1")

    return success, messages


def audit_no_silent_skips(data: dict) -> tuple[bool, list[str]]:
    """
    Verify no silent skipping - every SKU in universe should appear somewhere.
    """
    messages = []

    pos = data.get('pos', {})
    plan0 = pos.get('PLAN-0', {})

    sku_level = plan0.get('sku_level', [])
    skipped_skus = plan0.get('skipped_skus', [])

    total_in_sku_level = len(sku_level)
    total_skipped = len(skipped_skus) if isinstance(skipped_skus, (list, dict)) else 0

    messages.append(f"SKUs in sku_level: {total_in_sku_level}")
    messages.append(f"SKUs in skipped_skus: {total_skipped}")
    messages.append(f"Total accounted: {total_in_sku_level + total_skipped}")

    return True, messages


def main():
    print("="*60)
    print("PO Dashboard Audit")
    print("="*60)

    # Try to load data
    data = load_data_from_json(JSON_PATH)
    if not data:
        data = load_data_from_html(HTML_PATH)

    if not data:
        print("ERROR: Could not load data from JSON or HTML")
        sys.exit(5)

    print(f"Data loaded from: {JSON_PATH if JSON_PATH.exists() else HTML_PATH}")
    print(f"Generated at: {data.get('generated_at', 'unknown')}")
    cutoff_raw = data.get('cutoff_date', 'unknown')
    print(f"Cutoff date: {cutoff_raw}")
    print()

    cutoff_date = _normalize_date(cutoff_raw) or date.today()
    required_overrides = required_overrides_for_date(cutoff_date)

    if required_overrides:
        if not DB_PATH.exists():
            print("ERROR: Database missing; cannot verify active demand overrides.")
            print("Fix: restore db/app.db and run:")
            print("  python3 scripts/upsert_demand_overrides.py --seed-defaults")
            sys.exit(5)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_demand_overrides'"
            ).fetchone()
            if not table:
                print("ERROR: dim_demand_overrides table missing.")
                print("Fix: run:")
                print("  python3 scripts/upsert_demand_overrides.py --seed-defaults")
                sys.exit(5)

            active_overrides = load_active_overrides(
                conn, cutoff_date, list(required_overrides.keys())
            )
        finally:
            conn.close()

        missing = []
        mismatched = []
        for sku_key, meta in required_overrides.items():
            expected = meta["d_override"]
            actual = active_overrides.get(sku_key)
            if actual is None:
                missing.append(sku_key)
            elif abs(actual - expected) > 0.01:
                mismatched.append(f"{sku_key}={actual} (expected {expected})")

        if missing or mismatched:
            print("ERROR: Active demand overrides missing or incorrect.")
            if missing:
                print(f"  Missing overrides: {', '.join(missing)}")
            if mismatched:
                print(f"  Mismatched overrides: {', '.join(mismatched)}")
            print("Fix: run:")
            print("  python3 scripts/upsert_demand_overrides.py --seed-defaults")
            sys.exit(5)

    # Run audits
    all_success = True

    # Audit PLAN-0 for required SKUs
    print("-"*60)
    print("Audit 1: Required SKUs in PLAN-0")
    print("-"*60)
    success, messages = audit_plan0(data, required_overrides)
    for msg in messages:
        print(f"  {msg}")
    if not success:
        all_success = False
    print()

    # Audit prep model
    print("-"*60)
    print("Audit 2: Prep Model B")
    print("-"*60)
    success, messages = audit_prep_model(data)
    for msg in messages:
        print(f"  {msg}")
    if not success:
        all_success = False
    print()

    # Audit no silent skips
    print("-"*60)
    print("Audit 3: No Silent Skipping")
    print("-"*60)
    success, messages = audit_no_silent_skips(data)
    for msg in messages:
        print(f"  {msg}")
    print()

    # Summary
    print("="*60)
    if all_success:
        print("AUDIT PASSED")
        sys.exit(0)
    else:
        print("AUDIT FAILED")
        # Determine specific exit code
        pos = data.get('pos', {})
        plan0 = pos.get('PLAN-0', data if 'sku_level' in data else {})

        line52, _ = find_sku_in_po(plan0, "CL_OC_MEN_LINE52_BLACK")
        line51, _ = find_sku_in_po(plan0, "CL_OC_MEN_LINE51_WHITE")

        if line52 is None:
            print("Exit code 1: LINE52 missing everywhere")
            sys.exit(1)
        elif "CL_OC_MEN_LINE52_BLACK" in required_overrides and abs(line52.get('d_sku', 0) - required_overrides["CL_OC_MEN_LINE52_BLACK"]["d_override"]) > 0.01:
            expected = required_overrides["CL_OC_MEN_LINE52_BLACK"]["d_override"]
            print(f"Exit code 2: LINE52 d_sku={line52.get('d_sku', 0)}, expected={expected}")
            sys.exit(2)
        elif line51 is None:
            print("Exit code 4: LINE51 missing everywhere")
            sys.exit(4)
        elif "CL_OC_MEN_LINE51_WHITE" in required_overrides and abs(line51.get('d_sku', 0) - required_overrides["CL_OC_MEN_LINE51_WHITE"]["d_override"]) > 0.01:
            expected = required_overrides["CL_OC_MEN_LINE51_WHITE"]["d_override"]
            print(f"Exit code 3: LINE51 d_sku={line51.get('d_sku', 0)}, expected={expected}")
            sys.exit(3)
        else:
            print("Exit code 5: Other validation error")
            sys.exit(5)


if __name__ == "__main__":
    main()
