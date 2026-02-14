#!/usr/bin/env python3
"""
Run strict daily validation with workbook-anchor enforcement.

Fail closed when workbook path is not provided or missing.
Optionally emit lineage artifact.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAX_WORKBOOK_AGE_HOURS = 168.0
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.error_alerts import send_run_failure_alert


def emit_lineage_report(
    *,
    db_path: Path,
    workbook_path: Path,
    output_path: Path,
    strict_exit_code: int,
) -> None:
    from scripts.generate_lineage_report import generate_lineage_report

    generate_lineage_report(
        db_path=db_path,
        workbook_path=workbook_path,
        output_path=output_path,
        strict_exit_code=strict_exit_code,
    )


def _resolve_max_workbook_age_hours(value: float | None) -> float:
    if value is not None:
        return float(value)
    env_raw = os.environ.get("AB_CRM_WORKBOOK_MAX_AGE_HOURS", "").strip()
    if env_raw:
        try:
            return float(env_raw)
        except ValueError:
            return DEFAULT_MAX_WORKBOOK_AGE_HOURS
    return DEFAULT_MAX_WORKBOOK_AGE_HOURS


def _workbook_age_hours(path: Path) -> float:
    age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    return age_seconds / 3600.0


def _best_effort_failure_alert(*, message: str, db_path: Path, workbook_path: Path | None) -> None:
    context = f"db={db_path}"
    if workbook_path is not None:
        context += f", workbook={workbook_path}"
    try:
        send_run_failure_alert(
            error_message=message,
            script_name="run_strict_daily_preflight",
            context=context,
        )
    except Exception as exc:
        print(f"Preflight alert failed: {exc}")


def run_preflight(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path | None = None,
    emit_lineage: bool = False,
    lineage_output: Path | None = None,
    max_workbook_age_hours: float | None = None,
    send_alert_on_fail: bool = False,
) -> Tuple[int, str]:
    workbook = workbook_path
    if workbook is None:
        raw = os.environ.get("AB_CRM_WORKBOOK_PATH", "").strip()
        if raw:
            workbook = Path(raw).expanduser()

    if workbook is None:
        msg = "STRICT_DAILY_PREFLIGHT FAIL: AB_CRM_WORKBOOK_PATH is required"
        if send_alert_on_fail:
            _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=None)
        return 2, msg
    if not workbook.exists():
        msg = f"STRICT_DAILY_PREFLIGHT FAIL: workbook does not exist: {workbook}"
        if send_alert_on_fail:
            _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=workbook)
        return 2, msg

    age_limit_hours = _resolve_max_workbook_age_hours(max_workbook_age_hours)
    if age_limit_hours > 0:
        workbook_age_hours = _workbook_age_hours(workbook)
        if workbook_age_hours > age_limit_hours:
            msg = (
                "STRICT_DAILY_PREFLIGHT FAIL: stale workbook "
                f"(age_hours={workbook_age_hours:.1f}, max={age_limit_hours:.1f}) path={workbook}"
            )
            if send_alert_on_fail:
                _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=workbook)
            return 2, msg

    env = os.environ.copy()
    env["AB_CRM_WORKBOOK_PATH"] = str(workbook)

    cmd = [sys.executable, "scripts/validate_params.py", "--strict", "--db", str(db_path)]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
    strict_code = int(completed.returncode)

    lineage_path = lineage_output
    if emit_lineage and lineage_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        lineage_path = PROJECT_ROOT / "exports" / "lineage" / f"lineage_{ts}.json"

    if emit_lineage and lineage_path is not None:
        lineage_path.parent.mkdir(parents=True, exist_ok=True)
        emit_lineage_report(
            db_path=db_path,
            workbook_path=workbook,
            output_path=lineage_path,
            strict_exit_code=strict_code,
        )

    status = "PASS" if strict_code == 0 else "FAIL"
    msg = f"STRICT_DAILY_PREFLIGHT {status}: validate_params --strict rc={strict_code}"
    if emit_lineage and lineage_path is not None:
        msg += f" lineage={lineage_path}"
    if strict_code != 0 and send_alert_on_fail:
        _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=workbook)
    return strict_code, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict daily preflight with workbook-anchor enforcement")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Database path")
    parser.add_argument("--workbook", type=Path, default=None, help="CRM workbook path (overrides env)")
    parser.add_argument("--emit-lineage", action="store_true", help="Emit lineage artifact JSON")
    parser.add_argument("--lineage-output", type=Path, default=None, help="Explicit lineage artifact path")
    parser.add_argument(
        "--max-workbook-age-hours",
        type=float,
        default=None,
        help=f"Fail if workbook mtime age exceeds this threshold (default {DEFAULT_MAX_WORKBOOK_AGE_HOURS:g})",
    )
    parser.add_argument(
        "--send-alert-on-fail",
        action="store_true",
        help="Best-effort Telegram alert on preflight failure",
    )
    args = parser.parse_args()

    code, summary = run_preflight(
        db_path=args.db,
        workbook_path=args.workbook,
        emit_lineage=bool(args.emit_lineage),
        lineage_output=args.lineage_output,
        max_workbook_age_hours=args.max_workbook_age_hours,
        send_alert_on_fail=bool(args.send_alert_on_fail),
    )
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
