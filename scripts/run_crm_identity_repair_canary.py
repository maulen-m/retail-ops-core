#!/usr/bin/env python3
"""Fail-closed canary wrapper for CRM identity repair patching."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.patch_kaspi_parsed_fields import run_patch

DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_REPORT = Path("logs/kaspi_parsed_fields_patch_report.csv")
DEFAULT_BACKUP_DIR = Path("excel_ui/backups")
DEFAULT_PROOF = Path("exports/validation/crm_identity_repair_canary/rollback_proof.md")


def _write_rollback_proof(path: Path, *, backup_path: str, report_path: Path, workbook: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CRM identity repair canary rollback proof",
        "",
        f"- generated_at: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}`",
        f"- backup_path: `{backup_path}`",
        f"- report: `{report_path.as_posix()}`",
        "",
        "## Rollback command",
        "```bash",
        f"cp {backup_path} {workbook.as_posix()}",
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_canary(
    *,
    workbook: Path,
    sheet_name: str,
    report: Path,
    backup_dir: Path,
    proof_path: Path,
    only_line61: bool,
    max_updates: int,
    apply: bool,
) -> dict[str, Any]:
    if max_updates < 0:
        raise RuntimeError("max_updates must be >= 0")

    dry_stats = run_patch(
        workbook=workbook,
        sheet_name=sheet_name,
        report=report,
        backup_dir=backup_dir,
        only_line61=only_line61,
        apply=False,
    )
    rows_updated = int(dry_stats.get("rows_updated", 0))
    if rows_updated > max_updates:
        raise RuntimeError(f"dry-run rows_updated exceeds max_updates: {rows_updated} > {max_updates}")

    if not apply:
        return {
            "mode": "DRY_RUN",
            "rows_scanned": int(dry_stats.get("rows_scanned", 0)),
            "rows_updated": rows_updated,
            "report": str(report),
            "proof_path": "",
        }

    apply_stats = run_patch(
        workbook=workbook,
        sheet_name=sheet_name,
        report=report,
        backup_dir=backup_dir,
        only_line61=only_line61,
        apply=True,
    )
    backup_path = str(apply_stats.get("backup_path", "")).strip()
    if not backup_path:
        raise RuntimeError("apply mode did not return backup_path")
    if not Path(backup_path).exists():
        raise RuntimeError(f"backup path does not exist: {backup_path}")

    _write_rollback_proof(
        proof_path,
        backup_path=backup_path,
        report_path=report,
        workbook=workbook,
    )

    return {
        "mode": "APPLY",
        "rows_scanned": int(apply_stats.get("rows_scanned", 0)),
        "rows_updated": int(apply_stats.get("rows_updated", 0)),
        "backup_path": backup_path,
        "report": str(report),
        "proof_path": str(proof_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CRM identity repair canary (dry-run default)")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--proof-path", type=Path, default=DEFAULT_PROOF)
    parser.add_argument("--only-line61", action="store_true")
    parser.add_argument("--max-updates", type=int, default=50)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = run_canary(
        workbook=args.workbook,
        sheet_name=args.sheet,
        report=args.report,
        backup_dir=args.backup_dir,
        proof_path=args.proof_path,
        only_line61=bool(args.only_line61),
        max_updates=int(args.max_updates),
        apply=bool(args.apply),
    )

    print(f"mode={result['mode']}")
    print(f"rows_scanned={result['rows_scanned']}")
    print(f"rows_updated={result['rows_updated']}")
    print(f"report={result['report']}")
    if result.get("backup_path"):
        print(f"backup_path={result['backup_path']}")
    if result.get("proof_path"):
        print(f"proof_path={result['proof_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
