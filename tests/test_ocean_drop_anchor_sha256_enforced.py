from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.sales.ocean_drop_anchor import OceanDropAnchorError, load_ocean_drop_anchor


def test_anchor_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    ocean = tmp_path / "ocean.csv"
    ocean.write_text("order_id,store_code\n1,ACMEWEAR\n", encoding="utf-8")
    correct_sha = hashlib.sha256(ocean.read_bytes()).hexdigest()

    registry = tmp_path / "anchor.json"
    registry.write_text(
        json.dumps(
            {
                "ocean_drop_path": str(ocean),
                "as_of_end": "2026-02-26",
                "sha256": correct_sha,
            }
        ),
        encoding="utf-8",
    )
    load_ocean_drop_anchor(registry)

    ocean.write_text("order_id,store_code\n1,ACMEWEAR\n2,STOREB\n", encoding="utf-8")

    with pytest.raises(OceanDropAnchorError, match="sha256 mismatch"):
        load_ocean_drop_anchor(registry)
