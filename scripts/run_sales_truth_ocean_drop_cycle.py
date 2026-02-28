#!/usr/bin/env python3
"""Run deterministic ocean-drop sales truth cycle (dry-run default)."""

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
    proc = subprocess.run(cmd, cwd=str(cwd), shell=True, text=True, capture_output=True)
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return int(proc.returncode), output


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales Truth Ocean Drop Cycle",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- project_root: `{report['project_root']}`",
        "",
        "| step | rc | status | duration_sec | summary |",
        "|---|---:|---|---:|---|",
    ]
    for row in report["steps"]:
        lines.append(
            f"| `{row['step']}` | {row['rc']} | {'PASS' if row['ok'] else 'FAIL'} | {row['duration_sec']} | {row['summary']} |"
        )
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def run_sales_truth_ocean_drop_cycle(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path,
    strict: bool,
    ocean_drop: Path | None,
    crm_archive_lookup: Path | None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    run = runner or _run_shell
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)

    quoted_as_of = shlex.quote(as_of)
    ocean_drop_part = f" --ocean-drop {shlex.quote(str(ocean_drop))}" if ocean_drop else ""
    crm_part = f" --crm-archive-lookup {shlex.quote(str(crm_archive_lookup))}" if crm_archive_lookup else ""

    checks = [
        {
            "step": "build_ocean_drop_snapshot",
            "cmd": (
                "python3 scripts/build_ocean_drop_reference_snapshot.py "
                f"--as-of {quoted_as_of} --include-as-of-day --strict"
                f"{ocean_drop_part}{crm_part}"
            ),
        },
        {
            "step": "validate_sales_truth_ocean_drop_parity",
            "cmd": (
                "python3 scripts/validate_sales_truth_ocean_drop_parity.py "
                f"--as-of {quoted_as_of} --strict --volatility-days 14"
                f"{ocean_drop_part}{crm_part}"
            ),
        },
        {
            "step": "build_sales_truth_drift_report",
            "cmd": (
                "python3 scripts/build_sales_truth_drift_report.py "
                f"--as-of {quoted_as_of} --lookback-days 14 --strict"
                f"{ocean_drop_part}{crm_part}"
            ),
        },
        {
            "step": "sync_dim_kaspi_article_map_from_ocean_drop",
            "cmd": (
                "python3 scripts/sync_dim_kaspi_article_map_from_ocean_drop.py "
                f"--as-of {quoted_as_of} --strict"
                f"{ocean_drop_part}"
            ),
        },
        {
            "step": "sync_order_size_overrides_from_ocean_drop",
            "cmd": (
                "python3 scripts/sync_order_size_overrides_from_ocean_drop.py "
                f"--as-of {quoted_as_of} --strict"
                f"{ocean_drop_part}"
            ),
        },
        {
            "step": "rebuild_sales_fact_v2_from_kaspi_entries",
            "cmd": (
                "python3 scripts/rebuild_sales_fact_v2_from_kaspi_entries.py "
                f"--as-of {quoted_as_of} --strict"
            ),
        },
    ]

    steps = []
    errors = []
    for item in checks:
        started = time.perf_counter()
        rc, output = run(item["cmd"], root)
        duration = round(time.perf_counter() - started, 3)
        ok = int(rc) == 0
        summary = output.splitlines()[-1] if output else ""
        steps.append(
            {
                "step": item["step"],
                "cmd": item["cmd"],
                "rc": int(rc),
                "ok": ok,
                "duration_sec": duration,
                "summary": summary,
                "output": output,
            }
        )
        if not ok:
            errors.append(f"{item['step']} failed rc={rc}")
            break

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "project_root": str(root),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "errors": errors,
        "steps": steps,
    }

    json_path = out_dir / "sales_truth_ocean_drop_cycle_manifest.json"
    md_path = out_dir / "sales_truth_ocean_drop_cycle_manifest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    report["exit_code"] = 0 if (report["ok"] or not strict) else 1
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic ocean-drop sales truth cycle")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "exports" / "validation" / "sales_ocean_drop_cycle",
    )
    parser.add_argument("--ocean-drop", type=Path, default=None)
    parser.add_argument("--crm-archive-lookup", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_sales_truth_ocean_drop_cycle(
        project_root=args.project_root,
        as_of=str(args.as_of),
        output_root=args.output_root,
        strict=bool(args.strict),
        ocean_drop=args.ocean_drop,
        crm_archive_lookup=args.crm_archive_lookup,
    )
    print(f"sales_truth_ocean_drop_cycle_json={report['json_path']}")
    print(f"sales_truth_ocean_drop_cycle_md={report['md_path']}")
    print(f"status={report['status']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
