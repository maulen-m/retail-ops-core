from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
import subprocess
import sys

from scripts.prepare_line31_final_creative_mapping import build_mapping
from scripts.validate_line31_final_creative_mapping import (
    required_owner_approval_phrase,
    validate_mapping,
)


def _base_command(video: Path, thumbnail: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/prepare_line31_final_creative_mapping.py",
        "--creative-id",
        "line31_countrywide_v1",
        "--video",
        str(video),
        "--thumbnail",
        str(thumbnail),
        "--final-asset-uri",
        "https://cdn.acmewear.kz/line31/final.mp4",
        "--landing-url",
        "https://acmewear.pro/line31?utm_source=meta",
        "--kaspi-marketplace-cta-url",
        "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
        "--duration-seconds",
        "18",
        "--utm-placement",
        "reels",
    ]


def _write_media(tmp_path: Path) -> tuple[Path, Path]:
    video = tmp_path / "final.mp4"
    thumbnail = tmp_path / "thumb.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    return video, thumbnail


def _approval_evidence(tmp_path: Path) -> Path:
    phrase = required_owner_approval_phrase(
        Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_publish_intake_and_approval.md"
        )
    )
    evidence = tmp_path / "owner_approval_evidence.md"
    evidence.write_text(
        f"# Owner Approval Evidence\n\nRecorded: 2026-06-01T16:00:00+05:00\n\n{phrase}\n",
        encoding="utf-8",
    )
    return evidence


def _tracking_qa_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "tracking_redirect_qa.json"
    evidence.write_text(
        json.dumps(
            {
                "gate": "GREEN",
                "qa_scope": "live_postdeploy",
                "target_base_url": "https://acmewear.pro",
                "root": {
                    "status": 200,
                    "tracked_params_in_runtime_config": [
                        "utm_source",
                        "utm_medium",
                        "utm_campaign",
                        "utm_content",
                        "utm_placement",
                    ],
                    "missing_expected_utm_params": [],
                },
                "browser_events": [
                    {"event_name": "PageView", "api_status": 204, "stored": True},
                    {"event_name": "ViewContent", "api_status": 204, "stored": True},
                    {"event_name": "ColorSelect", "api_status": 204, "stored": True},
                    {"event_name": "KaspiClick", "api_status": 204, "stored": True},
                    {"event_name": "HighIntentKaspiClick", "api_status": 204, "stored": True},
                ],
                "redirect_routes": [
                    {
                        "http_status": 302,
                        "destination_route_matches_registry": True,
                        "tracked_utm_keys_missing_or_wrong": [],
                        "landing_color_preserved": True,
                        "landing_source_preserved": True,
                    }
                ],
                "fallback_route": {
                    "http_status": 302,
                    "tracked_utm_keys_missing_or_wrong": [],
                    "landing_color_preserved": True,
                    "landing_source_preserved": True,
                },
                "fail_closed_checks": {
                    "browser_spoofed_kaspi_redirect_status": 400,
                    "fake_purchase_status": 400,
                    "unknown_color_status": 404,
                },
                "no_fake_ecommerce_events": {
                    "fake_purchase_rejected": True,
                    "forbidden_events_checked": [
                        "Purchase",
                        "AddToCart",
                        "InitiateCheckout",
                        "AddPaymentInfo",
                    ],
                },
                "failure_summary": [],
            }
        ),
        encoding="utf-8",
    )
    return evidence


def test_prepare_mapping_prints_json_without_writing_output(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)
    output = tmp_path / "mapping.json"

    completed = subprocess.run(
        _base_command(video, thumbnail),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not output.exists()
    mapping = json.loads(completed.stdout)
    assert mapping["assets"][0]["creative_id"] == "line31_countrywide_v1"
    assert mapping["assets"][0]["utm_content"] == "line31_countrywide_v1"
    assert mapping["assets"][0]["utm_placement"] == "reels"
    assert "utm_medium=paid_social" in mapping["assets"][0]["landing_url"]
    assert "utm_campaign=line31_countrywide" in mapping["assets"][0]["landing_url"]
    assert mapping["publish_authority"]["approved"] is False


def test_prepare_mapping_detects_asset_dir_inputs(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()
    video = asset_dir / "line31_final.mp4"
    thumbnail = asset_dir / "line31_thumb.jpg"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_final_creative_mapping.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31?utm_source=meta",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--creative-ready-declared",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    mapping = json.loads(completed.stdout)
    asset = mapping["assets"][0]
    assert asset["local_file_path"] == str(video.resolve())
    assert asset["thumbnail_path_or_uri"] == str(thumbnail.resolve())


def test_prepare_mapping_rejects_ambiguous_asset_dir(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()
    (asset_dir / "line31_final_a.mp4").write_bytes(b"fake-video-a")
    (asset_dir / "line31_final_b.webm").write_bytes(b"fake-video-b")
    (asset_dir / "line31_thumb.png").write_bytes(b"fake-thumbnail")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_final_creative_mapping.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31?utm_source=meta",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "expected exactly one video file" in completed.stderr


def test_prepare_mapping_writes_strict_ready_file_when_owner_approved(
    tmp_path: Path,
) -> None:
    video, thumbnail = _write_media(tmp_path)
    approval_evidence = _approval_evidence(tmp_path)
    tracking_evidence = _tracking_qa_evidence(tmp_path)
    output = tmp_path / "mapping.json"

    completed = subprocess.run(
        [
            *_base_command(video, thumbnail),
            "--creative-ready-declared",
            "--owner-approved",
            "--approval-evidence-file",
            str(approval_evidence),
            "--tracking-qa-evidence-file",
            str(tracking_evidence),
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
    assert report["strict_publish_ready"] is True
    assert output.exists()
    result = validate_mapping(output)
    assert result.ok, result.errors
    assert result.metrics["local_video_hashes_checked"] == 1
    assert result.metrics["local_thumbnail_hashes_checked"] == 1
    assert result.metrics["approval_evidence_checked"] == 1
    assert result.metrics["tracking_redirect_qa_checked"] == 1


def test_prepare_mapping_refuses_to_overwrite_without_flag(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)
    output = tmp_path / "mapping.json"
    output.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [*_base_command(video, thumbnail), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "pass --overwrite" in completed.stderr


def test_prepare_mapping_owner_approval_requires_creative_ready(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)

    completed = subprocess.run(
        [*_base_command(video, thumbnail), "--owner-approved"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--owner-approved requires --creative-ready-declared" in completed.stderr


def test_prepare_mapping_owner_approval_requires_approval_evidence(
    tmp_path: Path,
) -> None:
    video, thumbnail = _write_media(tmp_path)

    completed = subprocess.run(
        [*_base_command(video, thumbnail), "--creative-ready-declared", "--owner-approved"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--owner-approved requires --approval-evidence-file" in completed.stderr


def test_prepare_mapping_owner_approval_requires_tracking_qa(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)
    approval_evidence = _approval_evidence(tmp_path)

    completed = subprocess.run(
        [
            *_base_command(video, thumbnail),
            "--creative-ready-declared",
            "--owner-approved",
            "--approval-evidence-file",
            str(approval_evidence),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--owner-approved requires --tracking-qa-evidence-file" in completed.stderr


def test_prepare_mapping_rejects_non_exact_approval_evidence(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)
    tracking_evidence = _tracking_qa_evidence(tmp_path)
    approval_evidence = tmp_path / "bad_approval.md"
    approval_evidence.write_text("I approve something else.\n", encoding="utf-8")

    completed = subprocess.run(
        [
            *_base_command(video, thumbnail),
            "--creative-ready-declared",
            "--owner-approved",
            "--approval-evidence-file",
            str(approval_evidence),
            "--tracking-qa-evidence-file",
            str(tracking_evidence),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "exact required owner approval phrase" in completed.stderr


def test_prepare_mapping_build_function_rejects_missing_video(tmp_path: Path) -> None:
    video, thumbnail = _write_media(tmp_path)
    video.unlink()

    args = Namespace(
        template=Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_asset_mapping_template.json"
        ),
        creative_id="line31_countrywide_v1",
        asset_dir=None,
        video=video,
        thumbnail=thumbnail,
        final_asset_uri="https://cdn.acmewear.kz/line31/final.mp4",
        landing_url="https://acmewear.pro/line31",
        kaspi_marketplace_cta_url="https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
        duration_seconds=18,
        utm_placement="reels",
        utm_content=None,
        aspect_ratio="9:16",
        language="ru",
        primary_cta="Shop now",
        owner_notes="",
        approval_phrase_path=(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_publish_intake_and_approval.md"
        ),
        approval_evidence_file=None,
        tracking_qa_evidence_file=None,
        creative_ready_declared=False,
        owner_approved=False,
    )

    try:
        build_mapping(args)
    except ValueError as exc:
        assert "video does not exist" in str(exc)
    else:
        raise AssertionError("missing video should fail")
