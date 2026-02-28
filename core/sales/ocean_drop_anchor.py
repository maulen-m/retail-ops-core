"""Helpers for resolving the Ocean Drop anchor registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "anchors" / "ocean_drop_sales_anchor.json"


class OceanDropAnchorError(RuntimeError):
    """Raised when Ocean Drop anchor registry is invalid or missing."""


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_ocean_drop_anchor(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    path = Path(registry_path).resolve()
    if not path.exists():
        raise OceanDropAnchorError(f"ocean drop anchor registry missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OceanDropAnchorError(f"invalid ocean drop anchor registry JSON: {path}") from exc

    ocean_drop_path = str(payload.get("ocean_drop_path") or "").strip()
    as_of_end = str(payload.get("as_of_end") or "").strip()
    sha256 = str(payload.get("sha256") or "").strip()
    if not ocean_drop_path:
        raise OceanDropAnchorError("ocean drop anchor registry missing 'ocean_drop_path'")
    if not as_of_end:
        raise OceanDropAnchorError("ocean drop anchor registry missing 'as_of_end'")
    if not sha256:
        raise OceanDropAnchorError("ocean drop anchor registry missing 'sha256'")

    ocean_drop_resolved = Path(ocean_drop_path).expanduser().resolve()
    if not ocean_drop_resolved.exists():
        raise OceanDropAnchorError(f"ocean drop file missing from anchor registry: {ocean_drop_resolved}")
    computed_sha = _sha256_file(ocean_drop_resolved)
    if computed_sha.lower() != sha256.lower():
        raise OceanDropAnchorError(
            "ocean drop anchor sha256 mismatch: "
            f"expected={sha256.lower()} actual={computed_sha.lower()} path={ocean_drop_resolved}"
        )

    payload["ocean_drop_path"] = ocean_drop_path
    payload["as_of_end"] = as_of_end
    payload["sha256"] = sha256.lower()
    payload["ocean_drop_path_resolved"] = str(ocean_drop_resolved)
    payload["sha256_computed"] = computed_sha.lower()
    payload["registry_path"] = str(path)
    return payload


def resolve_ocean_drop_path(
    *,
    explicit_path: Path | None,
    registry_path: Path = DEFAULT_REGISTRY,
) -> Path:
    payload = load_ocean_drop_anchor(registry_path)
    anchor_path = Path(payload["ocean_drop_path_resolved"]).resolve()

    if explicit_path is not None:
        path = explicit_path.resolve()
        if not path.exists():
            raise OceanDropAnchorError(f"ocean drop file missing: {path}")
        if path != anchor_path:
            raise OceanDropAnchorError(
                "explicit ocean drop path does not match locked anchor registry path: "
                f"explicit={path} anchor={anchor_path}"
            )
        return anchor_path

    return anchor_path
