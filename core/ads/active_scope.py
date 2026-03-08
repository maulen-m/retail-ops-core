from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADS_ACTIVE_SCOPE_CONFIG = PROJECT_ROOT / "config" / "ads_active_scope.yaml"


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _normalize_store(value: str | None) -> str:
    return str(value or "").strip().upper()


def _load_scope_payload(config_path: Path) -> dict[str, Any]:
    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"ads active scope config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"ads active scope config must be a mapping: {path}")
    return payload


def _match_window(windows: list[dict[str, Any]], on_date: date) -> dict[str, Any] | None:
    matched: dict[str, Any] | None = None
    matched_start: date | None = None
    for raw in windows:
        if not isinstance(raw, dict):
            continue
        start_raw = raw.get("start")
        if not start_raw:
            continue
        start_date = _coerce_date(str(start_raw))
        end_raw = raw.get("end")
        end_date = _coerce_date(str(end_raw)) if end_raw else None
        if start_date <= on_date and (end_date is None or on_date <= end_date):
            if matched is None or start_date >= (matched_start or start_date):
                matched = raw
                matched_start = start_date
    return matched


def resolve_store_scope_on(
    store_code: str,
    on_date: date | str,
    *,
    config_path: Path = DEFAULT_ADS_ACTIVE_SCOPE_CONFIG,
) -> dict[str, Any]:
    payload = _load_scope_payload(config_path)
    stores = payload.get("stores") or {}
    default_active = bool(payload.get("default_active", False))
    target_store = _normalize_store(store_code)
    effective_date = _coerce_date(on_date)

    store_payload = stores.get(target_store) or {}
    windows = store_payload.get("windows") or []
    matched = _match_window(windows, effective_date)
    if matched is None:
        return {
            "store_code": target_store,
            "on_date": effective_date.isoformat(),
            "active": default_active,
            "reason": "default_active" if default_active else "default_inactive",
        }
    return {
        "store_code": target_store,
        "on_date": effective_date.isoformat(),
        "active": bool(matched.get("active", False)),
        "reason": str(matched.get("reason") or "").strip() or "window_rule",
        "start": str(matched.get("start") or ""),
        "end": str(matched.get("end") or ""),
    }


def is_store_active_on(
    store_code: str,
    on_date: date | str,
    *,
    config_path: Path = DEFAULT_ADS_ACTIVE_SCOPE_CONFIG,
) -> bool:
    return bool(resolve_store_scope_on(store_code, on_date, config_path=config_path)["active"])


def resolve_active_store_codes(
    on_date: date | str,
    *,
    config_path: Path = DEFAULT_ADS_ACTIVE_SCOPE_CONFIG,
) -> set[str]:
    payload = _load_scope_payload(config_path)
    stores = payload.get("stores") or {}
    effective_date = _coerce_date(on_date)
    out: set[str] = set()
    for store_code in stores:
        if is_store_active_on(str(store_code), effective_date, config_path=config_path):
            out.add(_normalize_store(str(store_code)))
    return out
