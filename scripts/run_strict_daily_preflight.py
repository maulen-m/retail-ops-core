#!/usr/bin/env python3
"""
Run strict daily validation with workbook-anchor enforcement.

Fail closed when workbook path is not provided or missing.
Optionally emit lineage artifact.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable, Sequence, Tuple

from dotenv import load_dotenv as _load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAX_WORKBOOK_AGE_HOURS = 36.0
DEFAULT_MAX_FUTURE_MTIME_SKEW_SECONDS = 120.0
DEFAULT_MAX_WORKBOOK_LAG_DAYS = 1
PROOF_WINDOW_LOCK_ENV = "AB_PROOF_WINDOW_LOCK_PATH"
PROOF_WINDOW_LOCK_DEFAULT_RELATIVE = Path("config") / "proof_window.lock"
PROOF_WINDOW_BLOCK_EXIT_CODE = 75
PROOF_WINDOW_BLOCK_TOKEN = "STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.validation_copy import validation_db_path

# Optional dependency loaded lazily for bootstrap safety and test injection.
build_single_truth_drift_pack: Callable[..., dict] | None = None
send_run_failure_alert: Callable[..., bool] | None = None


def load_repo_dotenv() -> None:
    _load_dotenv(PROJECT_ROOT / ".env", override=False)


def _resolve_reexec_target(
    *,
    project_root: Path = PROJECT_ROOT,
    current_executable: str | Path | None = None,
) -> Path | None:
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return None
    current = Path(current_executable or sys.executable)
    try:
        current_resolved = current.resolve()
    except OSError:
        current_resolved = current
    try:
        target_resolved = venv_python.resolve()
    except OSError:
        target_resolved = venv_python
    if current_resolved == target_resolved:
        return None
    return target_resolved


def bootstrap_repo_venv_python(
    *,
    project_root: Path = PROJECT_ROOT,
    current_executable: str | Path | None = None,
    argv: Sequence[str] | None = None,
    execv_fn: Callable[[str, list[str]], None] | None = None,
) -> bool:
    target = _resolve_reexec_target(
        project_root=project_root,
        current_executable=current_executable,
    )
    if target is None:
        return False
    execv = execv_fn or os.execv
    arg_values = list(argv if argv is not None else sys.argv)
    execv(str(target), [str(target), *arg_values])
    return True


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


def _resolve_max_future_mtime_skew_seconds(value: float | None) -> float:
    if value is not None:
        return float(value)
    env_raw = os.environ.get("AB_CRM_WORKBOOK_MAX_FUTURE_SKEW_SECONDS", "").strip()
    if env_raw:
        try:
            return float(env_raw)
        except ValueError:
            return DEFAULT_MAX_FUTURE_MTIME_SKEW_SECONDS
    return DEFAULT_MAX_FUTURE_MTIME_SKEW_SECONDS


def _resolve_max_workbook_lag_days(value: int | None) -> int:
    if value is not None:
        return int(value)
    env_raw = os.environ.get("AB_CRM_WORKBOOK_MAX_LAG_DAYS", "").strip()
    if env_raw:
        try:
            return int(env_raw)
        except ValueError:
            return DEFAULT_MAX_WORKBOOK_LAG_DAYS
    return DEFAULT_MAX_WORKBOOK_LAG_DAYS


def _resolve_proof_window_lock_path(project_root: Path | None = None) -> Path:
    raw = os.environ.get(PROOF_WINDOW_LOCK_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    root = project_root if project_root is not None else PROJECT_ROOT
    return root / PROOF_WINDOW_LOCK_DEFAULT_RELATIVE


def _proof_window_lock_block_message(lock_path: Path, *, stat_error: str | None = None) -> str:
    msg = f"{PROOF_WINDOW_BLOCK_TOKEN} path={lock_path}"
    if stat_error:
        msg += f" stat_error={stat_error}"
    return msg


def _proof_window_lock_block_status(*, project_root: Path | None = None) -> Tuple[int, str] | None:
    lock_path = _resolve_proof_window_lock_path(project_root)
    try:
        lock_path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return PROOF_WINDOW_BLOCK_EXIT_CODE, _proof_window_lock_block_message(
            lock_path,
            stat_error=str(exc),
        )
    return PROOF_WINDOW_BLOCK_EXIT_CODE, _proof_window_lock_block_message(lock_path)


def _workbook_age_hours(path: Path) -> float:
    age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    return age_seconds / 3600.0


def _best_effort_failure_alert(*, message: str, db_path: Path, workbook_path: Path | None) -> None:
    context = f"db={db_path}"
    if workbook_path is not None:
        context += f", workbook={workbook_path}"
    try:
        global send_run_failure_alert
        if send_run_failure_alert is None:
            from core.alerts.error_alerts import send_run_failure_alert as _sender

            send_run_failure_alert = _sender
        send_run_failure_alert(
            error_message=message,
            script_name="run_strict_daily_preflight",
            context=context,
        )
    except Exception as exc:
        print(f"Preflight alert failed: {exc}")


def _load_drift_pack_builder() -> Callable[..., dict] | None:
    global build_single_truth_drift_pack
    if callable(build_single_truth_drift_pack):
        return build_single_truth_drift_pack
    try:
        from scripts.build_single_truth_drift_pack import (
            build_single_truth_drift_pack as _build_single_truth_drift_pack,
        )

        build_single_truth_drift_pack = _build_single_truth_drift_pack
        return build_single_truth_drift_pack
    except Exception:
        build_single_truth_drift_pack = None
        return None


def _business_insides_snapshot_exists(as_of_iso: str) -> bool:
    current = PROJECT_ROOT / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of_iso}.md"
    snapshot = (
        PROJECT_ROOT
        / "config"
        / "business_insides"
        / "snapshots"
        / f"BUSINESS_INSIDES_{as_of_iso}.md"
    )
    return current.exists() or snapshot.exists()


def _ensure_business_insides_snapshot(
    *,
    db_path: Path,
    as_of_iso: str,
    send_alert_on_fail: bool,
    workbook_path: Path,
    alert_db_path: Path | None = None,
) -> Tuple[int, str | None]:
    if _business_insides_snapshot_exists(as_of_iso):
        return 0, None
    alert_db = alert_db_path or db_path

    cmd = [
        sys.executable,
        "scripts/generate_business_insides.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of_iso,
    ]
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    if int(completed.returncode) != 0:
        msg = (
            "STRICT_DAILY_PREFLIGHT FAIL: business-insides generation failed "
            f"rc={int(completed.returncode)} as_of={as_of_iso}"
        )
        if send_alert_on_fail:
            _best_effort_failure_alert(message=msg, db_path=alert_db, workbook_path=workbook_path)
        return int(completed.returncode), msg
    if not _business_insides_snapshot_exists(as_of_iso):
        msg = (
            "STRICT_DAILY_PREFLIGHT FAIL: business-insides snapshot missing after generation "
            f"as_of={as_of_iso}"
        )
        if send_alert_on_fail:
            _best_effort_failure_alert(message=msg, db_path=alert_db, workbook_path=workbook_path)
        return 2, msg
    return 0, None


def run_preflight(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path | None = None,
    emit_lineage: bool = False,
    lineage_output: Path | None = None,
    max_workbook_age_hours: float | None = None,
    max_future_mtime_skew_seconds: float | None = None,
    send_alert_on_fail: bool = False,
    ensure_business_insides: bool = True,
    business_insides_as_of: str | None = None,
    emit_drift_pack: bool = True,
) -> Tuple[int, str]:
    proof_window_block = _proof_window_lock_block_status()
    if proof_window_block is not None:
        return proof_window_block

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
    if not db_path.exists():
        msg = f"STRICT_DAILY_PREFLIGHT FAIL: database does not exist: {db_path}"
        if send_alert_on_fail:
            _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=workbook)
        return 2, msg

    allowed_future_skew = _resolve_max_future_mtime_skew_seconds(max_future_mtime_skew_seconds)
    now_ts = time.time()
    mtime_delta_seconds = workbook.stat().st_mtime - now_ts
    if mtime_delta_seconds > allowed_future_skew:
        msg = (
            "STRICT_DAILY_PREFLIGHT FAIL: future workbook mtime "
            f"(future_seconds={mtime_delta_seconds:.1f}, max_skew={allowed_future_skew:.1f}) path={workbook}"
        )
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

    with validation_db_path(db_path) as validation_db:
        if ensure_business_insides:
            as_of_iso = (business_insides_as_of or date.today().isoformat()).strip()
            generate_code, generate_error = _ensure_business_insides_snapshot(
                db_path=validation_db,
                as_of_iso=as_of_iso,
                send_alert_on_fail=send_alert_on_fail,
                workbook_path=workbook,
                alert_db_path=db_path,
            )
            if generate_code != 0:
                return generate_code, str(generate_error)

        env = os.environ.copy()
        env["AB_CRM_WORKBOOK_PATH"] = str(workbook)

        cmd = [sys.executable, "scripts/validate_params.py", "--strict", "--db", str(validation_db)]
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=False)
        strict_code = int(completed.returncode)

        lineage_path = lineage_output
        if emit_lineage and lineage_path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            lineage_path = PROJECT_ROOT / "exports" / "lineage" / f"lineage_{ts}.json"

        if emit_lineage and lineage_path is not None:
            lineage_path.parent.mkdir(parents=True, exist_ok=True)
            emit_lineage_report(
                db_path=validation_db,
                workbook_path=workbook,
                output_path=lineage_path,
                strict_exit_code=strict_code,
            )

        drift_pack_path: Path | None = None
        drift_pack_error: str | None = None
        drift_pack_builder = _load_drift_pack_builder() if emit_drift_pack else None
        if strict_code == 0 and emit_drift_pack and callable(drift_pack_builder):
            try:
                as_of_iso = (business_insides_as_of or date.today().isoformat()).strip()
                max_lag_days = _resolve_max_workbook_lag_days(None)
                drift_result = drift_pack_builder(
                    db_path=validation_db,
                    as_of=as_of_iso,
                    workbook_path=workbook,
                    max_lag_days=max_lag_days,
                )
                drift_pack_path = Path(str(drift_result.get("markdown_path", "")))
            except Exception as exc:
                drift_pack_error = str(exc)

    status = "PASS" if strict_code == 0 else "FAIL"
    msg = f"STRICT_DAILY_PREFLIGHT {status}: validate_params --strict rc={strict_code}"
    if emit_lineage and lineage_path is not None:
        msg += f" lineage={lineage_path}"
    if drift_pack_path is not None:
        msg += f" drift_pack={drift_pack_path}"
    if drift_pack_error:
        msg += f" drift_pack_error={drift_pack_error}"
    if strict_code != 0 and send_alert_on_fail:
        _best_effort_failure_alert(message=msg, db_path=db_path, workbook_path=workbook)
    return strict_code, msg


def main() -> int:
    load_repo_dotenv()
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
        "--max-future-mtime-skew-seconds",
        type=float,
        default=None,
        help=(
            "Fail if workbook mtime is in the future beyond this skew "
            f"(default {DEFAULT_MAX_FUTURE_MTIME_SKEW_SECONDS:g} seconds)"
        ),
    )
    parser.add_argument(
        "--send-alert-on-fail",
        action="store_true",
        help="Best-effort Telegram alert on preflight failure",
    )
    parser.add_argument(
        "--ensure-business-insides",
        dest="ensure_business_insides",
        action="store_true",
        default=True,
        help="Generate missing BUSINESS_INSIDES snapshot for the preflight as-of date",
    )
    parser.add_argument(
        "--no-ensure-business-insides",
        dest="ensure_business_insides",
        action="store_false",
        help="Disable BUSINESS_INSIDES auto-generation in preflight",
    )
    parser.add_argument(
        "--business-insides-as-of",
        type=str,
        default=None,
        help="BUSINESS_INSIDES as-of date (YYYY-MM-DD); defaults to today",
    )
    parser.add_argument(
        "--emit-drift-pack",
        dest="emit_drift_pack",
        action="store_true",
        default=True,
        help="Emit single-truth drift pack after strict PASS",
    )
    parser.add_argument(
        "--no-emit-drift-pack",
        dest="emit_drift_pack",
        action="store_false",
        help="Disable drift pack emission after strict PASS",
    )
    args = parser.parse_args()

    code, summary = run_preflight(
        db_path=args.db,
        workbook_path=args.workbook,
        emit_lineage=bool(args.emit_lineage),
        lineage_output=args.lineage_output,
        max_workbook_age_hours=args.max_workbook_age_hours,
        max_future_mtime_skew_seconds=args.max_future_mtime_skew_seconds,
        send_alert_on_fail=bool(args.send_alert_on_fail),
        ensure_business_insides=bool(args.ensure_business_insides),
        business_insides_as_of=args.business_insides_as_of,
        emit_drift_pack=bool(args.emit_drift_pack),
    )
    print(summary)
    return code


if __name__ == "__main__":
    bootstrap_repo_venv_python()
    raise SystemExit(main())
