from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_status(path: Path, asset_dir: Path, approval_text_file: Path | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T21:00:00+05:00",
                "latest_drop_intake": {
                    "dir": str(asset_dir.parent),
                    "asset_dir": str(asset_dir),
                    "approval_text_file": str(approval_text_file or ""),
                    "checklist_path": str(asset_dir.parent / "FINAL_CREATIVE_DROP_CHECKLIST.json"),
                    "manifest": str(
                        asset_dir.parent / "line31_final_creative_drop_intake_manifest.json"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )


def _write_assets(asset_dir: Path) -> tuple[Path, Path]:
    asset_dir.mkdir(parents=True)
    video = asset_dir / "line31_final.mp4"
    thumbnail = asset_dir / "line31_thumb.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    return video, thumbnail


def test_current_drop_validator_reads_latest_status_pointer(tmp_path: Path) -> None:
    asset_dir = tmp_path / "drop" / "final_assets"
    asset_dir.mkdir(parents=True)
    status_path = tmp_path / "LINE31_LAUNCH_CURRENT_STATUS.json"
    _write_status(status_path, asset_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_current_final_creative_drop.py",
            "--status-path",
            str(status_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "NOT_READY"
    assert payload["latest_drop_intake"]["asset_dir"] == str(asset_dir)
    assert payload["current_status_path"] == str(status_path.resolve())
    assert any(
        "expected exactly one video" in error for error in payload["validator"]["errors"]
    )
    assert payload["no_external_writes_performed"] is True


def test_current_drop_validator_accepts_assets_and_real_urls(tmp_path: Path) -> None:
    asset_dir = tmp_path / "drop" / "final_assets"
    video, thumbnail = _write_assets(asset_dir)
    status_path = tmp_path / "LINE31_LAUNCH_CURRENT_STATUS.json"
    _write_status(status_path, asset_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_current_final_creative_drop.py",
            "--status-path",
            str(status_path),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "ASSETS_AND_URLS_READY_PENDING_APPROVAL"
    assert payload["validator"]["resolved_video"] == str(video.resolve())
    assert payload["validator"]["resolved_thumbnail"] == str(thumbnail.resolve())
    assert payload["validator"]["assets_ready"] is True
    assert payload["validator"]["approval_ready"] is False


def test_current_drop_validator_uses_current_approval_file_when_required(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "drop" / "final_assets"
    _write_assets(asset_dir)
    approval_text_file = tmp_path / "drop" / "approval" / "approval.txt"
    approval_text_file.parent.mkdir(parents=True)
    approval_text_file.write_text("placeholder, not the exact owner phrase\n", encoding="utf-8")
    status_path = tmp_path / "LINE31_LAUNCH_CURRENT_STATUS.json"
    _write_status(status_path, asset_dir, approval_text_file)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_current_final_creative_drop.py",
            "--status-path",
            str(status_path),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--use-current-approval-file",
            "--require-approval",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "NOT_READY"
    assert payload["effective_approval_text_file"] == str(approval_text_file)
    assert (
        payload["validator"]["approval_error"]
        == "approval evidence file does not contain the exact required owner approval phrase"
    )
