from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ACTIVE_AUTHORITY_SURFACES = [
    "docs/inventory/Sales_Data_Model_V16.md",
    "docs/inventory/Automation_Handoff_V16.md",
    "docs/inventory/Excel_UI_Contract_for_CRM_V1.md",
    "docs/inventory/Workflow_SOP_V2.md",
    "docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md",
    "core/po/recommender.py",
    "core/config/inventory_params.py",
    "core/calc/size_allocation.py",
    "core/parsers/kaspi_parser.py",
    "scripts/generate_po_dashboard_data.py",
    "scripts/validate_size_allocation.py",
    "tests/test_po_formulas.py",
    "tests/test_size_allocation.py",
    "db/schema.sql",
]

BANNED_STALE_AUTHORITY = {
    "Master_Inventory_Rules_v5.3": re.compile(r"Master_Inventory_Rules_v5\.3"),
    "Master_Inventory_Rules_v6": re.compile(r"Master_Inventory_Rules_v6"),
    "Sales_Data_Model_V15": re.compile(r"Sales_Data_Model_V15"),
    "update v8 first": re.compile(r"update v8 first", re.IGNORECASE),
    "See v8": re.compile(r"See v8", re.IGNORECASE),
    "v8/V16": re.compile(r"v8/V16"),
    "Kaspi, v8": re.compile(r"Kaspi, v8", re.IGNORECASE),
    "V15 formulas": re.compile(r"V15 formulas"),
}


def test_operational_stock_authority_surfaces_are_current() -> None:
    failures: list[str] = []
    for relative_path in ACTIVE_AUTHORITY_SURFACES:
        path = PROJECT_ROOT / relative_path
        text = path.read_text(encoding="utf-8")
        for label, pattern in BANNED_STALE_AUTHORITY.items():
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                failures.append(f"{relative_path}:{line_no}: stale authority pointer: {label}")

    assert failures == []
