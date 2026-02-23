#!/usr/bin/env python3
"""Daily ops orchestrator (dry-run default, fail-closed)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.stores.roster import load_active_store_codes

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v6_runtime"
Runner = Callable[[str, Path], tuple[int, str]]


def _run_shell(cmd: str, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return int(proc.returncode), output


def _append_step(
    *,
    steps: list[dict[str, Any]],
    step: str,
    cmd: str,
    rc: int,
    output: str,
    allow_failure: bool = False,
) -> bool:
    ok = rc == 0 or (allow_failure and rc != 0)
    summary = output.splitlines()[-1] if output else ""
    steps.append(
        {
            "step": step,
            "cmd": cmd,
            "rc": int(rc),
            "ok": bool(ok),
            "allow_failure": bool(allow_failure),
            "summary": summary,
        }
    )
    return ok


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Daily Ops Orchestrator Summary",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- dry_run: `{report['dry_run']}`",
        f"- status: `{'PASS' if report['ok'] else 'FAIL'}`",
        "",
        "## Steps",
    ]
    for row in report["steps"]:
        status = "OK" if row["ok"] else "FAIL"
        allow = " (allowed)" if row.get("allow_failure") and row["rc"] != 0 else ""
        lines.append(f"- `{row['step']}`: {status}{allow} rc={row['rc']} | {row['summary']}")
    return "\n".join(lines) + "\n"


def run_kaspi_daily_ops(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path,
    allow_store_failures: set[str],
    runner: Runner | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    run = runner or _run_shell
    stores = load_active_store_codes(root / "config" / "stores.yaml")
    allowed = {store.upper() for store in allow_store_failures}

    steps: list[dict[str, Any]] = []
    overall_ok = True

    static_checks = [
        (
            "scheduler_validate_only",
            "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
        ),
        (
            "anchor_health",
            f"python3 scripts/check_anchor_health.py --project-root {shlex.quote(str(root))} --as-of {shlex.quote(as_of)}",
        ),
        (
            "ops_status",
            f"python3 scripts/ops_status.py --project-root {shlex.quote(str(root))}",
        ),
        (
            "shipment_preflight",
            f"python3 scripts/preflight_shipment.py --project-root {shlex.quote(str(root))}",
        ),
    ]

    for step, cmd in static_checks:
        rc, output = run(cmd, root)
        if not _append_step(steps=steps, step=step, cmd=cmd, rc=rc, output=output):
            overall_ok = False

    for store in stores:
        cmd = (
            "python3 scripts/report_waybill_status.py "
            f"--date {shlex.quote(as_of)} --since-days 3 --store {shlex.quote(store)} --strict-stopline"
        )
        rc, output = run(cmd, root)
        allow_failure = store in allowed
        if not _append_step(
            steps=steps,
            step=f"waybill_status_{store}",
            cmd=cmd,
            rc=rc,
            output=output,
            allow_failure=allow_failure,
        ):
            overall_ok = False

    drift_commands = [
        (
            "build_ops_drift_pack",
            f"python3 scripts/build_ops_drift_pack.py --as-of {shlex.quote(as_of)}",
        ),
        (
            "validate_drift_pack_slo",
            f"python3 scripts/validate_drift_pack_slo.py --strict --as-of {shlex.quote(as_of)}",
        ),
    ]
    for step, cmd in drift_commands:
        rc, output = run(cmd, root)
        if not _append_step(steps=steps, step=step, cmd=cmd, rc=rc, output=output):
            overall_ok = False

    run_dir = output_root / as_of
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_json = run_dir / "daily_ops_summary.json"
    summary_md = run_dir / "daily_ops_summary.md"

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "project_root": str(root),
        "dry_run": bool(dry_run),
        "stores": stores,
        "allow_store_failures": sorted(allowed),
        "ok": bool(overall_ok),
        "exit_code": 0 if overall_ok else 1,
        "steps": steps,
        "summary_json": str(summary_json),
        "summary_md": str(summary_md),
    }

    summary_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed Kaspi daily ops orchestrator")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", type=str, default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--allow-store-failure",
        action="append",
        default=[],
        help="Allow listed store code(s) to fail waybill strict-stopline without failing full run.",
    )
    parser.add_argument("--apply", action="store_true", help="Reserved for future apply modes.")
    args = parser.parse_args()

    if args.apply and os.environ.get("ENABLE_DAILY_OPS_APPLY") != "1":
        print("ERROR: ENABLE_DAILY_OPS_APPLY=1 is required for --apply")
        return 1
    if args.apply:
        print("ERROR: --apply mode is not implemented for run_kaspi_daily_ops.py")
        return 1

    report = run_kaspi_daily_ops(
        project_root=args.project_root,
        as_of=args.as_of,
        output_root=args.output_root,
        allow_store_failures={str(s).upper() for s in args.allow_store_failure},
        dry_run=True,
    )
    print(report["summary_md"])
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
