from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.audit_line31_active_goal_completion import build_completion_audit
from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase
from scripts.validate_line31_launch_readiness import REQUIRED_CLOSEOUT_TOKENS, READY_GATE

SYNTHETIC_APPROVAL = Path("tests/fixtures/line31/SYNTHETIC_APPROVAL_PHRASE.txt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_closeout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "closeout.md").write_text(
        "\n".join([READY_GATE, *REQUIRED_CLOSEOUT_TOKENS]),
        encoding="utf-8",
    )


def _write_ready_mapping(root: Path) -> None:
    video = root / "video.mp4"
    thumbnail = root / "thumb.png"
    video.write_bytes(b"video")
    thumbnail.write_bytes(b"thumb")
    phrase = required_owner_approval_phrase(SYNTHETIC_APPROVAL)
    evidence = root / "owner_approval_evidence.md"
    evidence.write_text(f"# Approval\n\n{phrase}\n", encoding="utf-8")
    tracking_evidence = root / "tracking_redirect_qa.json"
    tracking_evidence.write_text(
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
                "local_file_path": str(video),
                "final_asset_uri": "https://cdn.acmewear.kz/line31/final.mp4",
                "thumbnail_path_or_uri": str(thumbnail),
                "video_sha256": _sha(video),
                "thumbnail_sha256": _sha(thumbnail),
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
            }
        ],
        "publish_authority": {
            "owner_approval_required": True,
            "approval_phrase_path": str(SYNTHETIC_APPROVAL),
            "approved": True,
            "approval_evidence_path": str(evidence),
            "approval_evidence_sha256": _sha(evidence),
        },
    }
    (root / "final_creative_asset_mapping_template.json").write_text(
        json.dumps(mapping),
        encoding="utf-8",
    )


def test_current_active_goal_completion_audit_is_incomplete(tmp_path: Path) -> None:
    audit = build_completion_audit(noncreative_output_root=tmp_path / "noncreative")
    requirement_status = {
        row["requirement"]: row["status"] for row in audit["requirements"]
    }

    assert audit["complete"] is False
    assert audit["gate"] == "INCOMPLETE"
    assert audit["ready_to_publish"] is False
    assert audit["pending_ok"] is False
    assert audit["strict_ok"] is False
    assert audit["current_noncreative_matrix_refreshed"] is True
    assert audit["current_noncreative_matrix"]["overall_gate"] in {"GREEN", "YELLOW"}
    assert requirement_status["Non-creative LINE31 launch readiness remains green"] == "PENDING"
    assert requirement_status[
        "Option 2 unrelated-failure repair first is repaired/quarantined"
    ] == (
        "ACHIEVED"
        if audit["current_noncreative_matrix"].get("can_use_green_except_creative")
        else "PENDING"
    )
    assert (
        requirement_status["Owner objective source freshness is green"]
        == "PENDING"
    )
    assert (
        requirement_status["Current cash and SHR timing use latest owner workbook truth"]
        == "PENDING"
    )
    assert (
        requirement_status["Protected cash reserve is exactly 800000 KZT"]
        == "PENDING"
    )
    assert (
        requirement_status[
            "Current LINE31 stock uses April leftovers plus PO1-A arrival rebuild"
        ]
        == "PENDING"
    )
    assert any(
        row["requirement"] == "Final creative asset mapping is filled and hash-verified"
        and row["status"] == "ACHIEVED"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "LINE31 Meta publish bridge is green and no-write"
        and row["status"] == "ACHIEVED"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "LINE31 Meta campaign/adset/three ads are live-applied through API"
        and row["status"] == "PENDING"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "Meta adset budget currency matches owner-approved KZT intent"
        and row["status"] == "PENDING"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "Post-publish monitoring plan is ready and truth-separated"
        and row["status"] == "ACHIEVED"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "Customer journey traceability audit is green"
        and row["status"] == "ACHIEVED"
        for row in audit["requirements"]
    )
    assert any(
        row["requirement"] == "Exact owner Meta publish approval evidence is recorded and SHA-verified"
        and row["status"] == "PENDING"
        for row in audit["requirements"]
    )
    assert audit["next_action"].startswith("Keep the partial LINE31 Meta shell paused.")


def test_completion_audit_passes_for_strict_ready_fixture(tmp_path: Path) -> None:
    _write_closeout(tmp_path)
    _write_ready_mapping(tmp_path)

    audit = build_completion_audit(
        evidence_root=tmp_path,
        refresh_noncreative_matrix=False,
    )

    assert audit["complete"] is False
    assert audit["gate"] == "INCOMPLETE"
    assert audit["ready_to_publish"] is False
    assert audit["pending_ok"] is True
    assert audit["strict_ok"] is True
    assert audit["current_noncreative_matrix_refreshed"] is False
    assert audit["current_noncreative_matrix"] is None
    requirement_status = {
        row["requirement"]: row["status"] for row in audit["requirements"]
    }
    assert (
        requirement_status["Non-creative LINE31 launch readiness remains green"]
        == "ACHIEVED"
    )
    assert (
        requirement_status["Strict LINE31 launch readiness passes"]
        == "ACHIEVED"
    )
    assert (
        requirement_status["Owner objective source freshness is green"]
        == "PENDING"
    )
    assert (
        requirement_status["Meta adset budget currency matches owner-approved KZT intent"]
        == "PENDING"
    )
    assert audit["next_action"].startswith("Keep the partial LINE31 Meta shell paused.")


def test_completion_audit_cli_exits_nonzero_when_incomplete(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_line31_active_goal_completion.py",
            "--json",
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["complete"] is False
    assert payload["gate"] == "INCOMPLETE"
    assert payload["current_noncreative_matrix_refreshed"] is True


def test_completion_audit_cli_allow_incomplete_exits_zero(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_line31_active_goal_completion.py",
            "--json",
            "--allow-incomplete",
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["complete"] is False
    assert payload["current_noncreative_matrix_refreshed"] is True


def test_completion_audit_cli_writes_markdown_file(tmp_path: Path) -> None:
    markdown_path = tmp_path / "audit.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_line31_active_goal_completion.py",
            "--json",
            "--allow-incomplete",
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--write-markdown",
            str(markdown_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["complete"] is False
    text = markdown_path.read_text(encoding="utf-8")
    assert "# LINE31 Active Goal Completion Audit" in text
    assert "Gate: `INCOMPLETE`" in text
    assert "Final creative asset mapping is filled and hash-verified" in text
    assert "Owner objective source freshness is green" in text
    assert "LINE31 Meta publish bridge is green and no-write" in text
    assert "LINE31 Meta campaign/adset/three ads are live-applied through API" in text
    assert "Post-publish monitoring plan is ready and truth-separated" in text
    assert "Customer journey traceability audit is green" in text
