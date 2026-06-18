from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys

from scripts.build_line31_launch_preflight_packet import build_packet
from scripts.validate_line31_owner_objective_source_freshness import DEFAULT_OWNER_FACTS_PATH


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_gate(payload: dict) -> str:
    if payload["owner_source_freshness_ok"] is False:
        return "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    if payload["strict_ok"] is True:
        return "GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH"
    if payload["pending_ok"] is True:
        return "GREEN_EXCEPT_CREATIVE"
    return "YELLOW_NON_CREATIVE_READINESS_BLOCKERS"


def test_build_current_line31_preflight_packet(tmp_path: Path) -> None:
    manifest = build_packet(
        output_root=tmp_path,
        run_id="unit",
        noncreative_output_root=tmp_path / "noncreative",
    )
    packet_dir = Path(manifest["packet_dir"])

    assert manifest["gate"] == _expected_gate(manifest)
    assert manifest["ready_to_publish"] is False
    assert manifest["strict_ok"] is False
    assert manifest["current_noncreative_matrix_refreshed"] is True
    assert manifest["current_noncreative_matrix"]["overall_gate"] in {"GREEN", "YELLOW"}
    if manifest["owner_source_freshness_ok"] is False:
        assert manifest["gate"] == "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
        assert manifest["source_freshness_blockers"]
        assert (
            manifest["next_action"]
            == "Repair owner objective source freshness before final creative publish readiness can be trusted."
        )
    else:
        assert manifest["owner_objective_source_freshness"]["gate"] == "GREEN_SOURCE_FRESHNESS"
        assert manifest["owner_objective_source_freshness"]["protected_reserve"] == {
            "expected_min_kzt": 800000,
            "owner_fact_min_kzt": 800000,
            "ok": True,
        }
    assert manifest["no_external_writes_performed"] is True
    assert "approval_evidence_path" in manifest["approval_evidence_requirement"]
    assert "--require-mapping-ready" in manifest["approval_evidence_requirement"]
    assert "--require-mapping-ready" in manifest[
        "standalone_approval_recorder_example_command"
    ]
    assert "placeholder creative mapping" in manifest["standalone_approval_guard"]
    assert packet_dir.exists()

    expected_files = {
        "commands_to_close.txt",
        "creative_strict_validation.json",
        "creative_template_validation.json",
        "next_launch_action.json",
        "owner_objective_source_freshness.json",
        "protected_surface_hashes.tsv",
        "readiness_pending_creative_allowed.json",
        "readiness_strict_publish.json",
        "line31_launch_preflight_manifest.json",
        "line31_launch_preflight_summary.md",
    }
    assert expected_files.issubset(set(manifest["outputs"]))

    written_manifest = json.loads(
        (packet_dir / "line31_launch_preflight_manifest.json").read_text(encoding="utf-8")
    )
    assert written_manifest["gate"] == manifest["gate"]
    assert "publish_authority.approved must be true for publish readiness" in written_manifest[
        "missing_or_pending"
    ]
    assert "tracking_redirect_qa.gate" in written_manifest["missing_or_pending"]
    assert "tracking_redirect_qa.evidence_sha256" in written_manifest["missing_or_pending"]
    if written_manifest["pending_ok"]:
        assert written_manifest["noncreative_blockers"] == []
    else:
        assert written_manifest["noncreative_blockers"]

    hashes = (packet_dir / "protected_surface_hashes.tsv").read_text(encoding="utf-8")
    assert "db/app.db" in hashes
    assert "SALES_KSP_CRM_V3.xlsx" in hashes
    summary = (packet_dir / "line31_launch_preflight_summary.md").read_text(
        encoding="utf-8"
    )
    assert "## Owner Objective Source Freshness" in summary
    assert "expected_min_kzt=800000" in summary
    assert "Advisory repo-health blockers" in summary
    assert "## Standalone Approval Recorder Command" in summary
    assert "--require-mapping-ready" in summary


def test_build_packet_refuses_existing_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "line31_final_launch_preflight_unit"
    output_dir.mkdir()

    try:
        build_packet(
            output_root=tmp_path,
            run_id="unit",
            noncreative_output_root=tmp_path / "noncreative",
        )
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("existing packet output should fail")


def test_build_packet_fails_closed_on_weak_owner_source_freshness(tmp_path: Path) -> None:
    owner_facts = json.loads(DEFAULT_OWNER_FACTS_PATH.read_text(encoding="utf-8"))
    owner_facts["cash"]["protected_reserve_min_kzt"] = 1500000
    owner_facts_path = tmp_path / "owner_facts_wrong_reserve.json"
    owner_facts_path.write_text(json.dumps(owner_facts), encoding="utf-8")

    manifest = build_packet(
        output_root=tmp_path,
        run_id="weak_owner_source",
        noncreative_output_root=tmp_path / "noncreative",
        owner_facts_path=owner_facts_path,
    )
    packet_dir = Path(manifest["packet_dir"])

    assert manifest["gate"] == "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    assert manifest["ready_to_publish"] is False
    assert manifest["owner_source_freshness_ok"] is False
    assert any(
        "protected reserve is not exactly 800000 KZT" in blocker
        for blocker in manifest["source_freshness_blockers"]
    )
    assert "Repair owner objective source freshness" in manifest["next_action"]

    next_action = json.loads(
        (packet_dir / "next_launch_action.json").read_text(encoding="utf-8")
    )
    assert next_action["owner_source_freshness_ok"] is False
    assert next_action["source_freshness_blockers"] == manifest[
        "source_freshness_blockers"
    ]
    summary = (packet_dir / "line31_launch_preflight_summary.md").read_text(
        encoding="utf-8"
    )
    assert "## Source Freshness Blockers" in summary


def test_build_packet_command_outputs_json(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_launch_preflight_packet.py",
            "--output-root",
            str(tmp_path),
            "--run-id",
            "cli",
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == _expected_gate(payload)
    if payload["owner_source_freshness_ok"] is False:
        assert payload["source_freshness_blockers"]
    else:
        assert payload["owner_objective_source_freshness"]["gate"] == "GREEN_SOURCE_FRESHNESS"
    assert Path(payload["packet_dir"]).exists()


def test_build_packet_command_does_not_mutate_protected_surfaces(tmp_path: Path) -> None:
    protected = [
        Path("db/app.db"),
        Path("excel_ui/SALES_KSP_CRM_V3.xlsx"),
    ]
    missing = [path for path in protected if not path.exists()]
    if missing:
        return

    before = {path: _sha(path) for path in protected}
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_line31_launch_preflight_packet.py",
            "--output-root",
            str(tmp_path),
            "--run-id",
            "no_mutation",
            "--noncreative-output-root",
            str(tmp_path / "noncreative"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    after = {path: _sha(path) for path in protected}
    assert after == before
