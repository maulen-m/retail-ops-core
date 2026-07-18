from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.validate_line31_launch_readiness import (
    DEFAULT_EVIDENCE_ROOT,
    REQUIRED_CLOSEOUT_TOKENS,
    READY_GATE,
    validate_launch_readiness,
)
from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase

SYNTHETIC_APPROVAL = Path("tests/fixtures/line31/SYNTHETIC_APPROVAL_PHRASE.txt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_closeout(root: Path, extra: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    body = "\n".join([READY_GATE, *REQUIRED_CLOSEOUT_TOKENS, extra])
    (root / "closeout.md").write_text(body, encoding="utf-8")


def _write_approval_evidence(root: Path) -> Path:
    phrase = required_owner_approval_phrase(SYNTHETIC_APPROVAL)
    evidence = root / "owner_approval_evidence.md"
    evidence.write_text(
        f"# Owner Approval Evidence\n\nRecorded: 2026-06-01T16:00:00+05:00\n\n{phrase}\n",
        encoding="utf-8",
    )
    return evidence


def _write_tracking_qa_evidence(root: Path) -> Path:
    evidence = root / "tracking_redirect_qa.json"
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


def _write_publish_ready_mapping(root: Path, video_path: Path, thumb_path: Path) -> None:
    approval_evidence = _write_approval_evidence(root)
    tracking_evidence = _write_tracking_qa_evidence(root)
    mapping = {
        "purpose": "LINE31 countrywide Meta launch final creative mapping intake template",
        "source_gate": "RUNTIME_ASSET_MAPPING_PREPARED",
        "creative_ready_declaration_received": True,
        "internal_kaspi_line31_campaigns_policy": (
            "KEEP_ON_UNTIL_OWNER_CREATIVE_READY_DECLARATION_AND_SEPARATE_PAUSE_APPROVAL"
        ),
        "landing_tracking_contract": {
            "utm_source": "meta",
            "utm_medium": "paid_social",
            "utm_campaign": "line31_countrywide",
            "required_fields": [
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_placement",
            ],
        },
        "tracking_redirect_qa": {
            "required": True,
            "gate": "GREEN",
            "evidence_path": str(tracking_evidence),
            "evidence_sha256": _sha(tracking_evidence),
        },
        "assets": [
            {
                "creative_id": "line31_launch_001",
                "local_file_path": str(video_path),
                "final_asset_uri": "https://cdn.acmewear.kz/line31/final.mp4",
                "thumbnail_path_or_uri": str(thumb_path),
                "video_sha256": _sha(video_path),
                "thumbnail_sha256": _sha(thumb_path),
                "aspect_ratio": "9:16",
                "duration_seconds": 21,
                "language": "ru",
                "primary_cta": "Shop now",
                "landing_url": (
                    "https://acmewear.pro/line31?"
                    "utm_source=meta&utm_medium=paid_social&utm_campaign=line31_countrywide&"
                    "utm_content=line31_launch_001&utm_placement=reels"
                ),
                "utm_content": "line31_launch_001",
                "utm_placement": "reels",
                "kaspi_marketplace_cta_url": "https://kaspi.kz/shop/p/sportivnyi-kostjum-acmewear-of-line31-st-black-123456789/",
                "owner_notes": "",
            }
        ],
        "publish_authority": {
            "owner_approval_required": True,
            "approval_phrase_path": str(SYNTHETIC_APPROVAL),
            "approved": True,
            "approval_evidence_path": str(approval_evidence),
            "approval_evidence_sha256": _sha(approval_evidence),
        },
    }
    (root / "final_creative_asset_mapping_template.json").write_text(
        json.dumps(mapping),
        encoding="utf-8",
    )


def test_current_line31_evidence_reports_real_noncreative_blockers() -> None:
    result = validate_launch_readiness(
        DEFAULT_EVIDENCE_ROOT,
        allow_pending_creative=True,
    )

    assert not result.ok
    assert result.gate == "YELLOW"
    assert result.metrics["creative_template_ok"] is True
    assert result.metrics["creative_strict_ok"] is False
    assert result.metrics["current_noncreative_can_use_green_except_creative"] is False
    assert set(result.metrics["current_noncreative_retained_blockers"]) == {
        "compact_child_cogs_integrity",
        "profit_publication_integrity",
        "generic_po_dashboard_stock_freshness_validator",
    }
    assert any("missing closeout" in error for error in result.errors)
    assert any("current non-creative gate is not green-except-creative" in error for error in result.errors)


def test_current_noncreative_matrix_blocks_pending_mode_when_yellow(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "overall_gate": "YELLOW",
                "can_use_green_except_creative": False,
                "gate_reason": "test blocker",
                "retained_noncreative_blockers": ["strict_repo_gate"],
            }
        ),
        encoding="utf-8",
    )

    result = validate_launch_readiness(
        DEFAULT_EVIDENCE_ROOT,
        allow_pending_creative=True,
        current_noncreative_matrix=matrix,
    )

    assert not result.ok
    assert result.gate == "YELLOW"
    assert any("current non-creative gate is not green-except-creative" in error for error in result.errors)


def test_current_line31_evidence_fails_strict_publish_until_creative_is_filled() -> None:
    result = validate_launch_readiness(DEFAULT_EVIDENCE_ROOT)

    assert not result.ok
    assert result.gate == "YELLOW"
    assert any("creative publish not ready" in error for error in result.errors)


def test_publish_ready_mapping_passes_strict(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    thumb = tmp_path / "thumb.png"
    video.write_bytes(b"video")
    thumb.write_bytes(b"thumb")
    _write_closeout(tmp_path)
    _write_publish_ready_mapping(tmp_path, video, thumb)

    result = validate_launch_readiness(tmp_path)

    assert result.ok, result.errors
    assert result.gate == "GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH"
    assert result.metrics["creative_strict_ok"] is True


def test_missing_tracking_redirect_qa_keeps_strict_publish_yellow(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    thumb = tmp_path / "thumb.png"
    video.write_bytes(b"video")
    thumb.write_bytes(b"thumb")
    _write_closeout(tmp_path)
    _write_publish_ready_mapping(tmp_path, video, thumb)
    mapping = json.loads((tmp_path / "final_creative_asset_mapping_template.json").read_text())
    mapping["tracking_redirect_qa"]["evidence_path"] = ""
    mapping["tracking_redirect_qa"]["evidence_sha256"] = ""
    mapping["tracking_redirect_qa"]["gate"] = ""
    (tmp_path / "final_creative_asset_mapping_template.json").write_text(
        json.dumps(mapping),
        encoding="utf-8",
    )

    result = validate_launch_readiness(tmp_path)

    assert not result.ok
    assert result.gate == "YELLOW"
    assert any("tracking_redirect_qa.evidence_path is required" in error for error in result.errors)


def test_missing_closeout_gate_fails_even_if_mapping_is_ready(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    thumb = tmp_path / "thumb.png"
    video.write_bytes(b"video")
    thumb.write_bytes(b"thumb")
    _write_closeout(tmp_path)
    (tmp_path / "closeout.md").write_text("Gate: GREENISH\n", encoding="utf-8")
    _write_publish_ready_mapping(tmp_path, video, thumb)

    result = validate_launch_readiness(tmp_path)

    assert not result.ok
    assert any("closeout missing required gate" in error for error in result.errors)


def test_line31_launch_readiness_commands_do_not_mutate_protected_surfaces() -> None:
    protected = [
        Path("db/app.db"),
        Path("excel_ui/SALES_KSP_CRM_V3.xlsx"),
    ]
    missing = [path for path in protected if not path.exists()]
    if missing:
        pytest.skip(f"protected surfaces missing in this checkout: {missing}")

    before = {path: _sha(path) for path in protected}
    commands = [
        [
            sys.executable,
            "scripts/validate_line31_launch_readiness.py",
            "--allow-pending-creative",
            "--json",
        ],
        [
            sys.executable,
            "scripts/validate_line31_launch_readiness.py",
            "--json",
        ],
        [
            sys.executable,
            "scripts/validate_line31_final_creative_mapping.py",
            "--mapping",
            "config/line31/final_creative_mapping_template.json",
            "--template-ok",
            "--json",
        ],
        [
            sys.executable,
            "scripts/validate_line31_final_creative_mapping.py",
            "--mapping",
            "config/line31/final_creative_mapping_template.json",
            "--json",
        ],
    ]

    returncodes = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
        )
        returncodes.append(completed.returncode)
        assert completed.stdout.strip().startswith("{"), completed.stdout + completed.stderr

    assert returncodes == [1, 1, 0, 1]
    after = {path: _sha(path) for path in protected}
    assert after == before
