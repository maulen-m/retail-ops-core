from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from scripts.report_line31_next_launch_action import build_report
from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase
from scripts.validate_line31_launch_readiness import REQUIRED_CLOSEOUT_TOKENS, READY_GATE

CURRENT_SOURCE_BLOCKER = "Cash_Balances latest timestamp mismatch"
SYNTHETIC_APPROVAL = Path("tests/fixtures/line31/SYNTHETIC_APPROVAL_PHRASE.txt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_closeout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "closeout.md").write_text(
        "\n".join([READY_GATE, *REQUIRED_CLOSEOUT_TOKENS]),
        encoding="utf-8",
    )


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


def _write_ready_mapping(root: Path, video: Path, thumbnail: Path) -> None:
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
            "approval_evidence_path": str(approval_evidence),
            "approval_evidence_sha256": _sha(approval_evidence),
        },
    }
    (root / "final_creative_asset_mapping_template.json").write_text(
        json.dumps(mapping),
        encoding="utf-8",
    )


def test_report_current_state_points_to_fill_creative_mapping() -> None:
    report = build_report()

    assert report["status"] == "YELLOW"
    assert report["ready_to_publish"] is False
    assert report["pending_gate_ok"] is False
    assert report["pending_gate"] == "YELLOW"
    assert report["strict_gate_ok"] is False
    assert report["strict_gate"] == "YELLOW"
    assert report["noncreative_blockers"]
    assert report["owner_source_freshness_ok"] is False
    assert any(CURRENT_SOURCE_BLOCKER in item for item in report["source_freshness_blockers"])
    assert report["final_assets_ready"] is True
    assert report["live_tracking_green"] is True
    assert "assets[0].video_sha256" not in report["missing_or_pending"]
    assert report["missing_or_pending"] == [
        "publish_authority.approved must be true for publish readiness"
    ]
    assert "tracking_redirect_qa.evidence_path" not in report["missing_or_pending"]
    assert "tracking_redirect_qa.evidence_sha256" not in report["missing_or_pending"]
    assert "tracking_redirect_qa.gate" not in report["missing_or_pending"]
    assert "non-creative LINE31 strict blockers" in report["next_action"]
    assert (
        report["one_shot_readiness_helper"]
        == "python3 scripts/prepare_line31_launch_readiness_from_assets.py"
    )
    assert "prepare_line31_launch_readiness_from_assets.py" in report[
        "one_shot_example_command"
    ]
    assert "--approval-text-file" in report["one_shot_example_command"]
    assert "--tracking-qa-evidence-file" in report["one_shot_example_command"]
    assert "prepare_line31_final_creative_mapping.py" in report[
        "mapping_only_example_command"
    ]
    assert "--asset-dir" in report["mapping_only_example_command"]
    assert "--tracking-qa-evidence-file" in report["mapping_only_example_command"]
    assert (
        report["drop_intake_helper"]
        == "python3 scripts/create_line31_final_creative_drop_intake.py"
    )
    assert "create_line31_final_creative_drop_intake.py --json" in report[
        "drop_intake_command"
    ]
    assert (
        report["drop_validator_helper"]
        == "python3 scripts/validate_line31_final_creative_drop_intake.py"
    )
    assert "validate_line31_final_creative_drop_intake.py" in report[
        "drop_validator_example_command"
    ]
    assert (
        report["current_drop_validator_helper"]
        == "python3 scripts/validate_line31_current_final_creative_drop.py"
    )
    assert report["current_drop_validator_command"] == (
        "python3 scripts/validate_line31_current_final_creative_drop.py --json"
    )
    assert "python3 scripts/validate_line31_final_creative_drop_intake.py --help" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/validate_line31_current_final_creative_drop.py --json" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/create_line31_final_creative_drop_intake.py --help" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/prepare_line31_launch_readiness_from_assets.py --help" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/build_line31_current_noncreative_gate_matrix.py --json" in report[
        "commands_to_close"
    ]
    assert (
        "python3 scripts/validate_line31_owner_objective_source_freshness.py --json"
        in report["commands_to_close"]
    )
    assert report["commands_to_close"].index(
        "python3 scripts/validate_line31_owner_objective_source_freshness.py --json"
    ) < report["commands_to_close"].index(
        "python3 scripts/build_line31_launch_preflight_packet.py --json"
    )
    assert report["commands_to_close"].index(
        "python3 scripts/build_line31_launch_preflight_packet.py --json"
    ) < report["commands_to_close"].index(
        "python3 scripts/audit_line31_active_goal_completion.py --json"
    )
    assert "python3 scripts/audit_line31_active_goal_completion.py --json" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/write_line31_current_launch_status.py --json" in report[
        "commands_to_close"
    ]
    assert "python3 scripts/validate_params.py --strict" not in report[
        "commands_to_close"
    ]
    assert "python3 scripts/validate_params.py --strict" in report[
        "advisory_repo_health_commands"
    ]
    assert "approval_evidence_path" in report["approval_evidence_requirement"]
    assert "tracking_redirect_qa.evidence_sha256" in report["approval_evidence_requirement"]
    assert "--require-mapping-ready" in report["approval_evidence_requirement"]
    assert (
        report["standalone_approval_recorder"]
        == "python3 scripts/record_line31_owner_publish_approval.py"
    )
    assert "--require-mapping-ready" in report[
        "standalone_approval_recorder_example_command"
    ]
    assert f"--mapping {report['mapping_path']}" in report[
        "standalone_approval_recorder_example_command"
    ]
    assert "placeholder creative mapping" in report["standalone_approval_guard"]
    assert "KEEP_INTERNAL_KASPI_LINE31_CAMPAIGNS_ON" in report["internal_kaspi_policy"]


def test_report_ready_state_points_to_serialized_publish_agent(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    thumbnail = tmp_path / "thumb.png"
    video.write_bytes(b"video")
    thumbnail.write_bytes(b"thumb")
    _write_closeout(tmp_path)
    _write_ready_mapping(tmp_path, video, thumbnail)

    report = build_report(evidence_root=tmp_path)

    assert report["status"] == "READY_TO_PUBLISH"
    assert report["ready_to_publish"] is True
    assert report["missing_or_pending"] == []
    assert "FINAL_CREATIVE_META_PUBLISH" in report["starter_prompt"]


def test_report_command_outputs_json() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/report_line31_next_launch_action.py", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "YELLOW"
    assert payload["ready_to_publish"] is False
    assert payload["missing_or_pending"] == [
        "publish_authority.approved must be true for publish readiness"
    ]
    assert payload["owner_source_freshness_ok"] is False
    assert any(CURRENT_SOURCE_BLOCKER in item for item in payload["source_freshness_blockers"])
    assert "one_shot_readiness_helper" in payload
    assert "one_shot_example_command" in payload
    assert "mapping_only_example_command" in payload
    assert "drop_intake_command" in payload
    assert "drop_validator_example_command" in payload
    assert "current_drop_validator_command" in payload
    assert "standalone_approval_recorder_example_command" in payload
    assert "--require-mapping-ready" in payload[
        "standalone_approval_recorder_example_command"
    ]
    assert payload["noncreative_blockers"]
