"""Per-store operator state stored inside the Google Ops Board day checkpoint.

The section is additive.  A missing section means every known store is
``PENDING`` and does not change closeout scope.

This module is the only supported writer for ``store_day_states``.  It re-reads
the checkpoint immediately before its atomic replace so a closeout write that
completed before that re-read is preserved.  There is deliberately no shared
file lock with the legacy closeout writer, so a write that lands between the
final re-read and ``os.replace`` can still win or be lost; callers should avoid
concurrent writers and treat the checkpoint as a single-writer control file.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from core.ops.waybill_shipping_obligations import (
    KNOWN_STORE_CODES,
    normalize_store_code,
)
from core.paths import data_path


ALMATY_TZ = ZoneInfo("Asia/Almaty")
SCHEMA_VERSION = 1
VALID_STATES = {
    "PENDING",
    "AUTO_SENT",
    "MANUAL_FULFILLED",
    "POSTPONED",
}
DEFAULT_WORKFLOW_RUN_ROOT = data_path(
    "exports", "google_ops_board", "workflow_runs"
)


def _target_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"invalid target date {value!r}; expected YYYY-MM-DD") from exc


def checkpoint_path_for_date(
    target_date: date | str,
    *,
    workflow_run_root: Path | None = None,
) -> Path:
    resolved_date = _target_date(target_date)
    root = Path(workflow_run_root or DEFAULT_WORKFLOW_RUN_ROOT).expanduser()
    return root / resolved_date.isoformat() / "closeout_checkpoint.json"


def _resolve_checkpoint_path(
    target_date: date | str,
    checkpoint_path: Path | None,
) -> Path:
    if checkpoint_path is not None:
        return Path(checkpoint_path).expanduser()
    return checkpoint_path_for_date(target_date)


def _read_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"day checkpoint is unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"day checkpoint must be a JSON object: {path}")
    return payload


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


def _blank_state() -> dict[str, str]:
    return {
        "state": "PENDING",
        "postponed_to": "",
        "set_by": "",
        "set_at": "",
        "reason": "",
    }


def _normalize_state_record(store: str, raw: Mapping[str, Any]) -> dict[str, str]:
    state = str(raw.get("state") or "PENDING").strip().upper()
    if state not in VALID_STATES:
        raise ValueError(f"unsupported day state {state!r} for store {store}")
    postponed_to = str(raw.get("postponed_to") or "").strip()
    if state == "POSTPONED":
        if not postponed_to:
            raise ValueError(f"POSTPONED state requires postponed_to for store {store}")
        _target_date(postponed_to)
    else:
        postponed_to = ""
    return {
        "state": state,
        "postponed_to": postponed_to,
        "set_by": str(raw.get("set_by") or "").strip(),
        "set_at": str(raw.get("set_at") or "").strip(),
        "reason": str(raw.get("reason") or "").strip(),
    }


def _section_from_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    target_date: date,
    path: Path,
) -> dict[str, Any]:
    checkpoint_date = str(checkpoint.get("target_date") or "").strip()
    if checkpoint_date and checkpoint_date != target_date.isoformat():
        raise ValueError(
            f"day checkpoint target_date mismatch: {checkpoint_date} != "
            f"{target_date.isoformat()}: {path}"
        )
    raw_section = checkpoint.get("store_day_states")
    if raw_section is None:
        return {}
    if not isinstance(raw_section, Mapping):
        raise ValueError("store_day_states must be a JSON object")
    if int(raw_section.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(
            "unsupported store_day_states schema_version="
            f"{raw_section.get('schema_version')!r}"
        )
    raw_stores = raw_section.get("stores")
    if not isinstance(raw_stores, Mapping):
        raise ValueError("store_day_states.stores must be a JSON object")
    stores: dict[str, dict[str, str]] = {}
    for raw_store, raw_record in raw_stores.items():
        store = normalize_store_code(raw_store)
        if store not in KNOWN_STORE_CODES:
            raise ValueError(f"unknown store code in day state: {raw_store!r}")
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"day state for {store} must be a JSON object")
        if store in stores:
            raise ValueError(f"duplicate normalized store code in day state: {store}")
        stores[store] = _normalize_state_record(store, raw_record)
    return {
        "schema_version": SCHEMA_VERSION,
        "stores": dict(sorted(stores.items())),
    }


def load_store_day_states(
    target_date: date | str,
    *,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Load the additive raw section; return ``{}`` when it is absent."""
    resolved_date = _target_date(target_date)
    path = _resolve_checkpoint_path(resolved_date, checkpoint_path)
    return _section_from_checkpoint(
        _read_checkpoint(path),
        target_date=resolved_date,
        path=path,
    )


def effective_store_states(
    target_date: date | str,
    *,
    checkpoint_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Return every known store, defaulting an absent entry to ``PENDING``."""
    section = load_store_day_states(target_date, checkpoint_path=checkpoint_path)
    recorded = dict(section.get("stores") or {})
    return {
        store: dict(recorded.get(store) or _blank_state())
        for store in sorted(KNOWN_STORE_CODES)
    }


def set_store_day_state(
    target_date: date | str,
    store: str,
    state: str,
    *,
    reason: str,
    set_by: str,
    postponed_to: str = "",
    checkpoint_path: Path | None = None,
) -> dict[str, str]:
    """Set one store state without restructuring other checkpoint keys.

    The final re-read narrows, but cannot eliminate, the race with the legacy
    closeout writer because that writer does not share a lock with this module.
    """
    resolved_date = _target_date(target_date)
    normalized_store = normalize_store_code(store)
    if normalized_store not in KNOWN_STORE_CODES:
        raise ValueError(f"unknown store code: {store!r}")
    normalized_state = str(state or "").strip().upper()
    if normalized_state not in VALID_STATES:
        raise ValueError(f"unsupported day state: {state!r}")
    clean_reason = str(reason or "").strip()
    clean_set_by = str(set_by or "").strip()
    if not clean_reason:
        raise ValueError("reason is required")
    if not clean_set_by:
        raise ValueError("set_by is required")
    clean_postponed_to = str(postponed_to or "").strip()
    if normalized_state == "POSTPONED":
        if not clean_postponed_to:
            raise ValueError("POSTPONED state requires postponed_to")
        _target_date(clean_postponed_to)
    else:
        clean_postponed_to = ""

    path = _resolve_checkpoint_path(resolved_date, checkpoint_path)
    # Validate the first view, then re-read immediately before the replace so a
    # completed closeout update is merged rather than overwritten.
    first_checkpoint = _read_checkpoint(path)
    _section_from_checkpoint(
        first_checkpoint,
        target_date=resolved_date,
        path=path,
    )
    latest_checkpoint = _read_checkpoint(path)
    latest_section = _section_from_checkpoint(
        latest_checkpoint,
        target_date=resolved_date,
        path=path,
    )
    record = {
        "state": normalized_state,
        "postponed_to": clean_postponed_to,
        "set_by": clean_set_by,
        "set_at": datetime.now(ALMATY_TZ).isoformat(),
        "reason": clean_reason,
    }
    stores = dict(latest_section.get("stores") or {})
    stores[normalized_store] = record
    payload = dict(latest_checkpoint)
    payload.setdefault("target_date", resolved_date.isoformat())
    payload["store_day_states"] = {
        "schema_version": SCHEMA_VERSION,
        "stores": dict(sorted(stores.items())),
    }
    _atomic_save_json_file(path, payload)
    return dict(record)
