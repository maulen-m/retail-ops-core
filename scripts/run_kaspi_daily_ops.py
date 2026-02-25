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
import time
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.stores.roster import load_active_store_codes

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v8_runtime"
DEFAULT_CACHE_ROOT = PROJECT_ROOT / "runtime_cache" / "daily_ops"
Runner = Callable[[str, Path], tuple[int, str]]

PROFILE_CONFIG = {
    "today-fast": {
        "since_days": 1,
        "include_overdue": False,
    },
    "catch-up": {
        "since_days": 3,
        "include_overdue": True,
    },
}


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
    duration_sec: float,
    allow_failure: bool = False,
    from_checkpoint: bool = False,
    from_cache: bool = False,
) -> bool:
    ok = rc == 0 or (allow_failure and rc != 0)
    summary = output.splitlines()[-1] if output else ""
    steps.append(
        {
            "step": step,
            "cmd": cmd,
            "rc": int(rc),
            "ok": bool(ok),
            "duration_sec": float(duration_sec),
            "allow_failure": bool(allow_failure),
            "from_checkpoint": bool(from_checkpoint),
            "from_cache": bool(from_cache),
            "summary": summary,
        }
    )
    return ok


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Daily Ops Orchestrator Summary",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- profile: `{report['profile']}`",
        f"- dry_run: `{report['dry_run']}`",
        f"- status: `{'PASS' if report['ok'] else 'FAIL'}`",
        f"- total_duration_sec: `{report['total_duration_sec']}`",
        f"- red_stores: `{','.join(report.get('red_stores', []))}`",
        "",
        "## Steps",
    ]
    for row in report["steps"]:
        status = "OK" if row["ok"] else "FAIL"
        allow = " (allowed)" if row.get("allow_failure") and row["rc"] != 0 else ""
        lines.append(
            f"- `{row['step']}`: {status}{allow} rc={row['rc']} "
            f"duration={row.get('duration_sec', 0.0)}s | {row['summary']}"
        )
    return "\n".join(lines) + "\n"


def run_kaspi_daily_ops(
    *,
    project_root: Path,
    as_of: str,
    output_root: Path,
    allow_store_failures: set[str],
    profile: str = "catch-up",
    stores_config: Path | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    enable_cache: bool = False,
    cache_dir: Path | None = None,
    runner: Runner | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    run = runner or _run_shell
    if profile not in PROFILE_CONFIG:
        raise RuntimeError(f"unknown daily ops profile: {profile}")
    profile_cfg = PROFILE_CONFIG[profile]
    stores_cfg_path = Path(stores_config) if stores_config else (root / "config" / "stores.yaml")
    stores = load_active_store_codes(stores_cfg_path)
    allowed = {store.upper() for store in allow_store_failures}
    checkpoint = Path(checkpoint_path) if checkpoint_path else (output_root / as_of / "daily_ops_checkpoint.json")
    cache_root = Path(cache_dir) if cache_dir else DEFAULT_CACHE_ROOT

    checkpoint_rows: dict[str, dict[str, Any]] = {}
    if resume and checkpoint.exists():
        checkpoint_payload = _load_json(checkpoint)
        if checkpoint_payload.get("as_of") != as_of:
            raise RuntimeError("checkpoint as_of mismatch")
        if checkpoint_payload.get("profile") != profile:
            raise RuntimeError("checkpoint profile mismatch")
        if checkpoint_payload.get("stores_config") != str(stores_cfg_path):
            raise RuntimeError("checkpoint stores_config mismatch")
        for row in checkpoint_payload.get("steps", []):
            if isinstance(row, dict) and row.get("ok") is True and row.get("step"):
                checkpoint_rows[str(row["step"])] = row

    steps: list[dict[str, Any]] = []
    store_results: dict[str, dict[str, Any]] = {}
    overall_ok = True
    started = time.perf_counter()

    def _persist_checkpoint() -> None:
        payload = {
            "as_of": as_of,
            "profile": profile,
            "stores_config": str(stores_cfg_path),
            "steps": [
                checkpoint_rows[name]
                for name in sorted(checkpoint_rows.keys())
            ],
        }
        _write_json(checkpoint, payload)

    def _record_step(
        *,
        step: str,
        cmd: str,
        allow_failure: bool = False,
        cache_key: str | None = None,
    ) -> bool:
        if step in checkpoint_rows:
            prev = checkpoint_rows[step]
            return _append_step(
                steps=steps,
                step=step,
                cmd=cmd,
                rc=int(prev.get("rc", 0)),
                output=str(prev.get("summary", "")),
                duration_sec=0.0,
                allow_failure=allow_failure,
                from_checkpoint=True,
            )

        cache_path = None
        if enable_cache and cache_key:
            safe_step = step.replace("/", "_").replace(" ", "_")
            cache_path = cache_root / as_of / profile / f"{safe_step}.json"
            if cache_path.exists():
                cached_payload = _load_json(cache_path)
                if str(cached_payload.get("cmd", "")) == cmd:
                    return _append_step(
                        steps=steps,
                        step=step,
                        cmd=cmd,
                        rc=int(cached_payload.get("rc", 1)),
                        output=str(cached_payload.get("output", "")),
                        duration_sec=0.0,
                        allow_failure=allow_failure,
                        from_cache=True,
                    )

        step_started = time.perf_counter()
        rc, output = run(cmd, root)
        duration = round(time.perf_counter() - step_started, 3)
        ok = _append_step(
            steps=steps,
            step=step,
            cmd=cmd,
            rc=rc,
            output=output,
            duration_sec=duration,
            allow_failure=allow_failure,
        )

        checkpoint_rows[step] = {
            "step": step,
            "cmd": cmd,
            "rc": int(rc),
            "ok": bool(ok),
            "summary": output.splitlines()[-1] if output else "",
            "duration_sec": float(duration),
            "allow_failure": bool(allow_failure),
        }
        _persist_checkpoint()

        if enable_cache and cache_path is not None:
            _write_json(
                cache_path,
                {
                    "step": step,
                    "cmd": cmd,
                    "rc": int(rc),
                    "output": output,
                    "as_of": as_of,
                    "profile": profile,
                },
            )
        return ok

    static_checks = [
        (
            "validate_schema",
            "python3 scripts/validate_schema.py",
        ),
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
        if not _record_step(step=step, cmd=cmd):
            overall_ok = False

    for store in stores:
        include_overdue_flag = " --include-overdue" if profile_cfg["include_overdue"] else ""
        cmd = (
            "python3 scripts/report_waybill_status.py "
            f"--date {shlex.quote(as_of)} --since-days {profile_cfg['since_days']} "
            f"--store {shlex.quote(store)}{include_overdue_flag} --strict-stopline"
        )
        allow_failure = store in allowed
        step_name = f"waybill_status_{store}"
        if not _record_step(
            step=step_name,
            cmd=cmd,
            allow_failure=allow_failure,
            cache_key=step_name,
        ):
            overall_ok = False
        current = steps[-1]
        store_results[store] = {
            "ok": bool(current["ok"]),
            "rc": int(current["rc"]),
            "allow_failure": bool(allow_failure),
            "from_checkpoint": bool(current.get("from_checkpoint", False)),
            "from_cache": bool(current.get("from_cache", False)),
            "summary": str(current.get("summary", "")),
        }

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
        if not _record_step(step=step, cmd=cmd):
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
        "profile": profile,
        "stores_config": str(stores_cfg_path),
        "stores": stores,
        "store_results": store_results,
        "red_stores": sorted([store for store, meta in store_results.items() if not bool(meta.get("ok", False))]),
        "allow_store_failures": sorted(allowed),
        "checkpoint_path": str(checkpoint),
        "resume": bool(resume),
        "cache_enabled": bool(enable_cache),
        "cache_dir": str(cache_root),
        "ok": bool(overall_ok),
        "exit_code": 0 if overall_ok else 1,
        "total_duration_sec": round(time.perf_counter() - started, 3),
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
        "--profile",
        choices=sorted(PROFILE_CONFIG.keys()),
        default="catch-up",
        help="today-fast = strict current-day; catch-up = include-overdue window.",
    )
    parser.add_argument(
        "--stores-config",
        type=Path,
        default=None,
        help="Optional override for store roster YAML path.",
    )
    parser.add_argument(
        "--checkpoint-path",
        type=Path,
        default=None,
        help="Optional checkpoint JSON path for resume support.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpointed successful steps.",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable opt-in cache for per-store waybill status steps.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help="Cache root for waybill status results when --cache is set.",
    )
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
        profile=args.profile,
        stores_config=args.stores_config,
        checkpoint_path=args.checkpoint_path,
        resume=bool(args.resume),
        enable_cache=bool(args.cache),
        cache_dir=args.cache_dir,
        dry_run=True,
    )
    print(report["summary_md"])
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
