from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fixture_status(tmp_path: Path) -> Path:
    mapping = _write_json(tmp_path / "mapping.json", {"status": "FINAL_CREATIVE_READY"})
    return _write_json(
        tmp_path / "status.json",
        {
            "mapping_path": str(mapping),
            "latest_deploy_liveqa_sequence": {
                "gate": "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE",
                "live_qa": {"payload": {"gate": "GREEN"}},
                "live_route_probe": {"route_ready_for_postdeploy_qa": True},
            },
            "latest_meta_publish_bridge": {
                "gate": "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE",
                "owner_paste_file": str(tmp_path / "OWNER_LINE31.txt"),
                "owner_approval_evidence": str(tmp_path / "owner_evidence.md"),
                "owner_approved_mapping": str(tmp_path / "owner_mapping.json"),
                "meta_api_live_write_approval_file": str(tmp_path / "OWNER_META.txt"),
                "commands": {
                    "record_line31_owner_publish_approval": "record-command",
                    "write_owner_approved_mapping": "mapping-command",
                    "validate_owner_approved_mapping": "validate-command",
                    "green_meta_publish_preflight_no_write": "preflight-command",
                    "execute_meta_publish_after_exact_meta_api_live_write_approval": "execute-command",
                },
            },
            "latest_meta_line31_publish_preflight": {
                "errors": [
                    "publish_authority.approved must be true",
                    "publish_authority.approval_evidence_path is required",
                ]
            },
        },
    )


def test_post_publish_monitoring_packet_green_and_classifies_commands(tmp_path: Path) -> None:
    status = _fixture_status(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_post_publish_monitoring_packet.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "monitor_test",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
    assert payload["external_write_attempted"] is False
    assert payload["meta_write_attempted"] is False
    assert payload["checks"]["latest_meta_preflight_blocked_only_by_approval"] is True
    assert "Kaspi order truth" in " ".join(payload["truth_separation_contract"])
    assert Path(payload["future_synthetic_tracking_qa_approval_phrase_path"]).read_text(
        encoding="utf-8"
    ).startswith("I approve LINE31_POST_PUBLISH_SYNTHETIC_TRACKING_QA")

    command_rows = list(
        csv.DictReader(
            Path(payload["commands_tsv"]).open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    safety_values = {row["safety"] for row in command_rows}
    assert "local_no_write" in safety_values
    assert "meta_live_write_exact_approval_required" in safety_values
    assert "website_synthetic_write_exact_approval_required" in safety_values
    assert "external_readonly" in safety_values
    assert any(row["command"] == "execute-command" for row in command_rows)

    closeout = Path(payload["output_dir"]) / "closeout.md"
    assert closeout.exists()
    closeout_text = closeout.read_text(encoding="utf-8")
    assert "Gate: GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE" in closeout_text
    assert "Meta traffic truth" in closeout_text
    assert "HighIntentKaspiClick" in closeout_text


def test_post_publish_monitoring_packet_yellow_when_live_qa_missing(tmp_path: Path) -> None:
    status = _fixture_status(tmp_path)
    payload = json.loads(status.read_text(encoding="utf-8"))
    payload["latest_deploy_liveqa_sequence"]["live_qa"]["payload"]["gate"] = "YELLOW"
    status.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_post_publish_monitoring_packet.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "monitor_yellow",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_LINE31_POST_PUBLISH_MONITORING_PLAN_REVIEW_REQUIRED_NO_WRITE"
    assert payload["checks"]["live_tracking_qa_green"] is False
