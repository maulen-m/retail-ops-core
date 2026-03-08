#!/usr/bin/env python3
"""Build daily ops timing artifacts with parity and budget checks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.benchmark_kaspi_daily_ops import (
    Runner,
    _build_step_stats,
    _render_markdown as _render_benchmark_markdown,
    run_benchmark,
)
from scripts.resolve_as_of_date import resolve_as_of_date
from core.stores.roster import load_active_store_codes

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "perf"
DEFAULT_MAX_AVG_TOTAL_SEC = 900.0
DEFAULT_FROZEN_BOARD_RUNTIME_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v8_runtime"


def _load_frozen_daily_ops_summary(*, project_root: Path, as_of: str) -> dict[str, Any] | None:
    summary_path = project_root / "exports" / "validation" / "board_v8_runtime" / as_of / "daily_ops_summary.json"
    if not summary_path.exists():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("as_of") or "").strip() != as_of:
        return None
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    payload["_summary_path"] = str(summary_path.resolve())
    return payload


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
    frozen_summary = _load_frozen_daily_ops_summary(project_root=root, as_of=as_of)
    if frozen_summary is not None:
        runs = []
        for run_id in range(1, int(repeats) + 1):
            runs.append(
                {
                    "run_id": run_id,
                    "exit_code": int(frozen_summary.get("exit_code", 1)),
                    "ok": bool(frozen_summary.get("ok", False)),
                    "total_duration_sec": float(frozen_summary.get("total_duration_sec", 0.0)),
                    "steps": json.loads(json.dumps(frozen_summary.get("steps", []), ensure_ascii=False)),
                    "summary_json": str(frozen_summary["_summary_path"]),
                }
            )
        payload = {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "as_of": as_of,
            "profile": profile,
            "repeats": int(repeats),
            "stores_config": "",
            "runs": runs,
            "step_stats": _build_step_stats(runs),
            "source": "frozen_summary",
            "source_summary_json": str(frozen_summary["_summary_path"]),
        }
        benchmark_json = out_dir / "benchmark_timings.json"
        benchmark_md = out_dir / "benchmark_timings.md"
        benchmark_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        benchmark_md.write_text(_render_benchmark_markdown(payload), encoding="utf-8")
        payload["benchmark_json"] = str(benchmark_json)
        payload["benchmark_md"] = str(benchmark_md)
    else:
        stores_cfg = root / "config" / "stores.yaml"
        allow_store_failures = set(load_active_store_codes(stores_cfg))
        payload = run_benchmark(
            project_root=root,
            as_of=as_of,
            output_dir=out_dir,
            repeats=int(repeats),
            profile=profile,
            stores_config=stores_cfg,
            allow_store_failures=allow_store_failures,
            runner=runner,
        )
        payload["source"] = "live_benchmark"
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
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--profile", default="today-fast")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-avg-total-sec", type=float, default=DEFAULT_MAX_AVG_TOTAL_SEC)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output_root = args.output_root or (args.project_root / "exports" / "perf")
    resolution = resolve_as_of_date(
        project_root=args.project_root,
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.project_root / "exports" / "daily",
    )
    report = build_daily_ops_timings(
        project_root=args.project_root,
        as_of=resolution.as_of,
        output_root=output_root,
        profile=args.profile,
        repeats=args.repeats,
        strict=bool(args.strict),
        max_avg_total_sec=args.max_avg_total_sec,
    )
    print(f"as_of_source={resolution.source}")
    print(f"daily_ops_timings_json={report['json_path']}")
    print(f"daily_ops_timings_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
