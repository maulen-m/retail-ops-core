#!/usr/bin/env python3
"""Validate structure of daily ops timing benchmark artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_timing_artifact(path: Path, strict: bool = False) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    errors: list[str] = []

    if not payload.get("as_of"):
        errors.append("missing required field: as_of")
    if not payload.get("profile"):
        errors.append("missing required field: profile")

    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        errors.append("runs must be a non-empty list")
    else:
        for i, run in enumerate(runs, start=1):
            if "total_duration_sec" not in run:
                errors.append(f"run[{i}] missing total_duration_sec")
            steps = run.get("steps")
            if not isinstance(steps, list) or not steps:
                errors.append(f"run[{i}] steps must be a non-empty list")
                continue
            for j, step in enumerate(steps, start=1):
                if "step" not in step:
                    errors.append(f"run[{i}].steps[{j}] missing step")
                if "duration_sec" not in step:
                    errors.append(f"run[{i}].steps[{j}] missing duration_sec")

    step_stats = payload.get("step_stats")
    if not isinstance(step_stats, dict):
        errors.append("step_stats must be an object")

    ok = not errors
    report = {
        "path": str(path),
        "ok": ok,
        "errors": errors,
    }
    if strict and not ok:
        raise RuntimeError("; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate daily ops timing artifact structure")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_timing_artifact(args.artifact, strict=bool(args.strict))
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("daily_ops_timing_artifact: OK" if report["ok"] else "daily_ops_timing_artifact: FAIL")
    if report["errors"]:
        for err in report["errors"]:
            print(f"- {err}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
