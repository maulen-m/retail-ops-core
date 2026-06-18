from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORES_CONFIG = PROJECT_ROOT / "config" / "stores.yaml"
DEFAULT_KASPI_STORES_CONFIG = PROJECT_ROOT / "config" / "kaspi_stores.yaml"


def load_active_store_codes(config_path: Path = DEFAULT_STORES_CONFIG) -> list[str]:
    payload: Any = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        raise RuntimeError(f"invalid stores config format: {config_path}")

    active_codes: list[str] = []
    for code, meta in stores.items():
        if not isinstance(meta, dict):
            continue
        active = bool(meta.get("active", True))
        if active:
            active_codes.append(str(code).upper())
    if not active_codes:
        raise RuntimeError(f"no active stores configured in {config_path}")
    return active_codes


def load_sync_enabled_kaspi_store_codes(
    config_path: Path = DEFAULT_KASPI_STORES_CONFIG,
) -> list[str]:
    payload: Any = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        raise RuntimeError(f"invalid Kaspi stores config format: {config_path}")

    rows: list[tuple[int, str]] = []
    for code, meta in stores.items():
        if not isinstance(meta, dict):
            continue
        if bool(meta.get("sync_enabled", True)):
            rows.append((int(meta.get("priority", 99)), str(code).upper()))
    rows.sort(key=lambda item: (item[0], item[1]))
    if not rows:
        raise RuntimeError(f"no sync-enabled Kaspi stores configured in {config_path}")
    return [code for _, code in rows]
