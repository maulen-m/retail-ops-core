#!/usr/bin/env python3
"""Run one strict H5 proving day command chain and emit deterministic summary artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import time
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# H5 Proving Day Summary",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- project_root: `{report['project_root']}`",
        "",
        "| step | rc | status | duration_sec | summary |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["steps"]:
        lines.append(
            f"| `{row['step']}` | {row['rc']} | {'PASS' if row['ok'] else 'FAIL'} | "
            f"{row['duration_sec']} | {row['summary']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def run_h5_proving_day(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path,
    strict: bool,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    run = runner or _run_shell
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)

    quoted_root = shlex.quote(str(root))
    quoted_as_of = shlex.quote(as_of)
    exceptions_json = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions.json"))
    triage_json = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.json"))
    triage_md = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.md"))
    diagnostics_out = shlex.quote(str(root / "exports" / "diagnostics"))

    checks = [
        {
            "step": "system_doctor",
            "cmd": (
                "python3 scripts/system_doctor.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-dir {shlex.quote(str(root / 'exports' / 'diagnostics' / as_of))}"
            ),
        },
        {
            "step": "validate_as_of_consistency",
            "cmd": (
                "python3 scripts/validate_as_of_consistency.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-root {diagnostics_out}"
            ),
        },
        {
            "step": "validate_business_insides_economics_ready",
            "cmd": (
                "python3 scripts/validate_business_insides_economics_ready.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'business_insides_economics'))} "
                "--strict"
            ),
        },
        {
            "step": "validate_shipped_truth_crm_waybill",
            "cmd": (
                "python3 scripts/validate_shipped_truth_crm_waybill.py "
                f"--project-root {quoted_root} "
                f"--since {quoted_as_of} "
                f"--until {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'shipped_truth_crm_waybill'))} "
                "--strict"
            ),
        },
        {
            "step": "validate_business_insides_ocean_drop_alignment",
            "cmd": (
                "python3 scripts/validate_business_insides_ocean_drop_alignment.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'business_insides_ocean_drop_alignment'))} "
                "--strict"
            ),
        },
        {
            "step": "validate_ops_selection_parity",
            "cmd": (
                "python3 scripts/validate_ops_selection_parity.py "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'ops_selection_parity'))} "
                "--strict"
            ),
        },
        {
            "step": "validate_scheduler_heartbeat",
            "cmd": (
                "python3 scripts/validate_scheduler_heartbeat.py "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                "--strict"
            ),
        },
        {
            "step": "validate_kaspi_archive_pack_integrity_ui",
            "cmd": (
                "python3 scripts/validate_kaspi_archive_pack_integrity.py "
                "--source ui "
                f"--as-of {quoted_as_of} "
                "--strict"
            ),
        },
        {
            "step": "run_sales_truth_ocean_drop_cycle",
            "cmd": (
                "python3 scripts/run_sales_truth_ocean_drop_cycle.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of}"
            ),
        },
        {
            "step": "triage_exceptions",
            "cmd": (
                "python3 scripts/triage_exceptions.py "
                f"--exceptions {exceptions_json} "
                "--playbook docs/ops/EXCEPTION_PLAYBOOK.md "
                "--allowlist config/exceptions_allowlist.json "
                f"--output-json {triage_json} "
                f"--output-md {triage_md} "
                "--strict"
            ),
        },
        {
            "step": "validate_h5_artifact_set",
            "cmd": (
                "python3 scripts/validate_h5_artifact_set.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of}"
            ),
        },
    ]

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in checks:
        started = time.perf_counter()
        rc, out = run(row["cmd"], root)
        duration = round(time.perf_counter() - started, 3)
        summary = out.splitlines()[-1] if out else ""
        ok = int(rc) == 0
        rows.append(
            {
                "step": row["step"],
                "cmd": row["cmd"],
                "rc": int(rc),
                "ok": bool(ok),
                "duration_sec": duration,
                "summary": summary,
                "output": out,
            }
        )
        if not ok:
            errors.append(f"{row['step']} failed rc={rc}")
            break

    overall_ok = len(errors) == 0
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "project_root": str(root),
        "status": "PASS" if overall_ok else "FAIL",
        "ok": bool(overall_ok),
        "errors": errors,
        "steps": rows,
        "exit_code": 0 if overall_ok else 1,
    }
    json_path = out_dir / "h5_proving_day_summary.json"
    md_path = out_dir / "h5_proving_day_summary.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    if strict and not overall_ok:
        report["exit_code"] = 1
    elif not strict:
        report["exit_code"] = 0
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strict H5 proving day chain in one command")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "exports" / "validation" / "h5_proving_day",
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_h5_proving_day(
        project_root=args.project_root,
        as_of=str(args.as_of),
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"h5_proving_day_json={report['json_path']}")
    print(f"h5_proving_day_md={report['md_path']}")
    print(f"status={report['status']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
