"""FitPack coordination switches for packing-only surfaces."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "fitpack_coordination.yaml"
STOREB_API_CODE = "STOREB"
STOREB_DISPLAY_NAME = "STORE-B"
EXCLUSION_LOG_LINE = "STOREB_EXCLUDED_FITPACK_CYCLES"

_STOREB_ALIASES = {
    "STOREB",
    "STORE-B",
    "STORE_B",
    "M GROUP",
    "30000002_PP1",
    "30000002_PP2",
}


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_fitpack_store_code(value: Any) -> str:
    """Normalize known STORE-B spellings to the Kaspi API store code."""
    text = _clean(value)
    if not text:
        return ""
    upper = text.upper()
    compact = upper.replace(" ", "").replace("_", "-")
    if upper in _STOREB_ALIASES or compact in {"STOREB", "STORE-B"}:
        return STOREB_API_CODE
    return upper


def is_storeb_store(value: Any) -> bool:
    return normalize_fitpack_store_code(value) == STOREB_API_CODE


def _warn(warn: Callable[[str], None] | None, message: str) -> None:
    if warn is not None:
        warn(message)
    else:
        logging.getLogger(__name__).warning(message)


def load_storeb_packing_excluded(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    *,
    warn: Callable[[str], None] | None = None,
) -> bool:
    """Return True only when the owner-gated flag is explicitly enabled.

    Missing config is the default OFF state. Invalid YAML or invalid value types
    fail safe to not excluded and emit a loud warning.
    """
    path = Path(config_path)
    if not path.exists():
        return False
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _warn(
            warn,
            f"WARNING: {EXCLUSION_LOG_LINE}: failed to parse {path}; "
            f"STORE-B packing exclusion NOT applied: {exc}",
        )
        return False
    if payload is None:
        return False
    if not isinstance(payload, dict):
        _warn(
            warn,
            f"WARNING: {EXCLUSION_LOG_LINE}: {path} must contain a mapping; "
            "STORE-B packing exclusion NOT applied.",
        )
        return False
    raw = payload.get("storeb_packing_excluded", False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    _warn(
        warn,
        f"WARNING: {EXCLUSION_LOG_LINE}: invalid storeb_packing_excluded={raw!r}; "
        "STORE-B packing exclusion NOT applied.",
    )
    return False


def filter_storeb_store_codes(
    stores: Iterable[Any],
    *,
    enabled: bool,
    warn: Callable[[str], None] | None = None,
    context: str = "store scope",
) -> list[Any]:
    if not enabled:
        return list(stores)
    kept: list[Any] = []
    skipped = 0
    for store in stores:
        if is_storeb_store(store):
            skipped += 1
            continue
        kept.append(store)
    if skipped:
        _warn(warn, f"{EXCLUSION_LOG_LINE}: skipped STORE-B in {context}.")
    return kept
