#!/usr/bin/env python3
"""Fail-closed, layered system diagnostics for daily operations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
Runner = Callable[[str, Path], tuple[int, str]]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_as_of_date import resolve_as_of_date


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


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# System Doctor Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- project_root: `{report['project_root']}`",
        f"- entry_point: `{report['entry_point']}`",
        f"- status: `{report['status']}`",
        f"- blocked_layer: `{report.get('blocked_layer') or 'none'}`",
        "",
        "## Layers",
        "",
        "| layer | status | checks_run | checks_failed |",
        "|---|---:|---:|---:|",
    ]
    for layer in report["layers"]:
        status = "GREEN" if layer["ok"] else "RED"
        lines.append(
            f"| `{layer['layer']}` | {status} | {layer['checks_run']} | {layer['checks_failed']} |"
        )

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| layer | check | rc | status | duration_sec | summary |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for check in report["checks"]:
        status = "OK" if check["ok"] else "FAIL"
        lines.append(
            f"| `{check['layer']}` | `{check['check']}` | {check['rc']} | {status} | "
            f"{check['duration_sec']} | {check['summary']} |"
        )
    return "\n".join(lines) + "\n"


def _doctor_checks(*, root: Path, as_of: str) -> list[dict[str, str]]:
    quoted_root = shlex.quote(str(root))
    quoted_as_of = shlex.quote(as_of)
    report_path = shlex.quote(str(root / "exports" / "daily" / as_of / "daily_ops_report.json"))
    exceptions_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions.json"))
    triage_json_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.json"))
    triage_md_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.md"))

    return [
        {
            "layer": "runtime",
            "check": "scheduler_validate_only",
            "cmd": "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
        },
        {
            "layer": "runtime",
            "check": "anchor_health",
            "cmd": f"python3 scripts/check_anchor_health.py --project-root {quoted_root} --as-of {quoted_as_of}",
        },
        {
            "layer": "runtime",
            "check": "ops_status",
            "cmd": f"python3 scripts/ops_status.py --project-root {quoted_root}",
        },
        {
            "layer": "truth",
            "check": "validate_params_strict",
            "cmd": f"python3 scripts/validate_params.py --strict --as-of {quoted_as_of}",
        },
        {
            "layer": "truth",
            "check": "validate_single_truth_system",
            "cmd": "python3 scripts/validate_single_truth_system.py",
        },
        {
            "layer": "truth",
            "check": "validate_schema",
            "cmd": "python3 scripts/validate_schema.py --json",
        },
        {
            "layer": "truth",
            "check": "validate_dashboard_plan_real_contract",
            "cmd": "python3 scripts/validate_dashboard_plan_real_contract.py --strict",
        },
        {
            "layer": "truth",
            "check": "validate_daily_ops_report",
            "cmd": f"python3 scripts/validate_daily_ops_report.py --strict --path {report_path}",
        },
        {
            "layer": "domain",
            "check": "build_domain_scorecards",
            "cmd": (
                "python3 scripts/build_domain_scorecards.py "
                f"--strict --as-of {quoted_as_of} "
                f"--project-root {quoted_root} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "domain",
            "check": "validate_cashfloor",
            "cmd": (
                "python3 scripts/validate_cashfloor.py "
                f"--strict --as-of {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "domain",
            "check": "translate_transfer_ledger_to_cashflow",
            "cmd": (
                "python3 scripts/translate_transfer_ledger_to_cashflow.py "
                f"--strict --as-of {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "execution",
            "check": "build_daily_ops_timings",
            "cmd": (
                "python3 scripts/build_daily_ops_timings.py "
                f"--strict --as-of {quoted_as_of} "
                f"--project-root {quoted_root} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'perf'))}"
            ),
        },
        {
            "layer": "execution",
            "check": "daily_ops_timing_artifact",
            "cmd": f"python3 scripts/validate_daily_ops_timing_artifact.py exports/perf/{as_of}/daily_ops_timings.json --strict",
        },
        {
            "layer": "governance",
            "check": "validate_exceptions_schema",
            "cmd": f"python3 scripts/validate_exceptions_schema.py {exceptions_path} --strict",
        },
        {
            "layer": "governance",
            "check": "validate_as_of_consistency",
            "cmd": (
                "python3 scripts/validate_as_of_consistency.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'diagnostics'))}"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_vs_waybill_parity",
            "cmd": (
                "python3 scripts/validate_sales_vs_waybill_parity.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_truth_external_reference",
            "cmd": (
                "python3 scripts/validate_sales_truth_external_reference.py "
                f"--project-root {quoted_root} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                "--strict-if-configured"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_truth_ocean_drop_parity",
            "cmd": (
                "python3 scripts/validate_sales_truth_ocean_drop_parity.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_ocean_drop_parity'))} "
                "--volatility-days 14 "
                "--strict-if-configured --strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_engine_self_sufficient",
            "cmd": (
                "python3 scripts/validate_sales_engine_self_sufficient.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_engine_self_sufficient'))} "
                "--strict-if-configured --strict"
            ),
        },
        {
            "layer": "governance",
            "check": "build_sales_truth_drift_report",
            "cmd": (
                "python3 scripts/build_sales_truth_drift_report.py "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                f"--parity-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_ocean_drop_parity'))} "
                "--lookback-days 14 "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "triage_exceptions",
            "cmd": (
                "python3 scripts/triage_exceptions.py "
                f"--exceptions {exceptions_path} "
                "--playbook docs/ops/EXCEPTION_PLAYBOOK.md "
                "--allowlist config/exceptions_allowlist.json "
                f"--output-json {triage_json_path} "
                f"--output-md {triage_md_path} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "lint_docs",
            "cmd": "bash scripts/lint_docs.sh",
        },
        {
            "layer": "governance",
            "check": "lint_docs_active_scope",
            "cmd": f"python3 scripts/lint_docs_active_scope.py --strict --project-root {quoted_root}",
        },
    ]


def run_system_doctor(
    *,
    project_root: Path,
    as_of: str,
    output_dir: Path,
    strict: bool,
    entry_point: str = "all",
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    run = runner or _run_shell
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    checks = _doctor_checks(root=root, as_of=as_of)
    layer_order = ["runtime", "truth", "domain", "execution", "governance"]

    check_rows: list[dict[str, Any]] = []
    blocked_layer: str | None = None
    overall_ok = True

    for layer in layer_order:
        layer_checks = [row for row in checks if row["layer"] == layer]
        for row in layer_checks:
            started = time.perf_counter()
            rc, out = run(row["cmd"], root)
            duration = round(time.perf_counter() - started, 3)
            summary = out.splitlines()[-1] if out else ""
            ok = rc == 0
            check_rows.append(
                {
                    "layer": layer,
                    "check": row["check"],
                    "cmd": row["cmd"],
                    "rc": int(rc),
                    "ok": bool(ok),
                    "duration_sec": duration,
                    "summary": summary,
                    "output": out,
                }
            )
            if not ok:
                overall_ok = False
                blocked_layer = layer
                break
        if not overall_ok:
            break

    layer_rows: list[dict[str, Any]] = []
    for layer in layer_order:
        rows = [row for row in check_rows if row["layer"] == layer]
        failed = [row for row in rows if not row["ok"]]
        layer_rows.append(
            {
                "layer": layer,
                "ok": len(failed) == 0 and len(rows) > 0,
                "checks_run": len(rows),
                "checks_failed": len(failed),
            }
        )

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report = {
        "generated_at": generated_at,
        "as_of": as_of,
        "project_root": str(root),
        "entry_point": entry_point,
        "ok": overall_ok,
        "status": "GREEN" if overall_ok else "RED",
        "blocked_layer": blocked_layer,
        "exit_code": 0 if overall_ok else 1,
        "layers": layer_rows,
        "checks": check_rows,
    }

    checks_path = output / "system_health_checks.json"
    json_path = output / "system_health.json"
    md_path = output / "system_health.md"
    checks_path.write_text(json.dumps(check_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    report["checks_path"] = str(checks_path)
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    if strict and not overall_ok:
        report["exit_code"] = 1
    elif not strict:
        report["exit_code"] = 0
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fail-closed layered diagnostics (System Doctor)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--entry-point",
        choices=["all", "po", "cashflow", "inventory", "api", "docs"],
        default="all",
    )
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    resolution = resolve_as_of_date(
        project_root=args.project_root.resolve(),
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.project_root.resolve() / "exports" / "daily",
    )
    as_of = resolution.as_of
    output_dir = args.output_dir or (args.project_root / "exports" / "diagnostics" / as_of)
    report = run_system_doctor(
        project_root=args.project_root,
        as_of=as_of,
        output_dir=output_dir,
        strict=bool(args.strict),
        entry_point=args.entry_point,
    )

    print(f"system_health_json={report['json_path']}")
    print(f"system_health_md={report['md_path']}")
    print(f"system_health_checks={report['checks_path']}")
    print(f"as_of_source={resolution.source}")
    print(f"status={report['status']}")
    if report["blocked_layer"]:
        print(f"blocked_layer={report['blocked_layer']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
