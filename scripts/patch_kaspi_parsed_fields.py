#!/usr/bin/env python3
"""Patch parsed Kaspi identity fields in CRM workbook (dry-run by default)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.patch_crm_identity_columns import patch_workbook

DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_REPORT = Path("logs/kaspi_parsed_fields_patch_report.csv")
DEFAULT_BACKUP_DIR = Path("excel_ui/backups")
APPLY_ENV_GATE = "ENABLE_KASPI_PARSING_PATCH_WRITE"


def run_patch(
    *,
    workbook: Path,
    sheet_name: str,
    report: Path,
    backup_dir: Path,
    only_line61: bool,
    apply: bool,
) -> dict[str, Any]:
    """Run patch in DRY-RUN (default) or gated APPLY mode."""
    if apply and os.environ.get(APPLY_ENV_GATE) != "1":
        raise RuntimeError(f"{APPLY_ENV_GATE}=1 is required for --apply")

    stats = patch_workbook(
        workbook=Path(workbook),
        sheet=sheet_name,
        apply=bool(apply),
        report=Path(report),
        backup_dir=Path(backup_dir),
        only_line61=bool(only_line61),
    )
    if apply and not str(stats.get("backup_path", "")).strip():
        raise RuntimeError("apply mode requires backup_path for rollback")
    return {
        "mode": "APPLY" if apply else "DRY_RUN",
        "rows_scanned": int(stats.get("rows_scanned", 0)),
        "rows_updated": int(stats.get("rows_updated", 0)),
        "backup_path": str(stats.get("backup_path", "")),
        "report": str(report),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Patch Kaspi parsed identity fields (dry-run default; apply is env-gated)."
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--only-line61", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    stats = run_patch(
        workbook=args.workbook,
        sheet_name=args.sheet,
        report=args.report,
        backup_dir=args.backup_dir,
        only_line61=bool(args.only_line61),
        apply=bool(args.apply),
    )
    print(f"Kaspi parsed fields patch ({stats['mode']})")
    print(f"  rows_scanned: {stats['rows_scanned']}")
    print(f"  rows_updated: {stats['rows_updated']}")
    if stats["backup_path"]:
        print(f"  backup: {stats['backup_path']}")
    print(f"  report: {stats['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
