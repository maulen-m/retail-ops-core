#!/usr/bin/env python3
"""Shared runtime helpers for Google Ops Board automation schedulers."""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path("~/Docs/Autonomous_business")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import extract_rows_from_matrix


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_CLOSEOUT_LOCK_PATH = PROJECT_ROOT / "runtime" / "locks" / "google_ops_board_closeout.lock"
DEFAULT_READY_DEBOUNCE_STATE_PATH = PROJECT_ROOT / "runtime" / "state" / "google_ops_board_ready_watch.json"
EARLY_CLOSEOUT_WATCH_START_HOUR = 11
EARLY_CLOSEOUT_WATCH_END_HOUR = 18
EARLY_CLOSEOUT_WATCH_END_MINUTE = 30
READY_DEBOUNCE_SECONDS = 90


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def now_almaty() -> datetime:
    return datetime.now(ALMATY_TZ)


def today_almaty() -> date:
    return now_almaty().date()


def within_early_closeout_watch_window(now: datetime | None = None) -> bool:
    local_now = (now or now_almaty()).astimezone(ALMATY_TZ)
    current_minutes = local_now.hour * 60 + local_now.minute
    start_minutes = EARLY_CLOSEOUT_WATCH_START_HOUR * 60
    end_minutes = EARLY_CLOSEOUT_WATCH_END_HOUR * 60 + EARLY_CLOSEOUT_WATCH_END_MINUTE
    return start_minutes <= current_minutes < end_minutes


def load_ready_debounce_state(path: Path = DEFAULT_READY_DEBOUNCE_STATE_PATH) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ready_debounce_state(state: dict[str, Any], path: Path = DEFAULT_READY_DEBOUNCE_STATE_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def clear_ready_debounce_state(path: Path = DEFAULT_READY_DEBOUNCE_STATE_PATH) -> None:
    target = Path(path)
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def evaluate_ready_debounce(
    *,
    state: dict[str, Any],
    target_date: date,
    now: datetime,
    ready: bool,
    debounce_seconds: int = READY_DEBOUNCE_SECONDS,
) -> dict[str, Any]:
    if not ready:
        return {"action": "clear", "elapsed_seconds": 0, "remaining_seconds": 0}

    target_iso = target_date.isoformat()
    armed_at_raw = clean_text(state.get("armed_at"))
    state_target = clean_text(state.get("target_date"))
    if state_target != target_iso or not armed_at_raw:
        return {
            "action": "arm",
            "state": {"target_date": target_iso, "armed_at": now.isoformat()},
            "elapsed_seconds": 0,
            "remaining_seconds": int(debounce_seconds),
        }

    try:
        armed_at = datetime.fromisoformat(armed_at_raw)
    except ValueError:
        return {
            "action": "arm",
            "state": {"target_date": target_iso, "armed_at": now.isoformat()},
            "elapsed_seconds": 0,
            "remaining_seconds": int(debounce_seconds),
        }

    if armed_at.tzinfo is None:
        armed_at = armed_at.replace(tzinfo=ALMATY_TZ)

    elapsed_seconds = max(0, int((now - armed_at).total_seconds()))
    remaining = max(0, int(debounce_seconds) - elapsed_seconds)
    if elapsed_seconds >= int(debounce_seconds):
        return {
            "action": "trigger",
            "state": {"target_date": target_iso, "armed_at": armed_at.isoformat()},
            "elapsed_seconds": elapsed_seconds,
            "remaining_seconds": 0,
        }

    return {
        "action": "wait",
        "state": {"target_date": target_iso, "armed_at": armed_at.isoformat()},
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining,
    }


class GoogleOpsBoardAutomationLock:
    """Serialize closeout and scheduled writeback automation."""

    def __init__(self, lock_path: Path = DEFAULT_CLOSEOUT_LOCK_PATH):
        self.lock_path = Path(lock_path)
        self.lock_file = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = open(self.lock_path, "w")
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_file.write(f"{os.getpid()}\n")
            self.lock_file.flush()
            return self
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError(
                "Another Google Ops Board automation instance is already running.\n"
                f"Lock file: {self.lock_path}"
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
        return False


def select_run_control_row(*, client, contract, target_date: date) -> dict[str, Any] | None:
    headers = contract.tabs["Run_Control"].headers
    matrix = client.get_tab_values("Run_Control")
    rows = extract_rows_from_matrix(headers, matrix)
    target_iso = target_date.isoformat()
    for row in rows:
        if clean_text(row.get("target_date")) == target_iso:
            return row
    return rows[0] if rows else None


def closeout_completion_state(*, client, contract, target_date: date) -> dict[str, Any]:
    row = select_run_control_row(client=client, contract=contract, target_date=target_date)
    target_match = bool(row) and clean_text((row or {}).get("target_date")) == target_date.isoformat()
    status = clean_text((row or {}).get("last_orchestrator_status")).upper()
    run_id = clean_text((row or {}).get("last_orchestrator_run_id"))
    return {
        "target_date": target_date.isoformat(),
        "completed": bool(target_match and status == "OK"),
        "status": status,
        "run_id": run_id,
        "row": row or {},
        "target_match": target_match,
    }
