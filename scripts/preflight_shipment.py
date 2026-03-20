#!/usr/bin/env python3
"""Hard preflight for shipment workflow.

Fail-closed gate that blocks shipment operations unless critical control-plane
checks are green.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Callable

Runner = Callable[[str], tuple[int, str]]


def _default_runner(cmd: str, *, project_root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(project_root),
        shell=True,
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return int(proc.returncode), output.strip()


def _resolve_workbook_anchor(project_root: Path) -> Path | None:
    env_path = os.environ.get("AB_CRM_WORKBOOK_PATH")
    if env_path:
        path = Path(env_path).expanduser()
        return path if path.exists() else None
    anchor = project_root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    if anchor.exists():
        return anchor
    return None


def run_preflight_shipment(
    *,
    project_root: Path,
    as_of: str | None = None,
    runner: Runner | None = None,
) -> dict:
    root = Path(project_root).resolve()
    run = runner or (lambda cmd: _default_runner(cmd, project_root=root))
    workbook_anchor = _resolve_workbook_anchor(root)
    workbook_env_prefix = ""
    if workbook_anchor is not None:
        workbook_env_prefix = (
            f"AB_CRM_WORKBOOK_PATH={shlex.quote(str(workbook_anchor))} "
        )
    validate_params_cmd = workbook_env_prefix + "python3 scripts/validate_params.py --strict"
    if as_of:
        validate_params_cmd += f" --as-of {shlex.quote(as_of)}"

    checks = [
        (
            "anchor_health",
            f"python3 scripts/check_anchor_health.py --project-root {shlex.quote(str(root))}",
        ),
        (
            "scheduler_validate_only",
            "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
        ),
        (
            "validate_params_strict",
            validate_params_cmd,
        ),
        (
            "validate_single_truth_system",
            "python3 scripts/validate_single_truth_system.py",
        ),
        (
            "ops_status",
            f"python3 scripts/ops_status.py --project-root {shlex.quote(str(root))}",
        ),
    ]

    rows: list[dict] = []
    failed = False
    for step, cmd in checks:
        rc, output = run(cmd)
        rows.append(
            {
                "step": step,
                "cmd": cmd,
                "rc": int(rc),
                "ok": rc == 0,
                "summary": output.splitlines()[-1] if output else "",
            }
        )
        if rc != 0:
            failed = True

    return {
        "project_root": str(root),
        "ok": not failed,
        "exit_code": 1 if failed else 0,
        "checks": rows,
    }


def _render_human(report: dict) -> str:
    lines = [
        "Shipment Preflight",
        f"Project root: {report['project_root']}",
        f"Status: {'PASS' if report['ok'] else 'FAIL'}",
        "",
        "Checks:",
    ]
    for row in report["checks"]:
        status = "OK" if row["ok"] else "FAIL"
        summary = row.get("summary") or ""
        lines.append(f"- {row['step']}: {status} (rc={row['rc']}) {summary}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed shipment preflight")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root path",
    )
    parser.add_argument("--as-of", default=None, help="Optional as-of date for strict validation")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path")
    args = parser.parse_args()

    report = run_preflight_shipment(project_root=args.project_root, as_of=args.as_of)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    text = payload if args.json else _render_human(report)
    print(text)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")

    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
