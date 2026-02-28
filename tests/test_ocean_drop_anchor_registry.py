from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.sales.ocean_drop_anchor import (
    OceanDropAnchorError,
    load_ocean_drop_anchor,
    resolve_ocean_drop_path,
)


def test_load_ocean_drop_anchor_requires_required_fields(tmp_path: Path) -> None:
    registry = tmp_path / "anchor.json"
    registry.write_text(json.dumps({"ocean_drop_path": "x.csv"}), encoding="utf-8")

    with pytest.raises(OceanDropAnchorError, match="as_of_end"):
        load_ocean_drop_anchor(registry)


def test_resolve_ocean_drop_path_uses_registry_when_explicit_missing(tmp_path: Path) -> None:
    ocean = tmp_path / "ocean.csv"
    ocean.write_text("a,b\n1,2\n", encoding="utf-8")
    sha = hashlib.sha256(ocean.read_bytes()).hexdigest()
    registry = tmp_path / "anchor.json"
    registry.write_text(
        json.dumps(
            {
                "ocean_drop_path": str(ocean),
                "as_of_end": "2026-02-26",
                "sha256": sha,
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_ocean_drop_path(explicit_path=None, registry_path=registry)
    assert resolved == ocean.resolve()
