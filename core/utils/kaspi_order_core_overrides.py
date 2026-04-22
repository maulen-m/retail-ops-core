from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from core.paths import PROJECT_ROOT


DEFAULT_ORDER_CORE_OVERRIDES_PATH = PROJECT_ROOT / "config" / "kaspi_order_name_core_overrides.yaml"
ORDER_CORE_OVERRIDES_ENV = "AB_KASPI_ORDER_NAME_CORE_OVERRIDES"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def resolve_order_core_overrides_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    env_value = os.environ.get(ORDER_CORE_OVERRIDES_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_ORDER_CORE_OVERRIDES_PATH


def load_order_name_core_overrides(path: Path | None = None) -> dict[str, str]:
    target = resolve_order_core_overrides_path(path)
    if not target.exists():
        return {}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw_overrides = data.get("overrides", data)
    if not isinstance(raw_overrides, dict):
        return {}

    result: dict[str, str] = {}
    for raw_order_id, spec in raw_overrides.items():
        order_id = _clean_text(raw_order_id)
        if not order_id:
            continue
        if isinstance(spec, dict):
            if spec.get("active") is False:
                continue
            core = _clean_text(spec.get("kaspi_name_core") or spec.get("core"))
        else:
            core = _clean_text(spec)
        if core:
            result[order_id] = core
    return result
