#!/usr/bin/env python3
"""Run daily Kaspi ads trust loop: healthcheck, coverage report, and daily brief."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.kaspi_ads_hourly_pipeline import DEFAULT_STORES_CONFIG
    from scripts.kaspi_ads_paths import (
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )
except ModuleNotFoundError:
    from kaspi_ads_hourly_pipeline import DEFAULT_STORES_CONFIG  # type: ignore
    from kaspi_ads_paths import (  # type: ignore
        DEFAULT_WORKTREE_ADS_DB_PATH,
        assert_ads_db_path_safe,
        resolve_ads_db_path,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEALTHCHECK_SCRIPT = PROJECT_ROOT / "scripts" / "kaspi_ads_healthcheck.py"
COVERAGE_SCRIPT = PROJECT_ROOT / "scripts" / "kaspi_ads_campaign_coverage_report.py"
DAILY_BRIEF_SCRIPT = PROJECT_ROOT / "scripts" / "kaspi_ads_elasticity.py"
DEFAULT_APP_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_TRUST_LOOP_DIR = PROJECT_ROOT / "reports" / "marketing" / "trust_loop"
DEFAULT_DAILY_BRIEF_DIR = PROJECT_ROOT / "reports" / "marketing" / "daily_brief"
DEFAULT_COVERAGE_OUT = DEFAULT_TRUST_LOOP_DIR / "kaspi_ads_campaign_coverage_latest.json"
DEFAULT_SUMMARY_OUT = DEFAULT_TRUST_LOOP_DIR / "kaspi_ads_daily_trust_loop_latest.json"

RunStepFn = Callable[[list[str]], tuple[int, str, str, dict[str, Any] | None]]


def _try_parse_json(stdout: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _run_step(cmd: list[str]) -> tuple[int, str, str, dict[str, Any] | None]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    parsed = _try_parse_json(proc.stdout)
    return proc.returncode, proc.stdout, proc.stderr, parsed


def _append_opt(cmd: list[str], flag: str, value: str | None) -> None:
    if value:
        cmd.extend([flag, value])


def run_daily_trust_loop(
    *,
    ads_db: Path,
    stores_config: Path,
    app_db: Path,
    coverage_out: Path,
    brief_out_dir: Path,
    summary_out: Path,
    since: str | None = None,
    until: str | None = None,
    campaign_ids: str | None = None,
    min_days: int = 3,
    default_margin_pct: float = 0.25,
    run_step_fn: RunStepFn = _run_step,
) -> dict[str, Any]:
    coverage_out.parent.mkdir(parents=True, exist_ok=True)
    brief_out_dir.mkdir(parents=True, exist_ok=True)
    summary_out.parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    failures: list[str] = []

    health_cmd = [
        sys.executable,
        str(HEALTHCHECK_SCRIPT),
        "--ads-db",
        str(ads_db),
        "--stores-config",
        str(stores_config),
        "--require-recon-rows",
    ]
    health_rc, health_out, health_err, health_json = run_step_fn(health_cmd)
    steps.append(
        {
            "name": "healthcheck",
            "command": health_cmd,
            "exit_code": int(health_rc),
            "summary": health_json,
            "stdout_tail": (health_out or "").strip().splitlines()[-20:],
            "stderr_tail": (health_err or "").strip().splitlines()[-20:],
        }
    )
    if health_rc != 0:
        failures.append("healthcheck")

    coverage_cmd = [
        sys.executable,
        str(COVERAGE_SCRIPT),
        "--ads-db",
        str(ads_db),
        "--stores-config",
        str(stores_config),
        "--out",
        str(coverage_out),
    ]
    coverage_rc, coverage_out_txt, coverage_err_txt, coverage_json = run_step_fn(coverage_cmd)
    steps.append(
        {
            "name": "coverage",
            "command": coverage_cmd,
            "exit_code": int(coverage_rc),
            "summary": coverage_json,
            "stdout_tail": (coverage_out_txt or "").strip().splitlines()[-20:],
            "stderr_tail": (coverage_err_txt or "").strip().splitlines()[-20:],
        }
    )
    if coverage_rc != 0:
        failures.append("coverage")

    brief_cmd = [
        sys.executable,
        str(DAILY_BRIEF_SCRIPT),
        "--ads-db",
        str(ads_db),
        "--app-db",
        str(app_db),
        "--out-dir",
        str(brief_out_dir),
        "--min-days",
        str(max(1, int(min_days))),
        "--default-margin-pct",
        str(float(default_margin_pct)),
    ]
    _append_opt(brief_cmd, "--since", since)
    _append_opt(brief_cmd, "--until", until)
    _append_opt(brief_cmd, "--campaign-ids", campaign_ids)

    brief_rc, brief_out_txt, brief_err_txt, brief_json = run_step_fn(brief_cmd)
    steps.append(
        {
            "name": "daily_brief",
            "command": brief_cmd,
            "exit_code": int(brief_rc),
            "summary": brief_json,
            "stdout_tail": (brief_out_txt or "").strip().splitlines()[-20:],
            "stderr_tail": (brief_err_txt or "").strip().splitlines()[-20:],
        }
    )
    if brief_rc != 0:
        failures.append("daily_brief")

    status = "ok" if not failures else "error"
    result = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "exit_code": 0 if status == "ok" else 1,
        "ads_db": str(ads_db),
        "stores_config": str(stores_config),
        "app_db": str(app_db),
        "coverage_out": str(coverage_out),
        "brief_out_dir": str(brief_out_dir),
        "summary_out": str(summary_out),
        "failures": failures,
        "steps": steps,
    }
    summary_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily Kaspi ads trust loop.")
    parser.add_argument("--ads-db", type=Path, default=None, help="Ads DB path (or set KASPI_MARKETING_DB_PATH)")
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--coverage-out", type=Path, default=DEFAULT_COVERAGE_OUT)
    parser.add_argument("--brief-out-dir", type=Path, default=DEFAULT_DAILY_BRIEF_DIR)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--since", default=None)
    parser.add_argument("--until", default=None)
    parser.add_argument("--campaign-ids", default=None, help="Comma-separated campaign IDs")
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--default-margin-pct", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ads_db_path = resolve_ads_db_path(ads_db_arg=args.ads_db, default_path=DEFAULT_WORKTREE_ADS_DB_PATH)
    assert_ads_db_path_safe(ads_db_path=ads_db_path)

    result = run_daily_trust_loop(
        ads_db=ads_db_path,
        stores_config=args.stores_config,
        app_db=args.app_db,
        coverage_out=args.coverage_out,
        brief_out_dir=args.brief_out_dir,
        summary_out=args.summary_out,
        since=args.since,
        until=args.until,
        campaign_ids=args.campaign_ids,
        min_days=args.min_days,
        default_margin_pct=args.default_margin_pct,
    )
    print(json.dumps(result, ensure_ascii=False))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
