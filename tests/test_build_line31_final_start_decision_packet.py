from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.build_line31_final_start_decision_packet import build_decision_payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_status(tmp_path: Path) -> dict[str, object]:
    meta_manifest = tmp_path / "meta" / "manifest.json"
    activation_manifest = tmp_path / "activation" / "manifest.json"
    activation_phrase = tmp_path / "activation" / "REQUIRED.txt"
    traceability_manifest = tmp_path / "traceability" / "manifest.json"
    label_manifest = tmp_path / "label" / "manifest.json"
    monitoring_manifest = tmp_path / "monitoring" / "manifest.json"
    for path in [
        meta_manifest,
        activation_manifest,
        traceability_manifest,
        label_manifest,
        monitoring_manifest,
    ]:
        _write_json(path, {"ok": True})
    activation_phrase.write_text(
        "I approve META_API_LIVE_WRITE: activate only existing LINE31 countrywide Meta campaign 120245481137650641\n",
        encoding="utf-8",
    )
    return {
        "status": "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED",
        "owner_facing_publish_status": "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION",
        "noncreative_blockers": [],
        "missing_or_pending": [
            "LINE31 Meta campaign, ad set, and exactly three ads are source-verified but still PAUSED",
            "final launch/start decision remains pending before activation",
        ],
        "latest_meta_current_readonly_snapshot": {
            "manifest": str(meta_manifest),
            "gate": "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_NO_WRITE",
            "checks_failed": 0,
            "checks_review": 0,
            "retained_ui_only_gaps": [],
            "current_state_summary": {
                "campaign_id": "120245481137650641",
                "adset_id": "120245481997290641",
                "campaign_status": "PAUSED",
                "adset_status": "PAUSED",
                "ads_by_adset_count": 3,
                "ad_ids": [
                    "120245492808400641",
                    "120245488532270641",
                    "120245492808390641",
                ],
                "adset_daily_budget": "3093",
                "customer_visible_message": "Женский комплект AcmeWear 3в1. Закажи на Каспи и получи сумку в подарок!",
                "customer_visible_cta": "ORDER_NOW",
                "customer_visible_title": "AcmeWear 3в1",
                "landing_url": "https://acmewear.pro/line31",
                "multi_advertiser_ads_enroll_statuses": {
                    "120245492808400641": "OPT_OUT",
                    "120245488532270641": "OPT_OUT",
                    "120245492808390641": "OPT_OUT",
                },
            },
        },
        "latest_meta_current_activation_preflight": {
            "manifest": str(activation_manifest),
            "gate": "GREEN_LINE31_META_ACTIVATE_ONLY_PREFLIGHT_READY_NO_WRITE",
            "apply_requested": False,
            "meta_write_attempted": False,
            "required_meta_write_phrase_path": str(activation_phrase),
            "preflight_evidence_lock": {
                "path": str(tmp_path / "activation" / "preflight_evidence_lock.json"),
                "sha256": "lock-sha",
            },
        },
        "latest_customer_journey_traceability_audit": {
            "manifest": str(traceability_manifest),
            "gate": "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE",
            "checks_failed": 0,
        },
        "latest_line31_live_customer_label_probe": {
            "manifest": str(label_manifest),
            "gate": "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE",
            "checks_failed": 0,
        },
        "latest_post_publish_monitoring_packet": {
            "manifest": str(monitoring_manifest),
            "gate": "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE",
            "meta_write_attempted": False,
            "truth_separation_contract": ["Meta truth stays separate."],
            "decision_gates": {"first_hour": "delivery ok"},
        },
    }


def test_decision_payload_ready_yellow_when_only_final_decision_remains(tmp_path: Path) -> None:
    oracle_pack = tmp_path / "oracle"
    (oracle_pack / "Answer").mkdir(parents=True)
    status_path = tmp_path / "status.json"
    status = _base_status(tmp_path)
    _write_json(status_path, status)

    payload = build_decision_payload(
        status=status,
        status_path=status_path,
        oracle_pack=oracle_pack,
        generated_at="2026-06-04T11:00:00+05:00",
    )

    assert payload["gate"] == "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"
    assert payload["checks_failed"] == 0
    assert payload["current_decision_state"]["status"] == "PAUSED_PRESTART_READY_FOR_OWNER_EXPERT_DECISION"
    assert payload["decision_options"][0]["option"] == "START_AS_IS"
    assert "--execute-approved-activation" in payload["decision_options"][0]["activation_command_template"]
    assert payload["meta_write_attempted"] is False
    assert payload["goal_complete"] is False


def test_decision_payload_red_when_meta_ui_gap_remains(tmp_path: Path) -> None:
    oracle_pack = tmp_path / "oracle"
    (oracle_pack / "Answer").mkdir(parents=True)
    status_path = tmp_path / "status.json"
    status = _base_status(tmp_path)
    status["latest_meta_current_readonly_snapshot"]["retained_ui_only_gaps"] = ["multi_advertiser_unknown"]  # type: ignore[index]

    payload = build_decision_payload(
        status=status,
        status_path=status_path,
        oracle_pack=oracle_pack,
        generated_at="2026-06-04T11:00:00+05:00",
    )

    assert payload["gate"] == "RED_LINE31_FINAL_START_DECISION_PACKET_INCOMPLETE_NO_WRITE"
    assert payload["checks_failed"] == 1
    assert any(row["check"] == "no_retained_meta_ui_gaps" and row["status"] == "FAIL" for row in payload["requirements_matrix"])


def test_decision_packet_cli_writes_outputs(tmp_path: Path) -> None:
    oracle_pack = tmp_path / "oracle"
    (oracle_pack / "Answer").mkdir(parents=True)
    status_path = tmp_path / "status.json"
    _write_json(status_path, _base_status(tmp_path))
    output_root = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_final_start_decision_packet.py",
            "--status-path",
            str(status_path),
            "--oracle-pack",
            str(oracle_pack),
            "--output-root",
            str(output_root),
            "--run-id",
            "packet",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"
    assert Path(payload["manifest_path"]).is_file()
    assert Path(payload["summary_md"]).read_text(encoding="utf-8").startswith(
        "Gate: YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"
    )
    assert Path(payload["requirements_matrix_csv"]).is_file()
    assert Path(payload["next_owner_action_md"]).is_file()
