from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.identity_stabilization_common import StatusError
from scripts.validate_external_snapshot_parity import validate_external_snapshot_parity


def _write_reference_csv(path: Path, *, unresolved_universal: int, unresolved_storeb: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx in range(5):
        rows.append(
            {
                "store_code": "UNIVERSAL",
                "effective_sku_key": "" if idx < unresolved_universal else f"U{idx}",
                "mapping_status": "new",
                "identity_status": "matched",
            }
        )
    for idx in range(5):
        rows.append(
            {
                "store_code": "STOREB",
                "effective_sku_key": "" if idx < unresolved_storeb else f"M{idx}",
                "mapping_status": "new",
                "identity_status": "matched",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def test_validate_external_snapshot_parity_pass(tmp_path: Path) -> None:
    reference_csv = tmp_path / "out" / "2026-03-04" / "offer_identity_reference.csv"
    _write_reference_csv(reference_csv, unresolved_universal=1, unresolved_storeb=1)
    baseline_json = tmp_path / "baseline.json"
    baseline_json.write_text(
        json.dumps(
            {
                "web_snapshot_summary": [
                    {"store": "UNIVERSAL", "missing_effective_sku_key": 2},
                    {"store": "STOREB", "missing_effective_sku_key": 2},
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    (snapshot_root / "universal_snapshot_2026-03-03.xlsx").write_text("ok", encoding="utf-8")
    (snapshot_root / "store-b_snapshot_2026-03-03.xlsx").write_text("ok", encoding="utf-8")

    report = validate_external_snapshot_parity(
        as_of=date(2026, 3, 4),
        reference_csv=reference_csv,
        baseline_json=baseline_json,
        snapshot_root=snapshot_root,
        output_root=tmp_path / "validation",
        strict=True,
        max_age_days=3,
    )
    assert report["status"] == "PASS"


def test_validate_external_snapshot_parity_fails_when_unresolved_exceeds_baseline(tmp_path: Path) -> None:
    reference_csv = tmp_path / "out" / "2026-03-04" / "offer_identity_reference.csv"
    _write_reference_csv(reference_csv, unresolved_universal=4, unresolved_storeb=1)
    baseline_json = tmp_path / "baseline.json"
    baseline_json.write_text(
        json.dumps({"web_snapshot_summary": [{"store": "UNIVERSAL", "missing_effective_sku_key": 2}]}),
        encoding="utf-8",
    )
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    (snapshot_root / "universal_snapshot_2026-03-03.xlsx").write_text("ok", encoding="utf-8")
    (snapshot_root / "store-b_snapshot_2026-03-03.xlsx").write_text("ok", encoding="utf-8")

    with pytest.raises(StatusError, match="IDENTITY_COVERAGE_FAIL"):
        validate_external_snapshot_parity(
            as_of=date(2026, 3, 4),
            reference_csv=reference_csv,
            baseline_json=baseline_json,
            snapshot_root=snapshot_root,
            output_root=tmp_path / "validation",
            strict=True,
            max_age_days=3,
        )
