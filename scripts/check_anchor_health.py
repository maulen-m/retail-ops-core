#!/usr/bin/env python3
"""Fail-closed anchor and runtime health checks for single-truth ops."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import subprocess
import time
from typing import Sequence

from scripts.validate_sales_against_workbook import parse_workbook_daily_totals

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CRM_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
DEFAULT_INBOUND_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
DEFAULT_VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
DEFAULT_MAX_AGE_HOURS = 36.0
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 120.0
DEFAULT_MAX_LAG_DAYS = 1


def _resolve_float(arg_value: float | None, env_key: str, default: float) -> float:
    if arg_value is not None:
        return float(arg_value)
    raw = os.environ.get(env_key, "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def _resolve_int(arg_value: int | None, env_key: str, default: int) -> int:
    if arg_value is not None:
        return int(arg_value)
    raw = os.environ.get(env_key, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            return default
    return default


def _validate_anchor_symlink(anchor_path: Path, *, name: str) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    if not anchor_path.exists() and not anchor_path.is_symlink():
        errors.append(f"missing anchor symlink: {name} path={anchor_path}")
        return None, errors
    if not anchor_path.is_symlink():
        errors.append(f"anchor is not symlink: {name} path={anchor_path}")
        return None, errors
    try:
        target = anchor_path.resolve(strict=True)
    except FileNotFoundError:
        errors.append(f"broken anchor symlink: {name} path={anchor_path}")
        return None, errors
    return target, errors


def _validate_workbook_mtime(
    workbook_path: Path,
    *,
    now_ts: float,
    max_age_hours: float,
    max_future_skew_seconds: float,
) -> list[str]:
    st = workbook_path.stat()
    age_seconds = now_ts - st.st_mtime
    future_seconds = st.st_mtime - now_ts
    errors: list[str] = []
    if future_seconds > max_future_skew_seconds:
        errors.append(
            "future workbook mtime beyond skew "
            f"(future_seconds={future_seconds:.1f}, max_skew={max_future_skew_seconds:.1f})"
        )
    if max_age_hours > 0 and age_seconds > max_age_hours * 3600:
        errors.append(
            "stale workbook mtime "
            f"(age_hours={age_seconds/3600.0:.1f}, max={max_age_hours:.1f})"
        )
    return errors


def _validate_content_lag(
    workbook_path: Path,
    *,
    as_of: date,
    max_lag_days: int,
) -> list[str]:
    errors: list[str] = []
    try:
        daily = parse_workbook_daily_totals(workbook_path)
    except Exception as exc:  # pragma: no cover - covered via error assertions
        return [f"unable to parse workbook content for lag check: {exc}"]
    if not daily:
        return ["unable to parse workbook content for lag check: no daily rows found"]
    max_day = max(date.fromisoformat(day_iso) for day_iso in daily.keys())
    lag_days = (as_of - max_day).days
    if lag_days > max_lag_days:
        errors.append(
            "workbook content lag exceeds threshold "
            f"(workbook_max_date={max_day.isoformat()}, as_of={as_of.isoformat()}, "
            f"lag_days={lag_days}, max_lag_days={max_lag_days})"
        )
    return errors


def _validate_venv_imports(venv_python: Path) -> list[str]:
    if not venv_python.exists():
        return [f"missing .venv/bin/python at {venv_python}"]
    if not os.access(venv_python, os.X_OK):
        return [f".venv/bin/python is not executable at {venv_python}"]
    check = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import pandas; import requests; import openpyxl",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        err = (check.stderr or check.stdout or "").strip()
        return [f"cannot import pandas/requests/openpyxl with {venv_python}: {err}".strip()]
    return []


def check_anchor_health(
    *,
    project_root: Path = PROJECT_ROOT,
    crm_anchor: Path | None = None,
    inbound_anchor: Path | None = None,
    venv_python: Path | None = None,
    max_age_hours: float | None = None,
    max_future_skew_seconds: float | None = None,
    max_lag_days: int | None = None,
    as_of: date | None = None,
    now_ts: float | None = None,
) -> tuple[int, list[str]]:
    root = project_root.resolve()
    crm_anchor_path = crm_anchor or (root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx")
    inbound_anchor_path = inbound_anchor or (root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx")
    venv_path = venv_python or (root / ".venv" / "bin" / "python")
    now = float(now_ts if now_ts is not None else time.time())
    current_day = as_of or date.today()
    age_limit = _resolve_float(max_age_hours, "AB_CRM_WORKBOOK_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS)
    future_limit = _resolve_float(
        max_future_skew_seconds,
        "AB_CRM_WORKBOOK_MAX_FUTURE_SKEW_SECONDS",
        DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    )
    lag_limit = _resolve_int(max_lag_days, "AB_CRM_WORKBOOK_MAX_LAG_DAYS", DEFAULT_MAX_LAG_DAYS)

    errors: list[str] = []
    lines: list[str] = []

    crm_target, crm_errors = _validate_anchor_symlink(crm_anchor_path, name="crm_anchor")
    inbound_target, inbound_errors = _validate_anchor_symlink(inbound_anchor_path, name="inbound_anchor")
    errors.extend(crm_errors)
    errors.extend(inbound_errors)

    if crm_target is not None:
        errors.extend(
            _validate_workbook_mtime(
                crm_target,
                now_ts=now,
                max_age_hours=age_limit,
                max_future_skew_seconds=future_limit,
            )
        )
        errors.extend(
            _validate_content_lag(
                crm_target,
                as_of=current_day,
                max_lag_days=lag_limit,
            )
        )
        lines.append(f"crm_anchor={crm_anchor_path} -> {crm_target}")
    if inbound_target is not None:
        lines.append(f"inbound_anchor={inbound_anchor_path} -> {inbound_target}")

    errors.extend(_validate_venv_imports(venv_path))
    lines.append(
        "thresholds="
        f"max_age_hours={age_limit} max_future_skew_seconds={future_limit} max_lag_days={lag_limit}"
    )

    if errors:
        lines.append("anchor health FAIL")
        lines.extend(f"ERROR: {err}" for err in errors)
        return 1, lines

    lines.append("anchor health PASS")
    return 0, lines


def _print_lines(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed anchor and runtime health check")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help="Repository root path")
    parser.add_argument("--crm-anchor", type=Path, default=DEFAULT_CRM_ANCHOR, help="CRM anchor symlink")
    parser.add_argument("--inbound-anchor", type=Path, default=DEFAULT_INBOUND_ANCHOR, help="Inbound anchor symlink")
    parser.add_argument("--venv-python", type=Path, default=DEFAULT_VENV_PYTHON, help="Repo venv python path")
    parser.add_argument("--max-age-hours", type=float, default=None, help="Override workbook max age hours")
    parser.add_argument(
        "--max-future-skew-seconds",
        type=float,
        default=None,
        help="Override allowed future mtime skew in seconds",
    )
    parser.add_argument("--max-lag-days", type=int, default=None, help="Override workbook content lag threshold")
    parser.add_argument("--as-of", type=str, default=None, help="As-of date in YYYY-MM-DD")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    code, lines = check_anchor_health(
        project_root=args.project_root,
        crm_anchor=args.crm_anchor,
        inbound_anchor=args.inbound_anchor,
        venv_python=args.venv_python,
        max_age_hours=args.max_age_hours,
        max_future_skew_seconds=args.max_future_skew_seconds,
        max_lag_days=args.max_lag_days,
        as_of=as_of,
    )
    _print_lines(lines)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
