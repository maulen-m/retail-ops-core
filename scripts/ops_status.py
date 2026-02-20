#!/usr/bin/env python3
"""Deterministic ops status check for single-truth scheduler/runtime health."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_anchor_health import check_anchor_health


def run_scheduler_validate_only(
    *,
    project_root: Path = PROJECT_ROOT,
    installer_script: Path | None = None,
) -> tuple[int, str]:
    script = installer_script or (project_root / "scripts" / "install_single_truth_ops_scheduler.sh")
    if not script.exists():
        return 2, f"validate-only FAIL: missing installer script at {script}"
    completed = subprocess.run(
        ["bash", str(script), "--validate-only", "--project-dir", str(project_root)],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode != 0:
        return int(completed.returncode), (
            f"validate-only FAIL: rc={completed.returncode}; "
            f"details={output[:300]}"
        )
    return 0, "validate-only PASS"


def run_ops_status(
    *,
    project_root: Path = PROJECT_ROOT,
    run_validate_only: bool = True,
) -> tuple[int, str]:
    anchor_code, anchor_lines = check_anchor_health(project_root=project_root)
    validate_code = 0
    validate_summary = "validate-only SKIPPED"
    if run_validate_only:
        validate_code, validate_summary = run_scheduler_validate_only(project_root=project_root)

    if anchor_code == 0 and validate_code == 0:
        return 0, "OPS_STATUS PASS: anchor health PASS; validate-only PASS"

    errors: list[str] = []
    if anchor_code != 0:
        first_anchor_error = next(
            (line for line in anchor_lines if line.startswith("ERROR:")),
            "ERROR: anchor health failed",
        )
        errors.append(f"anchor health FAIL ({first_anchor_error})")
    if validate_code != 0:
        errors.append(validate_summary)
    return 1, "OPS_STATUS FAIL: " + " | ".join(errors)


def _print_lines(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check single-truth ops health deterministically")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help="Repository root path")
    parser.add_argument(
        "--skip-validate-only",
        action="store_true",
        help="Skip install script validate-only command",
    )
    args = parser.parse_args()

    anchor_code, anchor_lines = check_anchor_health(project_root=args.project_root)
    _print_lines(anchor_lines)

    validate_code = 0
    validate_summary = "validate-only SKIPPED"
    if not args.skip_validate_only:
        validate_code, validate_summary = run_scheduler_validate_only(project_root=args.project_root)
    print(validate_summary)

    code, summary = run_ops_status(
        project_root=args.project_root,
        run_validate_only=not args.skip_validate_only,
    )
    print(summary)
    if anchor_code != 0:
        return int(anchor_code)
    if validate_code != 0:
        return int(validate_code)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
