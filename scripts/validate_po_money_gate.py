#!/usr/bin/env python3
"""Fail-closed validator for PO money-gate publication readiness."""

from __future__ import annotations

import argparse
from datetime import date
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_INBOUND_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"

CommandRunner = Callable[[list[str], Path], tuple[int, str, str]]


@dataclass
class GateCheck:
    name: str
    required: bool
    command: str
    ok: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""


def _resolve_inbound_workbook(project_root: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    env_raw = str(os.environ.get("AB_INBOUND_WORKBOOK_PATH", "")).strip()
    if env_raw:
        return Path(env_raw).expanduser()
    return (project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx").resolve()


def _default_runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def summarize_gate_checks(checks: list[GateCheck]) -> dict[str, object]:
    required_failed = [check.name for check in checks if check.required and not check.ok]
    optional_failed = [check.name for check in checks if (not check.required) and (not check.ok)]
    return {
        "ok": len(required_failed) == 0,
        "required_failed": required_failed,
        "optional_failed": optional_failed,
        "checks": [asdict(check) for check in checks],
    }


def run_po_money_gate(
    *,
    project_root: Path = PROJECT_ROOT,
    db_path: Path = DEFAULT_DB,
    inbound_workbook: Path | None = None,
    as_of: date | None = None,
    require_offer_linkage_strict: bool = False,
    fail_fast: bool = False,
    command_runner: CommandRunner = _default_runner,
) -> dict[str, object]:
    root = project_root.resolve()
    workbook_path = _resolve_inbound_workbook(root, explicit=inbound_workbook)
    checks: list[GateCheck] = []

    if not workbook_path.exists():
        checks.append(
            GateCheck(
                name="inbound_workbook_presence",
                required=True,
                command=f"exists {workbook_path}",
                ok=False,
                exit_code=1,
                stderr=f"inbound workbook not found: {workbook_path}",
            )
        )
        return {
            **summarize_gate_checks(checks),
            "project_root": str(root),
            "db_path": str(db_path),
            "inbound_workbook": str(workbook_path),
        }

    command_specs: list[tuple[str, bool, list[str]]] = [
        (
            "anchor_health",
            True,
            [
                sys.executable,
                str(root / "scripts" / "check_anchor_health.py"),
                "--project-root",
                str(root),
            ],
        ),
        (
            "inbound_sheet_consistency",
            True,
            [
                sys.executable,
                str(root / "scripts" / "validate_inbound_sheet_consistency.py"),
                "--xlsx",
                str(workbook_path),
                "--json",
            ],
        ),
        (
            "single_truth_system",
            True,
            [
                sys.executable,
                str(root / "scripts" / "validate_single_truth_system.py"),
                "--db",
                str(db_path),
                "--xlsx",
                str(workbook_path),
            ],
        ),
        (
            "cogs_integrity",
            True,
            (
                [
                sys.executable,
                str(root / "scripts" / "validate_cogs_integrity.py"),
                "--db",
                str(db_path),
                "--days",
                "30",
                "--max-unresolved-rows",
                "0",
                "--max-unresolved-skus",
                "0",
                ]
                + (["--as-of", as_of.isoformat()] if as_of is not None else [])
            ),
        ),
        (
            "single_truth_alignment",
            True,
            [
                sys.executable,
                str(root / "scripts" / "validate_single_truth_alignment.py"),
                "--db",
                str(db_path),
            ],
        ),
        (
            "offer_linkage",
            bool(require_offer_linkage_strict),
            [
                sys.executable,
                str(root / "scripts" / "validate_offer_linkage.py"),
                "--db",
                str(db_path),
            ],
        ),
    ]

    for name, required, cmd in command_specs:
        rc, stdout, stderr = command_runner(cmd, root)
        check = GateCheck(
            name=name,
            required=required,
            command=" ".join(cmd),
            ok=(rc == 0),
            exit_code=rc,
            stdout=(stdout or "").strip(),
            stderr=(stderr or "").strip(),
        )
        checks.append(check)
        if fail_fast and required and not check.ok:
            break

    report = summarize_gate_checks(checks)
    report["project_root"] = str(root)
    report["db_path"] = str(db_path)
    report["inbound_workbook"] = str(workbook_path)
    report["as_of"] = as_of.isoformat() if as_of is not None else None
    report["require_offer_linkage_strict"] = bool(require_offer_linkage_strict)
    return report


def _render_text(report: dict[str, object]) -> str:
    lines = [
        "PO money gate",
        f"ok={report['ok']}",
        f"required_failed={','.join(report['required_failed']) if report['required_failed'] else 'none'}",
        f"optional_failed={','.join(report['optional_failed']) if report['optional_failed'] else 'none'}",
        f"inbound_workbook={report['inbound_workbook']}",
    ]
    for check in report["checks"]:
        required = "required" if check["required"] else "optional"
        status = "OK" if check["ok"] else "FAIL"
        lines.append(
            f"- {check['name']}: {status} ({required}, rc={check['exit_code']})"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PO money-gate readiness")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--inbound-workbook", type=Path, default=None)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--require-offer-linkage-strict", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_po_money_gate(
        project_root=args.project_root,
        db_path=args.db,
        inbound_workbook=args.inbound_workbook,
        as_of=args.as_of,
        require_offer_linkage_strict=args.require_offer_linkage_strict,
        fail_fast=args.fail_fast,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
