from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from scripts.verify_kaspi_pricelist_hash import REQUIRED_COLUMNS, build_pricelist_hash_report


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_empty_manifest_is_armed(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    web_root = tmp_path / "wa"
    web_root.mkdir()
    _write_manifest(manifest, [])

    report = build_pricelist_hash_report(
        manifest_path=manifest,
        web_auto_root=web_root,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "ARMED"
    assert report["first_applied_upload_required"] is True
    assert report["ok"] is True


def test_planned_row_with_upload_and_rollback_hashes_is_armed(tmp_path: Path) -> None:
    web_root = tmp_path / "wa"
    upload = web_root / "runs" / "upload.xlsx"
    rollback = web_root / "runs" / "rollback.xlsx"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"upload")
    rollback.write_bytes(b"rollback")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(
        manifest,
        [
            {
                "upload_id": "UP-1",
                "upload_stage": "planned",
                "store_name": "ACMEWEAR",
                "upload_file": "runs/upload.xlsx",
                "rollback_file": "runs/rollback.xlsx",
                "post_readback_file": "",
                "expected_upload_sha256": _sha(upload),
                "expected_rollback_sha256": _sha(rollback),
                "expected_post_readback_sha256": "",
                "upload_applied_at": "",
                "owner_decision_id": "OD-TEST",
                "gate_id": "G-WA-02",
                "notes": "test",
            }
        ],
    )

    report = build_pricelist_hash_report(
        manifest_path=manifest,
        web_auto_root=web_root,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "ARMED"
    assert report["planned_row_count"] == 1
    assert report["applied_row_count"] == 0


def test_applied_row_with_readback_hashes_is_green(tmp_path: Path) -> None:
    web_root = tmp_path / "wa"
    upload = web_root / "runs" / "upload.xlsx"
    rollback = web_root / "runs" / "rollback.xlsx"
    readback = web_root / "runs" / "readback.xlsx"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"upload")
    rollback.write_bytes(b"rollback")
    readback.write_bytes(b"readback")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(
        manifest,
        [
            {
                "upload_id": "UP-2",
                "upload_stage": "applied",
                "store_name": "ACMEWEAR",
                "upload_file": "runs/upload.xlsx",
                "rollback_file": "runs/rollback.xlsx",
                "post_readback_file": "runs/readback.xlsx",
                "expected_upload_sha256": _sha(upload),
                "expected_rollback_sha256": _sha(rollback),
                "expected_post_readback_sha256": _sha(readback),
                "upload_applied_at": "2026-06-18T12:00:00+05:00",
                "owner_decision_id": "OD-TEST",
                "gate_id": "G-WA-02",
                "notes": "test",
            }
        ],
    )

    report = build_pricelist_hash_report(
        manifest_path=manifest,
        web_auto_root=web_root,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "GREEN"
    assert report["applied_row_count"] == 1


def test_hash_mismatch_is_red(tmp_path: Path) -> None:
    web_root = tmp_path / "wa"
    upload = web_root / "runs" / "upload.xlsx"
    rollback = web_root / "runs" / "rollback.xlsx"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"upload")
    rollback.write_bytes(b"rollback")
    manifest = tmp_path / "manifest.csv"
    _write_manifest(
        manifest,
        [
            {
                "upload_id": "UP-3",
                "upload_stage": "planned",
                "store_name": "ACMEWEAR",
                "upload_file": "runs/upload.xlsx",
                "rollback_file": "runs/rollback.xlsx",
                "post_readback_file": "",
                "expected_upload_sha256": "bad",
                "expected_rollback_sha256": _sha(rollback),
                "expected_post_readback_sha256": "",
                "upload_applied_at": "",
                "owner_decision_id": "OD-TEST",
                "gate_id": "G-WA-02",
                "notes": "test",
            }
        ],
    )

    report = build_pricelist_hash_report(
        manifest_path=manifest,
        web_auto_root=web_root,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "RED"
    assert report["ok"] is False
    assert report["row_errors"]
