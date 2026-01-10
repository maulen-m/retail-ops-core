#!/usr/bin/env python3
"""
Update PO Dashboard HTML with latest data.

Usage:
    python scripts/update_po_dashboard.py

This script:
1. Runs generate_po_dashboard_data.py to create fresh JSON
2. Updates po_dashboard.html with the new data
"""

import subprocess
import sys
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_FILE = PROJECT_ROOT / "exports" / "po_dashboard_data.json"
HTML_FILE = PROJECT_ROOT / "exports" / "po_dashboard.html"


def main():
    print("Step 1: Generating fresh PO data...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_po_dashboard_data.py")],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return 1

    print("\nStep 2: Updating HTML dashboard...")
    html_result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_po_dashboard_html.py")],
        capture_output=True,
        text=True
    )
    if html_result.returncode != 0:
        print(f"Error: {html_result.stderr}")
        return 1
    print(html_result.stdout)

    with open(DATA_FILE) as f:
        data = json.load(f)

    print(f"Dashboard updated: {HTML_FILE}")
    print(f"  - SKUs: {data['summary']['total_skus']}")
    print(f"  - Units: {data['summary']['total_units']}")
    print(f"  - Priority: {data['summary']['priority_skus']}")
    print(f"\nOpen in browser: file://{HTML_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
