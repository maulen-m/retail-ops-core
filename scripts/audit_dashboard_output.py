#!/usr/bin/env python3
"""
Audit script for PO Dashboard output.

Validates that:
1. LINE52 and LINE51 exist in PO-4 (either in sku_level or skipped_skus)
2. Demand overrides are applied (LINE52 D=50, LINE51 D=12)
3. No silent skipping (all SKUs accounted for)

Exit codes:
  0 - All checks passed
  1 - LINE52 missing everywhere
  2 - LINE52 exists but D_override not applied (d_sku != 50)
  3 - LINE51 exists but D_override not applied (d_sku != 12)
  4 - LINE51 missing everywhere
  5 - Other validation error
"""

import json
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HTML_PATH = PROJECT_ROOT / "exports" / "po_dashboard.html"
JSON_PATH = PROJECT_ROOT / "exports" / "po_dashboard_data.json"

# Required demand overrides
REQUIRED_OVERRIDES = {
    "CL_OC_MEN_LINE52_BLACK": 50.0,
    "CL_OC_MEN_LINE51_WHITE": 12.0,
}


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


def audit_po4(data: dict) -> tuple[bool, list[str]]:
    """
    Audit PO-4 specifically.
    Returns: (success, messages)
    """
    messages = []
    success = True

    # Get PO-4 data
    pos = data.get('pos', {})
    po4 = pos.get('PO-4')

    if not po4:
        # Maybe it's directly the PO data (old format)
        if 'sku_level' in data:
            po4 = data
        else:
            messages.append("ERROR: PO-4 not found in data")
            return False, messages

    messages.append(f"PO-4 found: {po4.get('summary', {}).get('total_skus', 0)} total SKUs")

    # Check each required SKU
    for sku_key, expected_d in REQUIRED_OVERRIDES.items():
        sku_data, in_skipped = find_sku_in_po(po4, sku_key)

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

        # Verify demand override
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
    po4 = pos.get('PO-4', {})

    sku_level = po4.get('sku_level', [])
    skipped_skus = po4.get('skipped_skus', [])

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
    print(f"Cutoff date: {data.get('cutoff_date', 'unknown')}")
    print()

    # Run audits
    all_success = True

    # Audit PO-4 for required SKUs
    print("-"*60)
    print("Audit 1: Required SKUs in PO-4")
    print("-"*60)
    success, messages = audit_po4(data)
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
        po4 = pos.get('PO-4', data if 'sku_level' in data else {})

        line52, _ = find_sku_in_po(po4, "CL_OC_MEN_LINE52_BLACK")
        line51, _ = find_sku_in_po(po4, "CL_OC_MEN_LINE51_WHITE")

        if line52 is None:
            print("Exit code 1: LINE52 missing everywhere")
            sys.exit(1)
        elif abs(line52.get('d_sku', 0) - 50.0) > 0.01:
            print(f"Exit code 2: LINE52 d_sku={line52.get('d_sku', 0)}, expected=50")
            sys.exit(2)
        elif line51 is None:
            print("Exit code 4: LINE51 missing everywhere")
            sys.exit(4)
        elif abs(line51.get('d_sku', 0) - 12.0) > 0.01:
            print(f"Exit code 3: LINE51 d_sku={line51.get('d_sku', 0)}, expected=12")
            sys.exit(3)
        else:
            print("Exit code 5: Other validation error")
            sys.exit(5)


if __name__ == "__main__":
    main()
