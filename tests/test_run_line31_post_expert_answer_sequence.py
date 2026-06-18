from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path

from scripts import run_line31_post_expert_answer_sequence as sequence


def _args(tmp_path: Path) -> Namespace:
    return Namespace(
        oracle_pack=tmp_path / "oracle_pack",
        output_root=tmp_path / "validation",
        final_start_manifest=None,
        status_json_path=tmp_path / "current" / "status.json",
        status_markdown_path=tmp_path / "current" / "status.md",
        audit_markdown_path=tmp_path / "current" / "audit.md",
        run_id="seq",
        json=False,
    )


def _patch_common(monkeypatch, tmp_path: Path, *, intake: dict, audit: dict) -> None:
    def fake_intake_run(_args):
        return {
            "gate": intake["gate"],
            "decision": intake["decision"],
            "decision_confidence": intake.get("decision_confidence", "HIGH"),
            "manifest_path": str(tmp_path / "intake" / "manifest.json"),
            "summary_md": str(tmp_path / "intake" / "summary.md"),
            "next_safe_action_md": str(tmp_path / "intake" / "next.md"),
            "answer_dir": str(tmp_path / "oracle_pack" / "Answer"),
            "answer_path": intake.get("answer_path", ""),
            "next_safe_action": intake.get("next_safe_action", {"action": "WAIT"}),
        }

    def fake_status(**_kwargs):
        return {
            "status": "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED",
            "owner_facing_publish_status": "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION",
            "ready_to_publish": False,
            "missing_or_pending": ["final launch/start decision remains pending before activation"],
            "json_path": str(tmp_path / "current" / "status.json"),
            "markdown_path": str(tmp_path / "current" / "status.md"),
        }

    def fake_audit(**_kwargs):
        return audit

    def fake_audit_markdown(payload):
        return f"Gate: `{payload['gate']}`\n"

    monkeypatch.setattr(sequence.ingest_line31_expert_launch_answer, "run", fake_intake_run)
    monkeypatch.setattr(sequence, "write_current_status", fake_status)
    monkeypatch.setattr(sequence, "build_completion_audit", fake_audit)
    monkeypatch.setattr(sequence, "audit_markdown", fake_audit_markdown)


def test_sequence_waits_when_expert_answer_is_missing(monkeypatch, tmp_path: Path) -> None:
    _patch_common(
        monkeypatch,
        tmp_path,
        intake={"gate": "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE", "decision": "PENDING_ANSWER"},
        audit={
            "gate": "INCOMPLETE",
            "complete": False,
            "ready_to_publish": False,
            "next_action": "Send the Oracle pack to the external expert.",
        },
    )

    payload = sequence.run(_args(tmp_path))

    assert payload["gate"] == "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE"
    assert payload["expert_intake"]["decision"] == "PENDING_ANSWER"
    assert payload["meta_write_attempted"] is False
    assert payload["external_write_attempted"] is False
    assert Path(payload["manifest_path"]).exists()
    assert Path(payload["summary_md"]).exists()
    assert Path(payload["next_safe_action_md"]).exists()


def test_sequence_start_as_is_routes_to_activation_wait(monkeypatch, tmp_path: Path) -> None:
    _patch_common(
        monkeypatch,
        tmp_path,
        intake={
            "gate": "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE",
            "decision": "START_AS_IS",
            "next_safe_action": {"action": "SAVE_EXACT_OWNER_APPROVAL_AND_ACTIVATE_ONLY_WITH_EXISTING_COMMAND"},
        },
        audit={
            "gate": "INCOMPLETE",
            "complete": False,
            "ready_to_publish": False,
            "next_action": "Use exact activate-only approval phrase.",
        },
    )

    payload = sequence.run(_args(tmp_path))

    assert payload["gate"] == "YELLOW_LINE31_POST_EXPERT_SEQUENCE_START_AS_IS_NEEDS_ACTIVATION_NO_WRITE"
    assert payload["next_safe_action"] == "Use exact activate-only approval phrase."


def test_sequence_change_before_start_stays_no_write(monkeypatch, tmp_path: Path) -> None:
    _patch_common(
        monkeypatch,
        tmp_path,
        intake={"gate": "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE", "decision": "CHANGE_BEFORE_START"},
        audit={
            "gate": "INCOMPLETE",
            "complete": False,
            "ready_to_publish": False,
            "next_action": "Scope changes and rerun preflight.",
        },
    )

    payload = sequence.run(_args(tmp_path))

    assert payload["gate"] == "YELLOW_LINE31_POST_EXPERT_SEQUENCE_CHANGES_REQUIRED_NO_WRITE"
    assert payload["production_db_or_workbook_write_attempted"] is False


def test_sequence_red_intake_stops(monkeypatch, tmp_path: Path) -> None:
    _patch_common(
        monkeypatch,
        tmp_path,
        intake={"gate": "RED_LINE31_EXPERT_ANSWER_AMBIGUOUS_NO_WRITE", "decision": "UNCLASSIFIED"},
        audit={
            "gate": "INCOMPLETE",
            "complete": False,
            "ready_to_publish": False,
            "next_action": "Resolve ambiguous answer.",
        },
    )

    payload = sequence.run(_args(tmp_path))

    assert payload["gate"] == "RED_LINE31_POST_EXPERT_SEQUENCE_STOPPED_NO_WRITE"


def test_sequence_cli_outputs_json_against_current_empty_answer_folder() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_line31_post_expert_answer_sequence.py",
            "--run-id",
            "pytest_current_empty_answer_sequence",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["gate"] in {
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE",
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_START_AS_IS_NEEDS_ACTIVATION_NO_WRITE",
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_CHANGES_REQUIRED_NO_WRITE",
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_HOLD_PAUSED_NO_WRITE",
        "YELLOW_LINE31_POST_EXPERT_SEQUENCE_UNCLASSIFIED_NO_WRITE",
        "GREEN_LINE31_POST_EXPERT_SEQUENCE_COMPLETE_AUDIT_READY_NO_WRITE",
    }
    assert payload["meta_write_attempted"] is False
    assert payload["external_write_attempted"] is False
