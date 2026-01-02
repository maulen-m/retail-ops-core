#!/usr/bin/env python3
"""
Ops preflight checks for Kaspi fulfillment workflow.

Checks:
- CRM workbook exists (auto-restore from latest backup if missing).
- Backups folder exists.
- Required CRM columns exist.
- ENABLE_KASPI_WRITE=1 if running shipping.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path, get_data_root


DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_BACKUPS = data_path("excel_ui", "backups")
DEFAULT_SHEET = "SALES_KSP_CRM_1"

REQUIRED_COLUMNS = {
    "order_id": {"OrderID", "№ заказа"},
    "my_size": {"MY_SIZE"},
    "planned_ship": {"PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"},
}


def _normalize(s: str) -> str:
    return "".join(str(s).strip().lower().split())


def _find_backup(backups_dir: Path) -> Path | None:
    patterns = ["*.backup_*.xlsx", "CRM_backup_*.xlsx"]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(backups_dir.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _restore_crm(crm_path: Path, backups_dir: Path) -> bool:
    backup = _find_backup(backups_dir)
    if not backup:
        print(
            "ERROR: CRM workbook missing and no backups found.\n"
            f"Expected: {crm_path}\n"
            f"Backups dir: {backups_dir}"
        )
        return False
    crm_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, crm_path)
    print(f"Restored CRM from backup: {backup}")
    return True


def _check_required_columns(df: pd.DataFrame) -> list[str]:
    missing = []
    normalized_cols = {_normalize(c): c for c in df.columns}
    for key, aliases in REQUIRED_COLUMNS.items():
        if any(_normalize(a) in normalized_cols for a in aliases):
            continue
        missing.append(key)
    return missing


def _check_crm_columns(crm_path: Path, sheet_name: str) -> bool:
    try:
        df = pd.read_excel(crm_path, sheet_name=sheet_name, nrows=1)
    except ValueError as exc:
        print(f"ERROR: Sheet not found in CRM: {sheet_name} ({exc})")
        return False
    except Exception as exc:
        print(f"ERROR: Failed to read CRM workbook: {exc}")
        return False

    missing = _check_required_columns(df)
    if missing:
        print(
            "ERROR: CRM workbook missing required columns:\n"
            f"  Missing: {', '.join(missing)}\n"
            f"  CRM: {crm_path} (sheet: {sheet_name})"
        )
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Ops preflight for Kaspi workflows")
    parser.add_argument("--crm-file", type=Path, default=DEFAULT_CRM)
    parser.add_argument("--backups-dir", type=Path, default=DEFAULT_BACKUPS)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--inventory-file", type=Path, default=None)
    parser.add_argument("--shipping", action="store_true", help="Require ENABLE_KASPI_WRITE=1")
    args = parser.parse_args()

    ok = True

    print(f"Data root: {get_data_root()}")

    if not args.backups_dir.exists():
        print(f"ERROR: Backups folder missing: {args.backups_dir}")
        print("Create it or restore from backup before proceeding.")
        ok = False

    if not args.crm_file.exists():
        if not args.backups_dir.exists():
            ok = False
        else:
            ok = _restore_crm(args.crm_file, args.backups_dir) and ok

    if args.inventory_file is not None and not args.inventory_file.exists():
        print(f"ERROR: Inventory workbook missing: {args.inventory_file}")
        ok = False

    if args.crm_file.exists():
        ok = _check_crm_columns(args.crm_file, args.sheet) and ok

    if args.shipping and os.environ.get("ENABLE_KASPI_WRITE") != "1":
        print("ERROR: ENABLE_KASPI_WRITE is not set to 1. Refusing to ship.")
        ok = False

    if not ok:
        return 1

    print("Preflight OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
