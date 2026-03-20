from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.validate_playwright_archive_downloads import (
    PlaywrightArchiveDownloadValidationError,
    validate_playwright_archive_downloads,
)
from scripts.webui_archive_truth_utils import compute_sha256


def _write_stores(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"stores": {"ACMEWEAR": {"enabled": True}}}),
        encoding="utf-8",
    )


def _write_run(root: Path, *, include_store: bool) -> Path:
    run = root / "run1"
    run.mkdir(parents=True, exist_ok=True)
    copied = run / "ACMEWEAR.csv"
    copied.write_text("id\n1\n", encoding="utf-8")
    manifest = {
        "run_id": "run1",
        "mode": "import-existing",
        "store_results": (
            [
                {
                    "store_code": "ACMEWEAR",
                    "status": "PASS",
                    "copied_file": str(copied.resolve()),
                    "sha256": compute_sha256(copied),
                }
            ]
            if include_store
            else []
        ),
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run


def _write_subset_run(root: Path) -> Path:
    run = root / "run_subset"
    run.mkdir(parents=True, exist_ok=True)
    copied = run / "ACMEWEAR.csv"
    copied.write_text("id\n1\n", encoding="utf-8")
    manifest = {
        "run_id": "run_subset",
        "mode": "live-download",
        "target_stores": ["ACMEWEAR"],
        "store_results": [
            {
                "store_code": "ACMEWEAR",
                "status": "PASS",
                "copied_file": str(copied.resolve()),
                "sha256": compute_sha256(copied),
            }
        ],
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run


def test_validate_playwright_archive_downloads_pass(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    run = _write_run(tmp_path, include_store=True)

    report = validate_playwright_archive_downloads(
        run_id=str(run),
        output_root=tmp_path,
        stores_config=stores,
        strict=True,
    )
    assert report["status"] == "PASS"


def test_validate_playwright_archive_downloads_strict_fail_when_store_missing(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    run = _write_run(tmp_path, include_store=False)

    with pytest.raises(PlaywrightArchiveDownloadValidationError):
        validate_playwright_archive_downloads(
            run_id=str(run),
            output_root=tmp_path,
            stores_config=stores,
            strict=True,
        )


def test_validate_playwright_archive_downloads_subset_target_passes(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    run = _write_subset_run(tmp_path)

    report = validate_playwright_archive_downloads(
        run_id=str(run),
        output_root=tmp_path,
        stores_config=stores,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["target_stores"] == ["ACMEWEAR"]
