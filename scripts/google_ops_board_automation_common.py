#!/usr/bin/env python3
"""Shared runtime helpers for Google Ops Board automation schedulers."""

from __future__ import annotations

import fcntl
import hashlib
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
DEFAULT_PREWINDOW_HEALTH_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "health"
DEFAULT_CLOSEOUT_CHECKPOINT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "workflow_runs"
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


def load_json_file(path: Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json_file(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def resolve_prewindow_health_report_path(
    target_date: date,
    root: Path = DEFAULT_PREWINDOW_HEALTH_ROOT,
    profile: str = "full",
) -> Path:
    profile_name = str(profile or "full").strip().lower()
    filename_map = {
        "full": "prewindow_health.json",
        "publish": "publish_health.json",
        "closeout": "closeout_health.json",
    }
    filename = filename_map.get(profile_name, f"{profile_name}_health.json")
    return Path(root) / target_date.isoformat() / filename


def resolve_closeout_checkpoint_path(
    target_date: date,
    root: Path = DEFAULT_CLOSEOUT_CHECKPOINT_ROOT,
) -> Path:
    return Path(root) / target_date.isoformat() / "closeout_checkpoint.json"


def build_workbook_fingerprint(workbook_path: Path) -> dict[str, Any]:
    path = Path(workbook_path).expanduser().resolve()
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": digest.hexdigest(),
    }


def salesraw_writeback_fingerprint(rows: list[dict[str, Any]]) -> str:
    stable_rows: list[dict[str, str]] = []
    for row in rows:
        stable_rows.append(
            {
                "_db_row_id": clean_text(row.get("_db_row_id")),
                "_line_key": clean_text(row.get("_line_key")),
                "OrderID": clean_text(row.get("OrderID")),
                "MY_SIZE": clean_text(row.get("MY_SIZE")),
                "Status": clean_text(row.get("Status")),
                "Date": clean_text(row.get("Date")),
            }
        )
    stable_rows.sort(key=lambda item: (item["_db_row_id"], item["_line_key"], item["OrderID"]))
    payload = json.dumps(stable_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
