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
from datetime import datetime, date
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path, get_data_root


DEFAULT_CRM = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_BACKUPS = data_path("excel_ui", "backups")
DEFAULT_SAFETY_BACKUPS = data_path("backups")
DEFAULT_SHEET = "SALES_KSP_CRM_1"

REQUIRED_COLUMNS = {
    "order_id": {"OrderID", "№ заказа"},
    "my_size": {"MY_SIZE"},
    "planned_ship": {"PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"},
}


def _normalize(s: str) -> str:
    return "".join(str(s).strip().lower().split())


def _find_backup(backups_dirs: Iterable[Path], patterns: Iterable[str]) -> Path | None:
    candidates: list[Path] = []
    for backups_dir in backups_dirs:
        if not backups_dir or not backups_dir.exists():
            continue
        for pattern in patterns:
            candidates.extend(backups_dir.rglob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _restore_workbook(
    target_path: Path,
    backups_dirs: Iterable[Path],
    patterns: Iterable[str],
    label: str,
) -> bool:
    backup = _find_backup(backups_dirs, patterns)
    if not backup:
        print(
            f"ERROR: {label} workbook missing and no backups found.\n"
            f"Expected: {target_path}\n"
            f"Backups searched: {', '.join(str(p) for p in backups_dirs if p)}"
        )
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target_path)
    print(f"Restored {label} from backup: {backup}")
    return True


def _backup_workbook(src: Path, backup_root: Path, label: str) -> Path | None:
    if not src.exists():
        return None
    today_dir = backup_root / date.today().isoformat()
    try:
        today_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"WARNING: Failed to create backup dir {today_dir}: {exc}")
        return None

    existing = list(today_dir.glob(f"{label}_backup_*.xlsx"))
    if existing:
        return existing[0]

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = today_dir / f"{label}_backup_{ts}.xlsx"
    try:
        shutil.copy2(src, dest)
        print(f"Backup saved: {dest}")
        return dest
    except Exception as exc:
        print(f"WARNING: Failed to backup {label}: {exc}")
        return None


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
    parser.add_argument("--safety-backups-dir", type=Path, default=DEFAULT_SAFETY_BACKUPS)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--inventory-file", type=Path, default=None)
    parser.add_argument("--shipping", action="store_true", help="Require ENABLE_KASPI_WRITE=1")
    args = parser.parse_args()

    ok = True

    data_root = get_data_root()
    print(f"Data root: {data_root}")

    env_root = os.environ.get("AB_DATA_DIR") or os.environ.get("DATA_DIR")
    if env_root and not data_root.exists():
        print(
            "ERROR: DATA_DIR/AB_DATA_DIR points to a missing path.\n"
            f"  Path: {data_root}\n"
            f"  Fix: mkdir -p {data_root} (or unset DATA_DIR/AB_DATA_DIR)"
        )
        ok = False

    backup_dirs = [args.backups_dir, args.safety_backups_dir]

    if not args.backups_dir.exists():
        print(f"ERROR: Backups folder missing: {args.backups_dir}")
        print(f"Fix: mkdir -p {args.backups_dir}")
        ok = False

    if not args.crm_file.exists():
        if not args.backups_dir.exists() and not args.safety_backups_dir.exists():
            ok = False
        else:
            ok = _restore_workbook(
                args.crm_file,
                backup_dirs,
                ["*.backup_*.xlsx", "CRM_backup_*.xlsx"],
                label="CRM",
            ) and ok

    if args.inventory_file is not None and not args.inventory_file.exists():
        print(f"ERROR: Inventory workbook missing: {args.inventory_file}")
        print("Fix: place the inventory workbook at that path or pass --inventory-file /path/to/file.xlsx")
        ok = False

    if args.crm_file.exists():
        _backup_workbook(args.crm_file, args.safety_backups_dir, label="CRM")

    if args.inventory_file is not None and args.inventory_file.exists():
        _backup_workbook(args.inventory_file, args.safety_backups_dir, label="Inventory")

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
