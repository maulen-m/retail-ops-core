from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
import subprocess
import sys

from scripts.prepare_line31_multi_creative_mapping import build_mapping
from scripts.validate_line31_final_creative_mapping import DEFAULT_TEMPLATE, validate_mapping

SYNTHETIC_APPROVAL = Path("tests/fixtures/line31/SYNTHETIC_APPROVAL_PHRASE.txt")


def _write_asset_manifest(tmp_path: Path) -> Path:
    assets = []
    for creative_id, duration in (
        ("line31_cw_ann_vse_eshe_v1", 16.267),
        ("line31_cw_ann_dumala_v1", 14.967),
        ("line31_cw_mulena_madina_v1", 15.867),
    ):
        video = tmp_path / f"{creative_id}.mp4"
        thumb = tmp_path / f"{creative_id}.jpg"
        video.write_bytes(f"video-{creative_id}".encode())
        thumb.write_bytes(f"thumb-{creative_id}".encode())
        assets.append(
            {
                "creative_id": creative_id,
                "local_video_path": str(video),
                "thumbnail_path": str(thumb),
                "duration_seconds": duration,
                "utm_content": creative_id,
                "utm_placement": "reels",
                "primary_cta": "open_line31_landing",
                "language": "ru",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "campaign_shape": {
                    "adset_count": 1,
                    "ad_count": 3,
                    "daily_budget_kzt": 15000,
                    "hard_cap_kzt": 20000,
                },
                "landing_cta_priority": [
                    "starry_black",
                    "wib_mixed_color_set",
                    "blue_misty",
                    "olive_green",
                    "remaining_colors",
                    "espresso_last",
                ],
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _args(manifest: Path, **overrides: object) -> Namespace:
    values = {
        "template": DEFAULT_TEMPLATE,
        "asset_manifest": manifest,
        "landing_url": "https://acmewear.pro/line31",
        "kaspi_marketplace_cta_url": (
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/"
        ),
        "final_asset_base_url": "",
        "utm_placement": "reels",
        "aspect_ratio": "9:16",
        "language": "ru",
        "primary_cta": "open_line31_landing",
        "owner_notes": "",
        "approval_phrase_path": str(SYNTHETIC_APPROVAL),
        "creative_ready_declared": True,
        "owner_approved": False,
        "approval_evidence_file": None,
        "tracking_qa_evidence_file": None,
        "output": None,
        "overwrite": False,
        "json": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_builds_three_creative_rows_from_asset_manifest(tmp_path: Path) -> None:
    manifest = _write_asset_manifest(tmp_path)

    mapping = build_mapping(_args(manifest))

    assert mapping["creative_ready_declaration_received"] is True
    assert mapping["publish_authority"]["approved"] is False
    assert mapping["multi_asset_source_manifest"]["assets_count"] == 3
    assert len(mapping["assets"]) == 3
    assert {row["creative_id"] for row in mapping["assets"]} == {
        "line31_cw_ann_vse_eshe_v1",
        "line31_cw_ann_dumala_v1",
        "line31_cw_mulena_madina_v1",
    }
    assert all("utm_campaign=line31_countrywide" in row["landing_url"] for row in mapping["assets"])
    assert all(row["final_asset_uri"].endswith(".mp4") for row in mapping["assets"])


def test_pending_multi_mapping_is_hash_valid_but_not_publish_ready(tmp_path: Path) -> None:
    manifest = _write_asset_manifest(tmp_path)
    output = tmp_path / "mapping.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_multi_creative_mapping.py",
            "--asset-manifest",
            str(manifest),
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--creative-ready-declared",
            "--output",
            str(output),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["assets_count"] == 3
    assert report["strict_publish_ready"] is False
    result = validate_mapping(output)
    assert not result.ok
    assert result.metrics["local_video_hashes_checked"] == 3
    assert result.metrics["local_thumbnail_hashes_checked"] == 3
    assert any("publish_authority.approved" in error for error in result.errors)
    assert any("tracking_redirect_qa.gate" in error for error in result.errors)


def test_duplicate_creative_ids_are_rejected(tmp_path: Path) -> None:
    manifest = _write_asset_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["assets"][1]["creative_id"] = payload["assets"][0]["creative_id"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_multi_creative_mapping.py",
            "--asset-manifest",
            str(manifest),
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "duplicates" in completed.stderr
