import hashlib
import json
from pathlib import Path

from scripts.check_agent750_launch_readiness import GREEN_TOKEN, ReadinessResult
from scripts import report_agent750_next_action as reporter
from scripts.report_agent750_next_action import (
    CURRENT_STOPLINE_POINTER,
    WAITING_POINTER,
    build_next_action,
)
from scripts.build_agent750_stopline_checkpoint import (
    checkpoint_filename,
    refresh_current_surfaces,
    render_checkpoint,
    run_checkpoint_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_next_action_waits_for_missing_codecaptain_answer():
    expected_completion_audit = max(
        (
            REPO_ROOT
            / "docs"
            / "parallel_runs"
            / "2026-05-06_codecaptain_proscope_red_recovery"
        ).glob("ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md")
    )
    expected_latest_audit = max(
        (
            REPO_ROOT
            / "docs"
            / "parallel_runs"
            / "2026-05-06_codecaptain_proscope_red_recovery"
        ).glob("CURRENT_OBJECTIVE_AUDIT_AGENT750_BLOCKED_*.md")
    )
    expected_stopline_triage = max(
        (
            REPO_ROOT
            / "docs"
            / "parallel_runs"
            / "2026-05-06_codecaptain_proscope_red_recovery"
        ).glob("STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_*.md")
    )
    payload = build_next_action(
        ReadinessResult(ok=False, errors=["missing_codecaptain_answer_file"])
    )

    assert payload["status"] == "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER"
    assert payload["local_action_state"] == "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
    assert payload["blocked_until"] == "codecaptain_agent750_exact_green_answer"
    assert payload["current_stopline_pointer"].endswith("CURRENT_AGENT750_STOPLINE.md")
    assert payload["waiting_pointer"] == str(WAITING_POINTER)
    assert payload["latest_completion_audit"] == str(expected_completion_audit)
    assert payload["latest_current_objective_audit"] == str(expected_latest_audit)
    assert payload["latest_stopline_triage"] == str(expected_stopline_triage)
    assert any("CURRENT_AGENT750_STOPLINE.md" in step for step in payload["next_steps"])
    assert any("WAITING_FOR_EXTERNAL_REVIEW_AGENT750.md" in step for step in payload["next_steps"])
    assert any("ACTIVE_OBJECTIVE_COMPLETION_AUDIT" in step for step in payload["next_steps"])
    assert any("CURRENT_OBJECTIVE_AUDIT_AGENT750_BLOCKED" in step for step in payload["next_steps"])
    assert any("STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750" in step for step in payload["next_steps"])
    assert any("Preferred upload ZIP:" in step for step in payload["next_steps"])
    assert any("ZIP manifest:" in step for step in payload["next_steps"])
    assert any("Validator manifest:" in step for step in payload["next_steps"])
    assert any("resume_agent750_to_753.py --source /path/to/CodeCaptain_answer.md" in step for step in payload["next_steps"])
    assert any("resume_agent750_to_753.py --launch" in step for step in payload["next_steps"])
    assert any("ingest_agent750_codecaptain_answer.py" in step for step in payload["next_steps"])
    assert "No --visibility-pane LIVE for this rollout." in payload["hard_stoplines"]
    assert "No human-visible tmux visibility panes for this rollout." in payload["hard_stoplines"]
    assert "No orchestrator_ping_mode=chat for this rollout." in payload["hard_stoplines"]
    assert "No orchestrator_ping_mode=receiver for this rollout." in payload["hard_stoplines"]
    assert "No manual chat-pane pings by execution agents." in payload["hard_stoplines"]
    assert "Do not proceed if tmux kill-switch files are missing." in payload["hard_stoplines"]


def test_next_action_stopline_pointer_matches_current_gate_status():
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))

    payload = build_next_action(
        ReadinessResult(
            ok=False,
            errors=["production_db_sha_mismatch", "protected_workbook_sha_mismatch"],
            db_sha256=status["current_boundary"]["production_db_sha256"],
            workbook_sha256=status["current_boundary"]["protected_workbook_sha256"],
            expected_db_sha256=status["reviewed_boundary_before_db_drift"]["production_db_sha256"],
            expected_workbook_sha256=status["reviewed_boundary_before_db_drift"]["protected_workbook_sha256"],
            db_sha256_matches_expected=False,
            workbook_sha256_matches_expected=False,
        )
    )

    assert payload["current_stopline_pointer"] == status["current_stopline_pointer"]
    assert payload["status"] == "BLOCKED_BY_DB_BOUNDARY_REVIEW"
    assert payload["local_action_state"] == "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED"
    assert payload["blocked_until"] == "current_production_db_boundary_review_resolved"
    assert payload["waiting_pointer"] == status["waiting_pointer"]
    assert payload["latest_completion_audit"] == status["latest_completion_audit"]
    assert payload["latest_stopline_triage"] == status["latest_stopline_triage"]
    assert payload["latest_answer_search"]["status"] == status["latest_answer_search"]["status"]
    assert (
        payload["latest_answer_search"]["canonical_answer_folder"]
        == status["latest_answer_search"]["canonical_answer_folder"]
    )
    assert (
        payload["latest_answer_search"]["canonical_answer_files"]
        == status["latest_answer_search"]["canonical_answer_files"]
    )
    assert "~/Downloads" in payload["latest_answer_search"]["searched_paths"]
    assert "~/Desktop" in payload["latest_answer_search"]["searched_paths"]
    assert "Canonical Answer folder now contains exactly one real Agent750 answer" in payload["latest_answer_search"][
        "non_authoritative_hits_summary"
    ]
    assert "Exactly one real CodeCaptain answer Markdown file" in payload[
        "latest_answer_search"
    ]["launch_rule"]
    assert payload["review_pack"]["path"] == status["review_pack"]["path"]
    assert (
        payload["review_pack"]["optional_upload_zip"]
        == status["review_pack"]["optional_upload_zip"]
    )
    assert (
        payload["review_pack"]["optional_upload_zip_manifest"]
        == status["review_pack"]["optional_upload_zip_manifest"]
    )
    assert (
        payload["review_pack"]["latest_validator_manifest"]
        == status["review_pack"]["latest_validator_manifest"]
    )
    assert payload["review_pack"]["prompt_sha256"] == status["review_pack"]["prompt_sha256"]
    assert (
        payload["review_pack"]["optional_upload_zip_sha256"]
        == status["review_pack"]["optional_upload_zip_sha256"]
    )
    zip_path = Path(payload["review_pack"]["optional_upload_zip"])
    assert payload["review_pack"]["status_path_json_valid"] is True
    assert payload["review_pack"]["status_path_error"] is None
    assert payload["review_pack"]["optional_upload_zip_exists"] is True
    assert payload["review_pack"]["optional_upload_zip_manifest_exists"] is True
    assert payload["review_pack"]["latest_validator_manifest_exists"] is True
    assert payload["review_pack"]["latest_validator_manifest_json_valid"] is True
    assert payload["review_pack"]["latest_validator_manifest_ok"] is True
    assert payload["review_pack"]["latest_validator_manifest_errors"] == []
    assert payload["review_pack"]["status_review_pack_errors"] == []
    assert payload["review_pack_blocking_errors"] == []
    assert payload["review_pack"]["latest_validator_manifest_status_pointer_error"] is None
    assert status["latest_completion_audit"] in payload["review_pack"][
        "latest_validator_manifest_status_pointer_terms"
    ]
    assert (
        payload["review_pack"]["latest_validator_manifest_status_pointer_terms_match_status"]
        is True
    )
    assert (
        payload["review_pack"]["latest_validator_manifest_optional_upload_zip_sha256"]
        == status["review_pack"]["optional_upload_zip_sha256"]
    )
    assert (
        payload["review_pack"][
            "latest_validator_manifest_optional_upload_zip_sha256_matches_status"
        ]
        is True
    )
    assert (
        payload["review_pack"][
            "latest_validator_manifest_optional_upload_zip_source_bytes_match"
        ]
        is True
    )
    assert payload["review_pack"]["optional_upload_zip_actual_sha256"] == hashlib.sha256(
        zip_path.read_bytes()
    ).hexdigest()
    assert payload["review_pack"]["optional_upload_zip_sha256_matches"] is True
    assert payload["latest_current_objective_audit"] == status["latest_current_objective_audit"]
    assert (
        payload["latest_db_boundary_drift_triage"]
        == status["db_boundary_review"]["latest_content_diff_artifact"]
    )
    assert (
        payload["latest_db_boundary_supplemental_review_request"]
        == status["db_boundary_review"]["supplemental_review_request"]
    )
    assert payload["status"] == "BLOCKED_BY_DB_BOUNDARY_REVIEW"
    assert str(CURRENT_STOPLINE_POINTER) == status["current_stopline_pointer"]
    assert str(WAITING_POINTER) == status["waiting_pointer"]
    assert CURRENT_STOPLINE_POINTER.exists()
    assert WAITING_POINTER.exists()
    assert Path(payload["latest_completion_audit"]).exists()
    assert Path(payload["latest_current_objective_audit"]).exists()
    assert Path(payload["latest_stopline_triage"]).exists()
    assert Path(payload["latest_db_boundary_drift_triage"]).exists()
    assert Path(payload["latest_db_boundary_supplemental_review_request"]).exists()


def test_next_action_combines_missing_answer_and_db_boundary_review():
    payload = build_next_action(
        ReadinessResult(
            ok=False,
            errors=[
                "missing_codecaptain_answer_file",
                "production_db_sha_mismatch",
                "protected_workbook_sha_mismatch",
            ],
            db_sha256="current-db-sha",
            workbook_sha256="current-workbook-sha",
            expected_db_sha256="reviewed-db-sha",
            expected_workbook_sha256="reviewed-workbook-sha",
            db_sha256_matches_expected=False,
            workbook_sha256_matches_expected=False,
        )
    )

    assert payload["status"] == "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER_AND_DB_BOUNDARY_REVIEW"
    assert payload["local_action_state"] == "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
    assert payload["blocked_until"] == "codecaptain_agent750_exact_green_answer_and_db_boundary_review"
    assert "production_db_sha_mismatch" in payload["errors"]
    assert "protected_workbook_sha_mismatch" in payload["errors"]
    assert payload["db_sha256"] == "current-db-sha"
    assert payload["workbook_sha256"] == "current-workbook-sha"
    assert payload["expected_db_sha256"] == "reviewed-db-sha"
    assert payload["expected_workbook_sha256"] == "reviewed-workbook-sha"
    assert payload["db_sha256_matches_expected"] is False
    assert payload["workbook_sha256_matches_expected"] is False
    assert any("review the current DB/workbook boundary" in step for step in payload["next_steps"])
    assert payload["latest_db_boundary_drift_triage"].endswith("DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md")
    assert payload["latest_db_boundary_supplemental_review_request"].endswith(
        "CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md"
    )
    assert any("DB-boundary drift triage supplement" in step for step in payload["next_steps"])
    assert any("DB-boundary supplemental review request" in step for step in payload["next_steps"])


def test_next_action_ready_state_still_uses_guarded_no_live_launcher():
    payload = build_next_action(
        ReadinessResult(ok=True, decision_token=GREEN_TOKEN, answer_files=["Code_Captain_AGENT750.md"])
    )

    assert payload["status"] == "READY_FOR_GUARDED_AGENT751_752_753_LAUNCH"
    assert payload["review_pack_blocking_errors"] == []
    assert any("resume_agent750_to_753.py --launch" in step for step in payload["next_steps"])
    assert any("launch_agent751_753_after_agent750.py" in step for step in payload["next_steps"])
    assert any("list_agent751_753_candidate_panes.py" in step for step in payload["next_steps"])
    launch_steps = [step for step in payload["next_steps"] if "launch_agent751_753_after_agent750.py" in step]
    assert all("--visibility-pane LIVE" not in step for step in launch_steps)
    assert any("Do not add --visibility-pane" in step for step in payload["next_steps"])
    assert any("do not use orchestrator_ping_mode=chat" in step for step in payload["next_steps"])
    assert any("or receiver" in step for step in payload["next_steps"])


def test_next_action_ready_green_blocks_unhealthy_review_pack(monkeypatch):
    bad_review_pack = {
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": None,
        "status_review_pack_errors": ["status_review_pack_optional_upload_zip_not_string"],
        "optional_upload_zip_exists": False,
        "optional_upload_zip_sha256_matches": False,
        "optional_upload_zip_manifest_exists": False,
        "latest_validator_manifest_exists": False,
        "latest_validator_manifest_json_valid": False,
        "latest_validator_manifest_ok": None,
        "latest_validator_manifest_errors": [],
        "latest_validator_manifest_status_pointer_error": None,
        "latest_validator_manifest_status_pointer_terms_match_status": False,
        "latest_validator_manifest_optional_upload_zip_sha256_matches_status": False,
        "latest_validator_manifest_optional_upload_zip_source_bytes_match": False,
    }
    monkeypatch.setattr(reporter, "current_review_pack_info", lambda: bad_review_pack)

    payload = reporter.build_next_action(
        ReadinessResult(
            ok=True,
            decision_token=GREEN_TOKEN,
            answer_files=["Code_Captain_AGENT750.md"],
        )
    )

    assert payload["status"] == "BLOCKED_BY_REVIEW_PACK"
    assert payload["local_action_state"] == "LOCAL_REVIEW_PACK_REPAIR_REQUIRED"
    assert payload["blocked_until"] == "agent750_review_pack_evidence_healthy"
    assert "status_review_pack_optional_upload_zip_not_string" in payload[
        "review_pack_blocking_errors"
    ]
    assert "optional_upload_zip_missing" in payload["review_pack_blocking_errors"]
    assert "latest_validator_manifest_missing" in payload["review_pack_blocking_errors"]
    assert "Do not launch Agents751/752/753." in payload["next_steps"]
    assert any("validate_agent750_review_pack.py" in step for step in payload["next_steps"])


def test_next_action_blocks_if_ok_without_exact_green_token():
    payload = build_next_action(
        ReadinessResult(ok=True, decision_token="YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE")
    )

    assert payload["status"] == "BLOCKED_BY_DECISION_TOKEN"
    assert payload["decision_token"] == "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
    assert "Do not launch Agents751/752/753." in payload["next_steps"]
    assert any(GREEN_TOKEN in step for step in payload["next_steps"])


def test_next_action_yellow_and_red_do_not_launch():
    yellow = build_next_action(
        ReadinessResult(ok=False, errors=["codecaptain_answer_requires_fix_before_launch"])
    )
    red = build_next_action(ReadinessResult(ok=False, errors=["codecaptain_answer_red_stopline"]))

    assert yellow["status"] == "BLOCKED_BY_CODECAPTAIN_YELLOW_FIX_REQUIRED"
    assert red["status"] == "BLOCKED_BY_CODECAPTAIN_RED_STOPLINE"
    assert "Do not launch Agents751/752/753." in yellow["next_steps"]
    assert "Do not launch Agents751/752/753." in red["next_steps"]


def test_next_action_other_readiness_errors_stop_before_launch():
    payload = build_next_action(
        ReadinessResult(
            ok=False,
            errors=["production_db_sha_mismatch", "protected_workbook_sha_mismatch"],
        )
    )

    assert payload["status"] == "BLOCKED_BY_DB_BOUNDARY_REVIEW"
    assert payload["local_action_state"] == "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED"
    assert payload["blocked_until"] == "current_production_db_boundary_review_resolved"
    assert any("Review the current production DB/workbook boundary" in step for step in payload["next_steps"])
    assert any("DB-boundary drift triage supplement" in step for step in payload["next_steps"])
    assert any("DB-boundary supplemental review request" in step for step in payload["next_steps"])


def test_stopline_checkpoint_renderer_captures_blockers_and_no_launch_rules():
    payload = {
        "status": "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER_AND_DB_BOUNDARY_REVIEW",
        "readiness_ok": False,
        "errors": [
            "missing_codecaptain_answer_file",
            "production_db_sha_mismatch",
            "protected_workbook_sha_mismatch",
        ],
        "answer_files": [],
        "decision_token": None,
        "db_sha256": "current-db",
        "expected_db_sha256": "expected-db",
        "db_sha256_matches_expected": False,
        "workbook_sha256": "current-workbook",
        "expected_workbook_sha256": "expected-workbook",
        "workbook_sha256_matches_expected": False,
        "downstream_artifacts": [],
        "misplaced_answer_files": [],
        "unexpected_answer_files": [],
        "proof_window_lock_exists": False,
        "tmux_visibility_kill_switch_exists": True,
        "tmux_completion_ping_kill_switch_exists": True,
        "review_pack_blocking_errors": [],
        "latest_answer_search": {
            "canonical_answer_folder": "/tmp/Answer",
            "canonical_answer_scan_observed_at_local": "2026-05-10T12:03:04+0500",
            "canonical_answer_files": ["README_SAVE_CODECAPTAIN_ANSWER_HERE.md"],
            "canonical_answer_real_files": [],
        },
        "review_pack": {
            "allowed_green_token": GREEN_TOKEN,
            "latest_validator_manifest_ok": True,
            "optional_upload_zip_sha256": "zip-sha",
            "latest_validator_manifest_optional_upload_zip_source_bytes_match": True,
        },
    }

    text = render_checkpoint(payload)

    assert checkpoint_filename(payload) == "CURRENT_STOPLINE_CHECKPOINT_AGENT750_WAITING_20260510_120304.md"
    assert "Prompt-To-Artifact Checklist" in text
    assert "missing_codecaptain_answer_file" in text
    assert "production_db_sha_mismatch" in text
    assert "protected_workbook_sha_mismatch" in text
    assert "`decision_token=null`" in text
    assert "- Decision token: `null`" in text
    assert "Current DB SHA `current-db`; expected SHA `expected-db`" in text
    assert "Current workbook SHA `current-workbook`; expected SHA `expected-workbook`" in text
    assert "Real answer files: none" in text
    assert "no Agent751/752/753 launch" in text
    assert "no `--visibility-pane LIVE`" in text


def test_stopline_checkpoint_run_path_uses_scan_timestamp(tmp_path):
    payload = {
        "latest_answer_search": {
            "canonical_answer_scan_observed_at_local": "2026-05-10T12:11:12+0500",
        }
    }

    assert run_checkpoint_path(payload, tmp_path) == (
        tmp_path / "CURRENT_STOPLINE_CHECKPOINT_AGENT750_WAITING_20260510_121112.md"
    )


def test_stopline_checkpoint_refresh_updates_only_current_doc_pointers(tmp_path):
    status_path = tmp_path / "current_gate_status_agent750_waiting_codecaptain.json"
    current_stopline = tmp_path / "CURRENT_AGENT750_STOPLINE.md"
    waiting_pointer = tmp_path / "WAITING_FOR_EXTERNAL_REVIEW_AGENT750.md"
    checkpoint_path = tmp_path / "CURRENT_STOPLINE_CHECKPOINT_AGENT750_WAITING_20260510_121314.md"
    payload = {
        "status": "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER_AND_DB_BOUNDARY_REVIEW",
        "local_action_state": "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION",
        "blocked_until": "codecaptain_agent750_exact_green_answer_and_db_boundary_review",
        "errors": [
            "missing_codecaptain_answer_file",
            "production_db_sha_mismatch",
            "protected_workbook_sha_mismatch",
        ],
        "db_sha256": "current-db",
        "workbook_sha256": "current-workbook",
        "latest_answer_search": {
            "status": "NO_REAL_AGENT750_CODECAPTAIN_ANSWER_FOUND",
            "canonical_answer_folder": "/tmp/Answer",
            "canonical_answer_scan_observed_at_local": "2026-05-10T12:13:14+0500",
            "canonical_answer_files": ["README_SAVE_CODECAPTAIN_ANSWER_HERE.md"],
            "canonical_answer_real_files": [],
            "canonical_answer_files_source": "live_filesystem",
            "canonical_answer_files_match_status": True,
            "searched_paths": ["~/Downloads"],
            "content_scan_terms": [GREEN_TOKEN],
            "non_authoritative_hits_summary": "None is a standalone Agent750 answer",
            "launch_rule": "Only exactly one real CodeCaptain answer Markdown file counts.",
        },
    }
    status_path.write_text(
        json.dumps(
            {
                "last_checked_local": "old",
                "status": "old",
                "local_action_state": "old",
                "blocked_until": "old",
                "current_blockers": [],
                "current_boundary": {
                    "production_db_sha256": "old-db",
                    "protected_workbook_sha256": "old-workbook",
                },
                "latest_answer_search": {
                    "status": "old",
                    "canonical_answer_files": [],
                },
                "latest_stopline_checkpoint": "old-checkpoint",
            }
        ),
        encoding="utf-8",
    )
    current_stopline.write_text(
        "Checked at: `old`\n"
        "- Latest stopline checkpoint: `old-checkpoint`\n"
        "Do not launch Agent751.\n",
        encoding="utf-8",
    )
    waiting_pointer.write_text(
        "Current old readiness remains blocked with:\n"
        "- `missing_codecaptain_answer_file`\n",
        encoding="utf-8",
    )

    touched = refresh_current_surfaces(
        payload,
        checkpoint_path,
        status_path=status_path,
        current_stopline_path=current_stopline,
        waiting_pointer_path=waiting_pointer,
    )
    refreshed_status = json.loads(status_path.read_text(encoding="utf-8"))

    assert touched == [status_path, current_stopline, waiting_pointer]
    assert refreshed_status["last_checked_local"] == "2026-05-10T12:13:14+0500"
    assert refreshed_status["latest_stopline_checkpoint"] == str(checkpoint_path)
    assert refreshed_status["current_blockers"] == payload["errors"]
    assert refreshed_status["current_boundary"]["production_db_sha256"] == "current-db"
    assert refreshed_status["current_boundary"]["protected_workbook_sha256"] == "current-workbook"
    assert refreshed_status["latest_answer_search"]["canonical_answer_real_files"] == []
    assert refreshed_status["latest_answer_search"]["canonical_answer_files_source"] == "live_filesystem"
    assert f"Checked at: `2026-05-10T12:13:14+0500`" in current_stopline.read_text(encoding="utf-8")
    assert str(checkpoint_path) in current_stopline.read_text(encoding="utf-8")
    assert "Current 2026-05-10 12:13 +0500 readiness remains blocked with:" in waiting_pointer.read_text(
        encoding="utf-8"
    )
    assert "Do not launch Agent751." in current_stopline.read_text(encoding="utf-8")
