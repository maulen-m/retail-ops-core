from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase


def _write_assets(asset_dir: Path) -> tuple[Path, Path]:
    asset_dir.mkdir()
    video = asset_dir / "line31_final.mp4"
    thumbnail = asset_dir / "line31_thumb.png"
    video.write_bytes(b"fake-video")
    thumbnail.write_bytes(b"fake-thumbnail")
    return video, thumbnail


def _write_tracking_qa_evidence(tmp_path: Path) -> Path:
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


def test_validate_drop_intake_rejects_empty_folder(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    asset_dir.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_final_creative_drop_intake.py",
            "--asset-dir",
            str(asset_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "NOT_READY"
    assert any("expected exactly one video" in error for error in payload["errors"])


def test_validate_drop_intake_rejects_placeholder_urls(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    _write_assets(asset_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_final_creative_drop_intake.py",
            "--asset-dir",
            str(asset_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "NOT_READY"
    assert any("final_asset_uri must not be a placeholder/example URI" in error for error in payload["errors"])
    assert any(
        "kaspi_marketplace_cta_url must not be a placeholder/example URI"
        in error
        for error in payload["errors"]
    )


def test_validate_drop_intake_assets_and_urls_ready_pending_approval(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    video, thumbnail = _write_assets(asset_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_final_creative_drop_intake.py",
            "--asset-dir",
            str(asset_dir),
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
    assert payload["resolved_video"] == str(video.resolve())
    assert payload["resolved_thumbnail"] == str(thumbnail.resolve())
    assert payload["assets_ready"] is True
    assert payload["approval_ready"] is False
    assert payload["no_external_writes_performed"] is True


def test_validate_drop_intake_can_require_exact_approval(tmp_path: Path) -> None:
    asset_dir = tmp_path / "final_assets"
    _write_assets(asset_dir)
    phrase = required_owner_approval_phrase(
        Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_publish_intake_and_approval.md"
        )
    )
    approval = tmp_path / "approval.txt"
    approval.write_text(f"Owner approval.\n\n{phrase}\n", encoding="utf-8")
    tracking = _write_tracking_qa_evidence(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_line31_final_creative_drop_intake.py",
            "--asset-dir",
            str(asset_dir),
            "--final-asset-uri",
            "https://cdn.acmewear.kz/line31/final.mp4",
            "--kaspi-marketplace-cta-url",
            "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
            "--approval-text-file",
            str(approval),
            "--tracking-qa-evidence-file",
            str(tracking),
            "--require-approval",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "READY_FOR_ONE_SHOT_WITH_APPROVAL"
    assert payload["approval_ready"] is True
