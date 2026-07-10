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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import extract_rows_from_matrix
from scripts.waybill_delivery_completion import (
    DEFAULT_RUN_ROOT,
    DEFAULT_TODAY_FOLDER,
    delivery_completion_state,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_CLOSEOUT_LOCK_PATH = PROJECT_ROOT / "runtime" / "locks" / "google_ops_board_closeout.lock"
DEFAULT_READY_DEBOUNCE_STATE_PATH = PROJECT_ROOT / "runtime" / "state" / "google_ops_board_ready_watch.json"
DEFAULT_CLOSEOUT_HALT_BARRIER_PATH = (
    PROJECT_ROOT / "runtime" / "state" / "google_ops_board_closeout_halt_barrier.json"
)
DEFAULT_PREWINDOW_HEALTH_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "health"
DEFAULT_CLOSEOUT_CHECKPOINT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "workflow_runs"
DEFAULT_KASPI_API_LEDGER_ROOT = PROJECT_ROOT / "runtime" / "api_ledger"
AUTOMATION_LOCK_HELD_ENV = "AB_GOOGLE_OPS_BOARD_LOCK_HELD"
EARLY_CLOSEOUT_WATCH_START_HOUR = 9
EARLY_CLOSEOUT_WATCH_END_HOUR = 19
EARLY_CLOSEOUT_WATCH_END_MINUTE = 5
AUTO_PROBABLE_CLOSEOUT_HOUR = 18
AUTO_PROBABLE_CLOSEOUT_MINUTE = 57
READY_DEBOUNCE_SECONDS = 60
HALT_BARRIER_SCHEMA_VERSION = 1


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def now_almaty() -> datetime:
    return datetime.now(ALMATY_TZ)


def today_almaty() -> date:
    return now_almaty().date()


def ensure_kaspi_api_call_ledger_env(
    env: dict[str, str],
    *,
    target_date: date,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, str]:
    """Default scheduled Kaspi API calls into a per-day JSONL ledger."""
    if str(env.get("KASPI_API_CALL_LEDGER_PATH") or "").strip():
        return env
    if str(env.get("KASPI_API_CALL_LEDGER") or "").strip():
        return env
    ledger_path = Path(project_root) / "runtime" / "api_ledger" / f"kaspi_api_{target_date.isoformat()}.jsonl"
    env["KASPI_API_CALL_LEDGER_PATH"] = str(ledger_path)
    return env


def within_early_closeout_watch_window(now: datetime | None = None) -> bool:
    local_now = (now or now_almaty()).astimezone(ALMATY_TZ)
    current_minutes = local_now.hour * 60 + local_now.minute
    start_minutes = EARLY_CLOSEOUT_WATCH_START_HOUR * 60
    end_minutes = EARLY_CLOSEOUT_WATCH_END_HOUR * 60 + EARLY_CLOSEOUT_WATCH_END_MINUTE
    return start_minutes <= current_minutes < end_minutes


def auto_probable_closeout_cutoff_reached(now: datetime | None = None) -> bool:
    local_now = (now or now_almaty()).astimezone(ALMATY_TZ)
    current_minutes = local_now.hour * 60 + local_now.minute
    cutoff_minutes = AUTO_PROBABLE_CLOSEOUT_HOUR * 60 + AUTO_PROBABLE_CLOSEOUT_MINUTE
    return current_minutes >= cutoff_minutes


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


def _atomic_save_json_file(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace a local control-plane JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.parent / f".{target.name}.{os.getpid()}.tmp"
    raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def load_closeout_halt_barrier(
    path: Path = DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
) -> dict[str, Any]:
    """Read the durable halt barrier; malformed state is itself blocking."""
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema_version": HALT_BARRIER_SCHEMA_VERSION,
            "state": "UNREADABLE",
            "blocks_automation": True,
            "path": str(target),
            "load_error": f"{type(exc).__name__}: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": HALT_BARRIER_SCHEMA_VERSION,
            "state": "UNREADABLE",
            "blocks_automation": True,
            "path": str(target),
            "load_error": "halt barrier is not a JSON object",
        }
    payload["path"] = str(target)
    return payload


def persist_closeout_halt_barrier(
    *,
    target_date: date,
    requested_at: datetime,
    source: str,
    request_key: str = "",
    path: Path = DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
) -> dict[str, Any]:
    """Persist the stop intent before any best-effort Google HOLD write."""
    existing = load_closeout_halt_barrier(path)
    local_requested_at = requested_at.astimezone(ALMATY_TZ)
    incoming_key = clean_text(request_key)
    existing_at = _parse_iso_datetime(existing.get("halt_requested_at"))
    same_target = clean_text(existing.get("target_date")) == target_date.isoformat()
    exact_replay = bool(
        same_target
        and incoming_key
        and incoming_key == clean_text(existing.get("halt_request_key"))
    )
    if exact_replay or (
        same_target and existing_at is not None and local_requested_at <= existing_at
    ):
        return existing
    payload = {
        "schema_version": HALT_BARRIER_SCHEMA_VERSION,
        "target_date": target_date.isoformat(),
        "halt_requested_at": local_requested_at.isoformat(),
        "source": clean_text(source) or "unknown",
        "halt_request_key": incoming_key,
        "state": "PENDING_HOLD",
        "blocks_automation": True,
        "updated_at": local_requested_at.isoformat(),
    }
    if same_target and existing_at is not None:
        payload["supersedes_halt_requested_at"] = existing_at.isoformat()
        payload["supersedes_halt_request_key"] = clean_text(
            existing.get("halt_request_key")
        )
    _atomic_save_json_file(path, payload)
    return load_closeout_halt_barrier(path)


def evaluate_closeout_halt_barrier(
    *,
    target_date: date,
    run_control_row: dict[str, Any] | None,
    request_ready_set_at: str = "",
    now: datetime | None = None,
    path: Path = DEFAULT_CLOSEOUT_HALT_BARRIER_PATH,
    persist_safe_transition: bool = True,
) -> dict[str, Any]:
    """Return whether the local halt barrier forbids this READY request.

    A proven exact HOLD changes the barrier from ``PENDING_HOLD`` to
    ``HOLD_CONFIRMED`` but deliberately keeps automation blocked.  A subsequent
    exact READY with a timestamp newer than the halt supersedes the barrier.  A
    blank READY is stampable only after HOLD was proven, which distinguishes a
    fresh employee transition from the stale READY that existed when HOLD
    failed.  Old in-flight request identities remain barred permanently.
    """
    barrier = load_closeout_halt_barrier(path)
    if not barrier:
        return {
            "blocked": False,
            "reason": "NO_HALT_BARRIER",
            "allow_fresh_blank_ready": False,
            "request_halted": False,
            "barrier": {},
        }
    if clean_text(barrier.get("state")) == "UNREADABLE":
        return {
            "blocked": True,
            "reason": "HALT_BARRIER_UNREADABLE",
            "allow_fresh_blank_ready": False,
            "request_halted": True,
            "barrier": barrier,
        }

    row = dict(run_control_row or {})
    row_target = clean_text(row.get("target_date"))
    row_ready_at_raw = clean_text(row.get("ready_set_at"))
    row_ready_value = clean_text(row.get("ready_for_closeout")).upper()
    barrier_target = clean_text(barrier.get("target_date"))
    halt_at = _parse_iso_datetime(barrier.get("halt_requested_at"))
    request_ready_at = _parse_iso_datetime(request_ready_set_at)
    row_ready_at = _parse_iso_datetime(row_ready_at_raw)
    local_now = (now or now_almaty()).astimezone(ALMATY_TZ)

    request_halted = bool(
        barrier_target == target_date.isoformat()
        and clean_text(request_ready_set_at)
        and (
            halt_at is None
            or request_ready_at is None
            or request_ready_at <= halt_at
        )
    )

    exact_hold = bool(
        barrier_target == target_date.isoformat()
        and
        row_target == target_date.isoformat()
        and row_ready_value == "HOLD"
        and not row_ready_at_raw
    )
    if exact_hold:
        if clean_text(barrier.get("state")) != "HOLD_CONFIRMED":
            barrier = {
                **barrier,
                "state": "HOLD_CONFIRMED",
                "blocks_automation": True,
                "hold_confirmed_at": local_now.isoformat(),
                "hold_readback": {
                    "target_date": row_target,
                    "ready_for_closeout": row_ready_value,
                    "ready_set_at": "",
                },
                "updated_at": local_now.isoformat(),
            }
            barrier.pop("path", None)
            if persist_safe_transition:
                _atomic_save_json_file(path, barrier)
                barrier = load_closeout_halt_barrier(path)
        return {
            "blocked": True,
            "reason": "HALT_CONFIRMED",
            "allow_fresh_blank_ready": False,
            "request_halted": request_halted,
            "barrier": barrier,
        }

    ready_is_post_halt = bool(
        row_target == target_date.isoformat()
        and row_ready_value == "READY"
        and row_ready_at is not None
        and halt_at is not None
        and row_ready_at > halt_at
    )
    if ready_is_post_halt:
        if bool(barrier.get("blocks_automation")) or clean_text(
            barrier.get("state")
        ) != "SUPERSEDED_BY_FRESH_READY":
            barrier = {
                **barrier,
                "state": "SUPERSEDED_BY_FRESH_READY",
                "blocks_automation": False,
                "superseded_at": local_now.isoformat(),
                "superseding_request_identity": {
                    "target_date": row_target,
                    "ready_set_at": row_ready_at_raw,
                },
                "updated_at": local_now.isoformat(),
            }
            barrier.pop("path", None)
            if persist_safe_transition:
                _atomic_save_json_file(path, barrier)
                barrier = load_closeout_halt_barrier(path)
        return {
            "blocked": request_halted,
            "reason": "REQUEST_HALTED" if request_halted else "FRESH_READY_SUPERSEDES_HALT",
            "allow_fresh_blank_ready": False,
            "request_halted": request_halted,
            "barrier": barrier,
        }

    try:
        barrier_date = date.fromisoformat(barrier_target)
    except ValueError:
        barrier_date = None
    date_rollover_ready = bool(
        barrier_date is not None and target_date > barrier_date
    )
    allow_fresh_blank_ready = bool(
        (
            clean_text(barrier.get("state")) == "HOLD_CONFIRMED"
            or date_rollover_ready
        )
        and row_target == target_date.isoformat()
        and row_ready_value == "READY"
        and not row_ready_at_raw
    )
    globally_blocked = bool(barrier.get("blocks_automation", True))
    return {
        "blocked": bool(globally_blocked or request_halted),
        "reason": (
            "FRESH_BLANK_READY_REQUIRES_IDENTITY_STAMP"
            if allow_fresh_blank_ready
            else ("REQUEST_HALTED" if request_halted else "HALT_BARRIER_ACTIVE")
        ),
        "allow_fresh_blank_ready": allow_fresh_blank_ready,
        "request_halted": request_halted,
        "barrier": barrier,
    }


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
    ready_set_at: str = "",
    debounce_seconds: int = READY_DEBOUNCE_SECONDS,
) -> dict[str, Any]:
    if not ready:
        return {"action": "clear", "elapsed_seconds": 0, "remaining_seconds": 0}

    target_iso = target_date.isoformat()
    ready_identity = clean_text(ready_set_at)
    armed_at_raw = clean_text(state.get("armed_at"))
    state_target = clean_text(state.get("target_date"))
    state_ready_set_at = clean_text(state.get("ready_set_at"))
    if state_target != target_iso or state_ready_set_at != ready_identity or not armed_at_raw:
        return {
            "action": "arm",
            "state": {
                "target_date": target_iso,
                "ready_set_at": ready_identity,
                "armed_at": now.isoformat(),
            },
            "elapsed_seconds": 0,
            "remaining_seconds": int(debounce_seconds),
        }

    try:
        armed_at = datetime.fromisoformat(armed_at_raw)
    except ValueError:
        return {
            "action": "arm",
            "state": {
                "target_date": target_iso,
                "ready_set_at": ready_identity,
                "armed_at": now.isoformat(),
            },
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
            "state": {
                "target_date": target_iso,
                "ready_set_at": ready_identity,
                "armed_at": armed_at.isoformat(),
            },
            "elapsed_seconds": elapsed_seconds,
            "remaining_seconds": 0,
        }

    return {
        "action": "wait",
        "state": {
            "target_date": target_iso,
            "ready_set_at": ready_identity,
            "armed_at": armed_at.isoformat(),
        },
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
    return None


def run_control_request_identity(row: dict[str, Any] | None) -> dict[str, str]:
    return {
        "target_date": clean_text((row or {}).get("target_date")),
        "ready_set_at": clean_text((row or {}).get("ready_set_at")),
    }


def closeout_completion_state(
    *,
    client,
    contract,
    target_date: date,
    today_folder: Path = DEFAULT_TODAY_FOLDER,
    run_root: Path = DEFAULT_RUN_ROOT,
) -> dict[str, Any]:
    row = select_run_control_row(client=client, contract=contract, target_date=target_date)
    target_match = bool(row) and clean_text((row or {}).get("target_date")) == target_date.isoformat()
    status = clean_text((row or {}).get("last_orchestrator_status")).upper()
    run_id = clean_text((row or {}).get("last_orchestrator_run_id"))
    request_identity = run_control_request_identity(row)
    checkpoint_path = resolve_closeout_checkpoint_path(target_date, root=Path(run_root))
    checkpoint = load_json_file(checkpoint_path)
    delivery_pin = dict(checkpoint.get("delivery_artifacts") or {})
    manifest_path_text = clean_text(delivery_pin.get("manifest_path"))
    manifest_sha256 = clean_text(delivery_pin.get("manifest_sha256"))
    pinned_request_identity = {
        "target_date": clean_text(
            (delivery_pin.get("request_identity") or {}).get("target_date")
        ),
        "ready_set_at": clean_text(
            (delivery_pin.get("request_identity") or {}).get("ready_set_at")
        ),
    }
    pin_status = ""
    if clean_text(checkpoint.get("execution_mode")) != "apply":
        pin_status = "CHECKPOINT_APPLY_PIN_MISSING"
    elif clean_text(checkpoint.get("target_date")) != target_date.isoformat():
        pin_status = "CHECKPOINT_TARGET_DATE_MISMATCH"
    elif pinned_request_identity != request_identity:
        pin_status = "CHECKPOINT_REQUEST_IDENTITY_MISMATCH"
    elif not manifest_path_text or len(manifest_sha256) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in manifest_sha256
    ):
        pin_status = "CHECKPOINT_MANIFEST_UNPINNED"
    else:
        pinned_manifest = Path(manifest_path_text).expanduser()
        if not pinned_manifest.is_file():
            pin_status = "CHECKPOINT_MANIFEST_MISSING"
        elif hashlib.sha256(pinned_manifest.read_bytes()).hexdigest() != manifest_sha256:
            pin_status = "CHECKPOINT_MANIFEST_SHA256_MISMATCH"

    if pin_status:
        delivery_state = {
            "completed": False,
            "status": pin_status,
            "channel": "",
            "target_date": target_date.isoformat(),
            "request_identity": {},
            "manifest_path": manifest_path_text,
            "manifest_count": 0,
            "confirmed_count": 0,
        }
    else:
        delivery_state = delivery_completion_state(
            today_folder=Path(today_folder),
            target_date=target_date,
            run_root=Path(run_root),
            run_id=run_id,
            manifest_path=Path(manifest_path_text),
            expected_manifest_sha256=manifest_sha256,
        )
    delivery_attempt = dict(checkpoint.get("delivery_attempt") or {})
    delivery_stage = dict((checkpoint.get("stages") or {}).get("delivery_send") or {})
    delivery_may_have_been_attempted = bool(delivery_attempt or delivery_stage)
    telegram_ledger_missing_after_attempt = bool(
        delivery_may_have_been_attempted
        and clean_text(delivery_state.get("status")).upper()
        == "TELEGRAM_LEDGER_MISSING"
    )
    if telegram_ledger_missing_after_attempt:
        delivery_state = {
            **delivery_state,
            "status": "TELEGRAM_LEDGER_MISSING_AFTER_ATTEMPT",
            "resume_safe": False,
            "uncertain_delivery": True,
        }
    else:
        delivery_state = {
            **delivery_state,
            "resume_safe": not clean_text(delivery_state.get("status")).upper().startswith(
                ("CHECKPOINT_", "PINNED_")
            ),
            "uncertain_delivery": False,
        }
    delivery_completed = bool(delivery_state.get("completed"))
    delivery_request_identity = {
        "target_date": clean_text((delivery_state.get("request_identity") or {}).get("target_date")),
        "ready_set_at": clean_text((delivery_state.get("request_identity") or {}).get("ready_set_at")),
    }
    request_identity_match = bool(
        request_identity["target_date"]
        and request_identity["ready_set_at"]
        and request_identity == delivery_request_identity
    )
    zero_order_path = (
        Path(run_root).expanduser()
        / target_date.isoformat()
        / run_id
        / "zero_order_completion.json"
    )
    zero_order_state = load_json_file(zero_order_path) if run_id else {}
    zero_order_request_identity = {
        "target_date": clean_text(
            (zero_order_state.get("request_identity") or {}).get("target_date")
        ),
        "ready_set_at": clean_text(
            (zero_order_state.get("request_identity") or {}).get("ready_set_at")
        ),
    }
    zero_order_count = zero_order_state.get("required_order_count")
    zero_order_count_is_zero = zero_order_count == 0 or clean_text(
        zero_order_count
    ) == "0"
    checkpoint_required = dict(checkpoint.get("required_orders") or {})
    marker_required_path = clean_text(zero_order_state.get("required_orders_path"))
    marker_required_sha256 = clean_text(zero_order_state.get("required_orders_sha256"))
    checkpoint_required_path = clean_text(checkpoint_required.get("path"))
    checkpoint_required_sha256 = clean_text(checkpoint_required.get("sha256"))
    checkpoint_required_identity = {
        "target_date": clean_text(
            (checkpoint_required.get("request_identity") or {}).get("target_date")
        ),
        "ready_set_at": clean_text(
            (checkpoint_required.get("request_identity") or {}).get("ready_set_at")
        ),
    }
    zero_order_pin_ok = False
    if (
        marker_required_path
        and marker_required_path == checkpoint_required_path
        and marker_required_sha256
        and marker_required_sha256 == checkpoint_required_sha256
        and checkpoint_required_identity == request_identity
    ):
        required_path = Path(marker_required_path).expanduser()
        try:
            required_raw = required_path.read_bytes()
            required_payload = json.loads(required_raw.decode("utf-8"))
        except Exception:
            required_payload = None
        if isinstance(required_payload, dict):
            observed_required_hash = hashlib.sha256(required_raw).hexdigest()
            zero_order_pin_ok = bool(
                observed_required_hash == marker_required_sha256
                and clean_text(required_payload.get("target_date"))
                == target_date.isoformat()
                and dict(required_payload.get("request_identity") or {})
                == request_identity
                and list(required_payload.get("expected_order_ids") or []) == []
                and list(required_payload.get("orders") or []) == []
                and int((required_payload.get("counts") or {}).get("orders") or 0) == 0
            )
    zero_order_completed = bool(
        zero_order_state.get("completed") is True
        and clean_text(zero_order_state.get("mode")) == "apply"
        and clean_text(zero_order_state.get("run_id")) == run_id
        and clean_text(zero_order_state.get("target_date")) == target_date.isoformat()
        and zero_order_count_is_zero
        and zero_order_pin_ok
        and request_identity["target_date"]
        and request_identity["ready_set_at"]
        and zero_order_request_identity == request_identity
    )
    completed = bool(
        target_match
        and status == "OK"
        and (
            (delivery_completed and request_identity_match)
            or zero_order_completed
        )
    )
    return {
        "target_date": target_date.isoformat(),
        "completed": completed,
        "status": status,
        "run_id": run_id,
        "row": row or {},
        "target_match": target_match,
        "delivery_completed": delivery_completed,
        "delivery_may_have_been_attempted": delivery_may_have_been_attempted,
        "delivery_resume_safe": bool(delivery_state.get("resume_safe")),
        "telegram_ledger_missing_after_attempt": telegram_ledger_missing_after_attempt,
        "request_identity": request_identity,
        "delivery_request_identity": delivery_request_identity,
        "request_identity_match": request_identity_match,
        "zero_order_pin_ok": zero_order_pin_ok,
        "completion_kind": (
            "zero_order_noop"
            if zero_order_completed
            else ("delivery" if delivery_completed and request_identity_match else "")
        ),
        "zero_order_completed": zero_order_completed,
        "zero_order_completion_path": str(zero_order_path) if run_id else "",
        "checkpoint_path": str(checkpoint_path),
        "zero_order_request_identity": zero_order_request_identity,
        "delivery_status": clean_text(delivery_state.get("status")),
        "delivery_channel": clean_text(delivery_state.get("channel")),
        "delivery_manifest_count": int(delivery_state.get("manifest_count") or 0),
        "delivery_confirmed_count": int(delivery_state.get("confirmed_count") or 0),
        "delivery_state": delivery_state,
    }
