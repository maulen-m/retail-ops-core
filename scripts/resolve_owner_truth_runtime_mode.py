#!/usr/bin/env python3
"""Resolve fail-closed owner-truth runtime behavior for live vs replay execution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class RuntimeModeError(RuntimeError):
    """Raised when requested runtime mode cannot be satisfied safely."""


def resolve_owner_truth_runtime_mode(
    *,
    project_root: Path,
    as_of: str,
    mode: str,
    strict: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    runtime_root = root / "exports" / "validation" / "board_v8_runtime" / as_of
    summary_json = runtime_root / "daily_ops_summary.json"
    seed_json = runtime_root / "ops_selection_seed.json"

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in {"live", "replay"}:
        raise RuntimeModeError(f"unsupported runtime mode: {mode}")

    blocked_inputs: list[dict[str, str]] = []
    ok = True
    status = "PASS"
    error_code = None
    run_kaspi_daily_ops = normalized_mode == "live"
    reuse_existing_daily_ops_summary = normalized_mode == "replay" and summary_json.exists()
    use_ops_selection_seed = normalized_mode == "replay" and seed_json.exists()

    if normalized_mode == "replay" and not summary_json.exists():
        ok = False
        status = "FAIL"
        error_code = "REPLAY_DAILY_OPS_SUMMARY_MISSING"

    if normalized_mode == "live" and seed_json.exists():
        blocked_inputs.append(
            {
                "kind": "replay_only_seed",
                "path": str(seed_json),
                "action": "ignored_in_live_mode",
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(root),
        "as_of": as_of,
        "mode": normalized_mode,
        "status": status,
        "ok": ok,
        "error_code": error_code,
        "runtime_root": str(runtime_root),
        "daily_ops_summary_json": str(summary_json),
        "daily_ops_summary_exists": summary_json.exists(),
        "ops_selection_seed_json": str(seed_json),
        "ops_selection_seed_exists": seed_json.exists(),
        "run_kaspi_daily_ops": run_kaspi_daily_ops,
        "reuse_existing_daily_ops_summary": reuse_existing_daily_ops_summary,
        "use_ops_selection_seed": use_ops_selection_seed,
        "blocked_inputs": blocked_inputs,
    }
    if strict and not ok:
        raise RuntimeModeError(error_code or "RUNTIME_MODE_RESOLUTION_FAILED")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve owner-truth live vs replay runtime mode")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--mode", choices=["live", "replay"], required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = resolve_owner_truth_runtime_mode(
            project_root=args.project_root,
            as_of=str(args.as_of),
            mode=str(args.mode),
            strict=bool(args.strict),
        )
    except RuntimeModeError as exc:
        print("status=FAIL")
        print("error_code=RUNTIME_MODE_RESOLUTION_FAILED")
        print(f"message={exc}")
        return 1

    output_json = args.output_json
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"runtime_mode_report={output_json}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
