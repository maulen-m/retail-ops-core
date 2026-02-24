#!/usr/bin/env python3
"""Benchmark daily ops orchestration timings and emit deterministic artifacts."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_kaspi_daily_ops import (
    PROFILE_CONFIG,
    Runner,
    run_kaspi_daily_ops,
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "exports" / "validation" / "board_v7_runtime"


def _build_step_stats(runs: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, list[float]] = {}
    for run in runs:
        for step in run.get("steps", []):
            name = str(step.get("step", ""))
            duration = float(step.get("duration_sec", 0.0))
            if not name:
                continue
            buckets.setdefault(name, []).append(duration)

    stats: dict[str, dict[str, float | int]] = {}
    for name, values in buckets.items():
        stats[name] = {
            "runs": len(values),
            "avg_duration_sec": round(sum(values) / len(values), 3),
            "min_duration_sec": round(min(values), 3),
            "max_duration_sec": round(max(values), 3),
        }
    return stats


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Daily Ops Benchmark",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- profile: `{report['profile']}`",
        f"- repeats: `{report['repeats']}`",
        "",
        "## Step Stats",
    ]
    for step, stats in sorted(report["step_stats"].items()):
        lines.append(
            f"- `{step}`: runs={stats['runs']} avg={stats['avg_duration_sec']}s "
            f"min={stats['min_duration_sec']}s max={stats['max_duration_sec']}s"
        )
    return "\n".join(lines) + "\n"


def run_benchmark(
    *,
    project_root: Path,
    as_of: str,
    output_dir: Path,
    repeats: int,
    profile: str,
    stores_config: Path | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    for run_id in range(1, repeats + 1):
        report = run_kaspi_daily_ops(
            project_root=root,
            as_of=as_of,
            output_root=out / "orchestrator_runs",
            allow_store_failures=set(),
            profile=profile,
            stores_config=stores_config,
            runner=runner,
            dry_run=True,
        )
        runs.append(
            {
                "run_id": run_id,
                "exit_code": int(report.get("exit_code", 1)),
                "ok": bool(report.get("ok", False)),
                "total_duration_sec": float(report.get("total_duration_sec", 0.0)),
                "steps": report.get("steps", []),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "profile": profile,
        "repeats": repeats,
        "stores_config": str(stores_config) if stores_config else "",
        "runs": runs,
        "step_stats": _build_step_stats(runs),
    }
    json_path = out / "benchmark_timings.json"
    md_path = out / "benchmark_timings.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    payload["benchmark_json"] = str(json_path)
    payload["benchmark_md"] = str(md_path)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Kaspi daily ops stage timings")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--profile", choices=sorted(PROFILE_CONFIG.keys()), default="catch-up")
    parser.add_argument("--stores-config", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.repeats < 1:
        print("ERROR: --repeats must be >= 1")
        return 1

    report = run_benchmark(
        project_root=args.project_root,
        as_of=args.as_of,
        output_dir=args.output_dir,
        repeats=int(args.repeats),
        profile=args.profile,
        stores_config=args.stores_config,
    )
    print(f"benchmark_json: {report['benchmark_json']}")
    print(f"benchmark_md: {report['benchmark_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
