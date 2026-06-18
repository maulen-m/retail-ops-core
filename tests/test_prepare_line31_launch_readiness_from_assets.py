from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase


def _write_media(tmp_path: Path) -> tuple[Path, Path]:
    video = tmp_path / "final.mp4"
    thumbnail = tmp_path / "thumb.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    return video, thumbnail


def _base_command(tmp_path: Path, *, run_id: str) -> tuple[list[str], Path, Path]:
    video, thumbnail = _write_media(tmp_path)
    return (
        [
            sys.executable,
            "scripts/prepare_line31_launch_readiness_from_assets.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--video",
            str(video),
            "--thumbnail",
            str(thumbnail),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--output-mapping",
            str(tmp_path / "mapping.json"),
            "--preflight-output-root",
            str(tmp_path),
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--approval-output-dir",
            str(tmp_path / "approvals"),
            "--run-id",
            run_id,
            "--json",
        ],
        video,
        thumbnail,
    )


def _approval_text(tmp_path: Path) -> Path:
    phrase = required_owner_approval_phrase(
        Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_publish_intake_and_approval.md"
        )
    )
    approval = tmp_path / "approval.txt"
    approval.write_text(
        f"Owner approval captured for launch-day test.\n\n{phrase}\n",
        encoding="utf-8",
    )
    return approval


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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prepare_launch_readiness_creative_ready_pending_approval(tmp_path: Path) -> None:
    command, _, _ = _base_command(tmp_path, run_id="pending")
    completed = subprocess.run(
        [*command, "--creative-ready-declared"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    assert payload["ready_to_publish"] is False
    assert payload["pending_ok"] is True
    assert payload["strict_ok"] is False
    assert payload["owner_source_freshness_ok"] is False
    assert payload["source_freshness_blockers"]
    assert payload["owner_approved"] is False
    assert payload["no_external_writes_performed"] is True
    assert Path(payload["output_mapping"]).exists()
    assert Path(payload["preflight_packet_dir"]).exists()

    mapping = json.loads(Path(payload["output_mapping"]).read_text(encoding="utf-8"))
    assert mapping["creative_ready_declaration_received"] is True
    assert mapping["publish_authority"]["approved"] is False


def test_prepare_launch_readiness_detects_asset_dir_inputs(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()
    video = asset_dir / "line31_final_video.mp4"
    thumbnail = asset_dir / "line31_thumbnail.webp"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_launch_readiness_from_assets.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--output-mapping",
            str(tmp_path / "mapping.json"),
            "--preflight-output-root",
            str(tmp_path),
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--approval-output-dir",
            str(tmp_path / "approvals"),
            "--run-id",
            "asset_dir",
            "--creative-ready-declared",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["resolved_video"] == str(video.resolve())
    assert payload["resolved_thumbnail"] == str(thumbnail.resolve())

    mapping = json.loads(Path(payload["output_mapping"]).read_text(encoding="utf-8"))
    asset = mapping["assets"][0]
    assert asset["local_file_path"] == str(video.resolve())
    assert asset["thumbnail_path_or_uri"] == str(thumbnail.resolve())


def test_prepare_launch_readiness_asset_dir_with_approval_is_launch_ready(
    tmp_path: Path,
) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()
    video = asset_dir / "line31_final_video.mp4"
    thumbnail = asset_dir / "line31_thumbnail.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    approval_text = _approval_text(tmp_path)
    tracking_evidence = _tracking_qa_evidence(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_launch_readiness_from_assets.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--output-mapping",
            str(tmp_path / "mapping.json"),
            "--preflight-output-root",
            str(tmp_path),
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--approval-output-dir",
            str(tmp_path / "approvals"),
            "--run-id",
            "asset_dir_approved",
            "--creative-ready-declared",
            "--approval-text-file",
            str(approval_text),
            "--tracking-qa-evidence-file",
            str(tracking_evidence),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    assert payload["ready_to_publish"] is False
    assert payload["owner_approved"] is True
    assert payload["owner_source_freshness_ok"] is False
    assert payload["source_freshness_blockers"]
    assert payload["resolved_video"] == str(video.resolve())
    assert payload["resolved_thumbnail"] == str(thumbnail.resolve())

    mapping = json.loads(Path(payload["output_mapping"]).read_text(encoding="utf-8"))
    evidence_path = Path(mapping["publish_authority"]["approval_evidence_path"])
    assert evidence_path.exists()
    assert mapping["publish_authority"]["approval_evidence_sha256"] == _sha(evidence_path)
    assert Path(payload["preflight_packet_dir"]).exists()


def test_prepare_launch_readiness_rejects_ambiguous_asset_dir(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()
    (asset_dir / "line31_final_video_a.mp4").write_bytes(b"fake-video-a")
    (asset_dir / "line31_final_video_b.mov").write_bytes(b"fake-video-b")
    (asset_dir / "line31_thumbnail.png").write_bytes(b"fake-thumbnail")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_line31_launch_readiness_from_assets.py",
            "--creative-id",
            "line31_countrywide_v1",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--landing-url",
            "https://acmewear.pro/line31",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--duration-seconds",
            "18",
            "--utm-placement",
            "reels",
            "--output-mapping",
            str(tmp_path / "mapping.json"),
            "--preflight-output-root",
            str(tmp_path),
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--approval-output-dir",
            str(tmp_path / "approvals"),
            "--run-id",
            "ambiguous_asset_dir",
            "--creative-ready-declared",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "expected exactly one video file" in completed.stderr


def test_prepare_launch_readiness_owner_approved_records_evidence(
    tmp_path: Path,
) -> None:
    command, _, _ = _base_command(tmp_path, run_id="approved")
    approval_text = _approval_text(tmp_path)
    tracking_evidence = _tracking_qa_evidence(tmp_path)
    completed = subprocess.run(
        [
            *command,
            "--creative-ready-declared",
            "--approval-text-file",
            str(approval_text),
            "--tracking-qa-evidence-file",
            str(tracking_evidence),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    assert payload["ready_to_publish"] is False
    assert payload["owner_approved"] is True
    assert payload["owner_source_freshness_ok"] is False
    assert payload["source_freshness_blockers"]

    mapping = json.loads(Path(payload["output_mapping"]).read_text(encoding="utf-8"))
    evidence_path = Path(mapping["publish_authority"]["approval_evidence_path"])
    assert evidence_path.exists()
    assert mapping["publish_authority"]["approval_evidence_sha256"] == _sha(evidence_path)
    assert mapping["tracking_redirect_qa"]["evidence_sha256"] == _sha(tracking_evidence)
    assert Path(payload["preflight_packet_dir"]).exists()


def test_prepare_launch_readiness_rejects_bad_approval_text(tmp_path: Path) -> None:
    command, _, _ = _base_command(tmp_path, run_id="bad_approval")
    bad = tmp_path / "bad_approval.txt"
    bad.write_text("I approve something else.\n", encoding="utf-8")

    completed = subprocess.run(
        [*command, "--creative-ready-declared", "--approval-text-file", str(bad)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "exact required LINE31 owner approval phrase" in completed.stderr


def test_prepare_launch_readiness_requires_creative_ready_for_approval(
    tmp_path: Path,
) -> None:
    command, _, _ = _base_command(tmp_path, run_id="approval_without_ready")
    approval_text = _approval_text(tmp_path)

    completed = subprocess.run(
        [*command, "--approval-text-file", str(approval_text)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "requires --creative-ready-declared" in completed.stderr


def test_prepare_launch_readiness_requires_tracking_qa_for_approval(
    tmp_path: Path,
) -> None:
    command, _, _ = _base_command(tmp_path, run_id="approval_without_tracking")
    approval_text = _approval_text(tmp_path)

    completed = subprocess.run(
        [
            *command,
            "--creative-ready-declared",
            "--approval-text-file",
            str(approval_text),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "requires --tracking-qa-evidence-file" in completed.stderr


def test_prepare_launch_readiness_refuses_mapping_overwrite(tmp_path: Path) -> None:
    command, _, _ = _base_command(tmp_path, run_id="overwrite")
    output_mapping = tmp_path / "mapping.json"
    output_mapping.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [*command, "--creative-ready-declared"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "pass --overwrite" in completed.stderr
