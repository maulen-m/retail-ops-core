#!/usr/bin/env python3
"""Build daily ops timing artifacts with parity and budget checks."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_kaspi_daily_ops import Runner, run_benchmark

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "perf"
DEFAULT_MAX_AVG_TOTAL_SEC = 900.0


def evaluate_timing_budget(*, payload: dict[str, Any], max_avg_total_sec: float) -> dict[str, Any]:
    runs = payload.get("runs") or []
    errors: list[str] = []
    if not isinstance(runs, list) or not runs:
        errors.append("timing payload must include non-empty runs")
        return {
            "ok": False,
            "avg_total_duration_sec": 0.0,
            "max_avg_total_sec": float(max_avg_total_sec),
            "errors": errors,
        }

    totals = [float(run.get("total_duration_sec", 0.0)) for run in runs]
    avg_total = round(sum(totals) / len(totals), 3)
    if avg_total > float(max_avg_total_sec):
        errors.append(
            f"budget exceeded: avg_total_duration_sec={avg_total} > max_avg_total_sec={float(max_avg_total_sec)}"
        )
    return {
        "ok": not errors,
        "avg_total_duration_sec": avg_total,
        "max_avg_total_sec": float(max_avg_total_sec),
        "errors": errors,
    }


def evaluate_parity(*, payload: dict[str, Any]) -> dict[str, Any]:
    runs = payload.get("runs") or []
    if not isinstance(runs, list) or len(runs) <= 1:
        return {"ok": True, "errors": []}

    errors: list[str] = []
    baseline = {
        str(step.get("step")): {
            "rc": int(step.get("rc", 1)),
            "ok": bool(step.get("ok", False)),
        }
        for step in runs[0].get("steps", [])
    }
    for idx, run in enumerate(runs[1:], start=2):
        current = {
            str(step.get("step")): {
                "rc": int(step.get("rc", 1)),
                "ok": bool(step.get("ok", False)),
            }
            for step in run.get("steps", [])
        }
        if baseline != current:
            errors.append(f"run_{idx} rc/ok parity mismatch against run_1")
    return {"ok": not errors, "errors": errors}


def _render_md(payload: dict[str, Any], budget: dict[str, Any], parity: dict[str, Any]) -> str:
    lines = [
        "# Daily Ops Timings",
        "",
        f"- as_of: `{payload.get('as_of', '')}`",
        f"- profile: `{payload.get('profile', '')}`",
        f"- repeats: `{payload.get('repeats', 0)}`",
        f"- budget_ok: `{budget['ok']}`",
        f"- avg_total_duration_sec: `{budget['avg_total_duration_sec']}`",
        f"- max_avg_total_sec: `{budget['max_avg_total_sec']}`",
        f"- parity_ok: `{parity['ok']}`",
        "",
    ]
    if budget["errors"] or parity["errors"]:
        lines.append("## Errors")
        lines.append("")
        for err in budget["errors"] + parity["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend(
        [
            "## Step Stats",
            "",
            "| step | runs | avg_duration_sec | min_duration_sec | max_duration_sec |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for step, stats in sorted((payload.get("step_stats") or {}).items()):
        lines.append(
            f"| `{step}` | {stats.get('runs', 0)} | {stats.get('avg_duration_sec', 0)} | "
            f"{stats.get('min_duration_sec', 0)} | {stats.get('max_duration_sec', 0)} |"
        )
    return "\n".join(lines) + "\n"


def build_daily_ops_timings(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    profile: str = "today-fast",
    repeats: int = 2,
    strict: bool = False,
    max_avg_total_sec: float = DEFAULT_MAX_AVG_TOTAL_SEC,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = run_benchmark(
        project_root=root,
        as_of=as_of,
        output_dir=out_dir,
        repeats=int(repeats),
        profile=profile,
        runner=runner,
    )
    budget = evaluate_timing_budget(payload=payload, max_avg_total_sec=float(max_avg_total_sec))
    parity = evaluate_parity(payload=payload)
    run_failures = [run for run in payload.get("runs", []) if int(run.get("exit_code", 1)) != 0]

    ok = (not run_failures) and budget["ok"] and parity["ok"]
    json_payload = {
        **payload,
        "budget": budget,
        "parity": parity,
        "ok": ok,
    }
    json_path = out_dir / "daily_ops_timings.json"
    md_path = out_dir / "daily_ops_timings.md"
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload, budget, parity), encoding="utf-8")

    return {
        "ok": ok,
        "exit_code": 0 if (ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": json_payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build daily ops timing artifacts with budget/parity checks")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--profile", default="today-fast")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-avg-total-sec", type=float, default=DEFAULT_MAX_AVG_TOTAL_SEC)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_daily_ops_timings(
        project_root=args.project_root,
        as_of=args.as_of,
        output_root=args.output_root,
        profile=args.profile,
        repeats=args.repeats,
        strict=bool(args.strict),
        max_avg_total_sec=args.max_avg_total_sec,
    )
    print(f"daily_ops_timings_json={report['json_path']}")
    print(f"daily_ops_timings_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
