from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.identity_stabilization_common import StatusError
from scripts.validate_identity_replay_anchor import validate_identity_replay_anchor


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_identity_anchor(root: Path, anchor_date: str, *, status: str = "PASS") -> Path:
    anchor = root / anchor_date
    anchor.mkdir(parents=True, exist_ok=True)
    (anchor / "offer_identity_reference.csv").write_text("store_code,sku_id_ksp\nUNIVERSAL,1001\n", encoding="utf-8")
    (anchor / "unresolved_rows.csv").write_text("store_code,sku_id_ksp\n", encoding="utf-8")
    _write_json(
        anchor / "source_manifest.json",
        {
            "generated_at": "2026-03-20T05:18:06",
            "as_of": anchor_date,
            "sources": [
                {
                    "path": "/tmp/universal_snapshot.xlsx",
                    "sha256": "abc",
                    "rows": 1,
                    "snapshot_date": "2026-03-10",
                    "store_code": "UNIVERSAL",
                }
            ],
            "latest_snapshot_date": "2026-03-10",
        },
    )
    _write_json(anchor / "import_report.json", {"status": status, "error_code": "" if status == "PASS" else status})
    _write_json(anchor / "validate_external_snapshot_parity.json", {"status": status, "error_code": "" if status == "PASS" else status})
    _write_json(anchor / "validate_recent_identity_coverage.json", {"status": status, "error_code": "" if status == "PASS" else status})
    _write_json(anchor / "validate_order_entries_freshness.json", {"status": status, "error_code": "" if status == "PASS" else status})
    return anchor


def test_validate_identity_replay_anchor_uses_latest_anchor_on_or_before_as_of(tmp_path: Path) -> None:
    root = tmp_path / "identity"
    _seed_identity_anchor(root, "2026-03-08")
    _seed_identity_anchor(root, "2026-03-09")

    report = validate_identity_replay_anchor(
        as_of="2026-03-19",
        identity_root=root,
        output_root=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["anchor_date"] == "2026-03-09"
    assert report["latest_snapshot_date"] == "2026-03-10"
    assert report["snapshot_lag_days"] == 9


def test_validate_identity_replay_anchor_skips_incomplete_newer_anchor(tmp_path: Path) -> None:
    root = tmp_path / "identity"
    newer = root / "2026-03-19"
    newer.mkdir(parents=True, exist_ok=True)
    _write_json(newer / "validate_reference_freshness.json", {"status": "PASS", "error_code": ""})
    _seed_identity_anchor(root, "2026-03-09")

    report = validate_identity_replay_anchor(
        as_of="2026-03-19",
        identity_root=root,
        output_root=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["anchor_date"] == "2026-03-09"
    assert report["latest_snapshot_date"] == "2026-03-10"


def test_validate_identity_replay_anchor_fails_when_required_anchor_file_missing(tmp_path: Path) -> None:
    root = tmp_path / "identity"
    anchor = _seed_identity_anchor(root, "2026-03-09")
    (anchor / "validate_recent_identity_coverage.json").unlink()

    with pytest.raises(StatusError, match="IDENTITY_REPLAY_ANCHOR_MISSING"):
        validate_identity_replay_anchor(
            as_of="2026-03-19",
            identity_root=root,
            output_root=tmp_path / "out",
            strict=True,
        )


def test_validate_identity_replay_anchor_fails_when_anchor_status_not_pass(tmp_path: Path) -> None:
    root = tmp_path / "identity"
    _seed_identity_anchor(root, "2026-03-09", status="IDENTITY_COVERAGE_FAIL")

    with pytest.raises(StatusError, match="IDENTITY_REPLAY_ANCHOR_FAIL"):
        validate_identity_replay_anchor(
            as_of="2026-03-19",
            identity_root=root,
            output_root=tmp_path / "out",
            strict=True,
        )
