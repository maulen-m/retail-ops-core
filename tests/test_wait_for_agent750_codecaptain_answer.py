import hashlib
import json
from pathlib import Path

from scripts.check_agent750_launch_readiness import GREEN_TOKEN, ReadinessResult
from scripts.wait_for_agent750_codecaptain_answer import wait_for_readiness


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_waiter_returns_ready_immediately_without_sleeping():
    sleep_calls = []

    result = wait_for_readiness(
        readiness_fn=lambda: ReadinessResult(ok=True, decision_token=GREEN_TOKEN),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        monotonic_fn=lambda: 0.0,
        timeout_seconds=30.0,
        interval_seconds=5.0,
    )

    assert result.return_code == 0
    assert result.payload["status"] == "READY_FOR_GUARDED_AGENT751_752_753_LAUNCH"
    assert result.payload["timed_out"] is False
    assert sleep_calls == []


def test_waiter_polls_until_ready_before_timeout():
    states = [
        ReadinessResult(ok=False, errors=["missing_codecaptain_answer_file"]),
        ReadinessResult(ok=True, decision_token=GREEN_TOKEN),
    ]
    sleep_calls = []
    times = iter([0.0, 0.0, 1.0])

    result = wait_for_readiness(
        readiness_fn=lambda: states.pop(0),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        monotonic_fn=lambda: next(times),
        timeout_seconds=30.0,
        interval_seconds=5.0,
    )

    assert result.return_code == 0
    assert result.payload["status"] == "READY_FOR_GUARDED_AGENT751_752_753_LAUNCH"
    assert result.payload["poll_count"] == 2
    assert sleep_calls == [5.0]


def test_waiter_times_out_read_only_when_answer_missing():
    sleep_calls = []
    times = iter([0.0, 0.0, 11.0])

    result = wait_for_readiness(
        readiness_fn=lambda: ReadinessResult(ok=False, errors=["missing_codecaptain_answer_file"]),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        monotonic_fn=lambda: next(times),
        timeout_seconds=10.0,
        interval_seconds=5.0,
    )

    assert result.return_code == 2
    assert result.payload["status"] == "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER"
    assert result.payload["timed_out"] is True
    assert result.payload["hard_stoplines"]
    assert sleep_calls == [5.0]


def test_waiter_single_check_when_timeout_zero():
    sleep_calls = []
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

    result = wait_for_readiness(
        readiness_fn=lambda: ReadinessResult(ok=False, errors=["missing_codecaptain_answer_file"]),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        monotonic_fn=lambda: 0.0,
        timeout_seconds=0.0,
        interval_seconds=5.0,
    )

    assert result.return_code == 2
    assert result.payload["timed_out"] is False
    assert result.payload["poll_count"] == 1
    assert result.payload["latest_completion_audit"] == str(expected_completion_audit)
    assert result.payload["latest_current_objective_audit"] == str(expected_latest_audit)
    assert any("ACTIVE_OBJECTIVE_COMPLETION_AUDIT" in step for step in result.payload["next_steps"])
    assert any("CURRENT_OBJECTIVE_AUDIT_AGENT750_BLOCKED" in step for step in result.payload["next_steps"])
    assert sleep_calls == []


def test_waiter_combined_blocker_includes_db_boundary_review_artifacts():
    sleep_calls = []
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))

    result = wait_for_readiness(
        readiness_fn=lambda: ReadinessResult(
            ok=False,
            errors=["missing_codecaptain_answer_file", "production_db_sha_mismatch"],
        ),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
        monotonic_fn=lambda: 0.0,
        timeout_seconds=0.0,
        interval_seconds=5.0,
    )

    assert result.return_code == 2
    assert result.payload["status"] == "WAITING_FOR_CODECAPTAIN_AGENT750_ANSWER_AND_DB_BOUNDARY_REVIEW"
    assert result.payload["latest_completion_audit"] == status["latest_completion_audit"]
    assert result.payload["latest_stopline_triage"] == status["latest_stopline_triage"]
    assert any(
        status["latest_stopline_triage"] in step for step in result.payload["next_steps"]
    )
    assert result.payload["latest_answer_search"]["status"] == status["latest_answer_search"]["status"]
    assert (
        result.payload["latest_answer_search"]["canonical_answer_folder"]
        == status["latest_answer_search"]["canonical_answer_folder"]
    )
    assert (
        result.payload["latest_answer_search"]["canonical_answer_files"]
        == status["latest_answer_search"]["canonical_answer_files"]
    )
    assert "~/Downloads" in result.payload["latest_answer_search"]["searched_paths"]
    assert "~/Desktop" in result.payload["latest_answer_search"]["searched_paths"]
    assert "Canonical Answer folder now contains exactly one real Agent750 answer" in result.payload[
        "latest_answer_search"
    ]["non_authoritative_hits_summary"]
    assert "Exactly one real CodeCaptain answer Markdown file" in result.payload[
        "latest_answer_search"
    ]["launch_rule"]
    assert result.payload["latest_db_boundary_drift_triage"].endswith(
        "DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md"
    )
    assert result.payload["latest_db_boundary_supplemental_review_request"].endswith(
        "CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md"
    )
    assert result.payload["review_pack"]["optional_upload_zip"] == status["review_pack"][
        "optional_upload_zip"
    ]
    assert result.payload["review_pack"]["optional_upload_zip_sha256"] == status[
        "review_pack"
    ]["optional_upload_zip_sha256"]
    assert result.payload["review_pack"]["optional_upload_zip_manifest"] == status[
        "review_pack"
    ]["optional_upload_zip_manifest"]
    assert result.payload["review_pack"]["latest_validator_manifest"] == status[
        "review_pack"
    ]["latest_validator_manifest"]
    assert result.payload["review_pack"]["prompt_sha256"] == status["review_pack"][
        "prompt_sha256"
    ]
    zip_path = Path(result.payload["review_pack"]["optional_upload_zip"])
    assert result.payload["review_pack"]["status_path_json_valid"] is True
    assert result.payload["review_pack"]["status_path_error"] is None
    assert result.payload["review_pack"]["optional_upload_zip_exists"] is True
    assert result.payload["review_pack"]["optional_upload_zip_manifest_exists"] is True
    assert result.payload["review_pack"]["latest_validator_manifest_exists"] is True
    assert result.payload["review_pack"]["latest_validator_manifest_json_valid"] is True
    assert result.payload["review_pack"]["latest_validator_manifest_ok"] is True
    assert result.payload["review_pack"]["latest_validator_manifest_errors"] == []
    assert result.payload["review_pack"]["latest_validator_manifest_status_pointer_error"] is None
    assert status["latest_completion_audit"] in result.payload["review_pack"][
        "latest_validator_manifest_status_pointer_terms"
    ]
    assert (
        result.payload["review_pack"][
            "latest_validator_manifest_status_pointer_terms_match_status"
        ]
        is True
    )
    assert (
        result.payload["review_pack"][
            "latest_validator_manifest_optional_upload_zip_sha256"
        ]
        == status["review_pack"]["optional_upload_zip_sha256"]
    )
    assert (
        result.payload["review_pack"][
            "latest_validator_manifest_optional_upload_zip_sha256_matches_status"
        ]
        is True
    )
    assert (
        result.payload["review_pack"][
            "latest_validator_manifest_optional_upload_zip_source_bytes_match"
        ]
        is True
    )
    assert result.payload["review_pack"]["optional_upload_zip_actual_sha256"] == hashlib.sha256(
        zip_path.read_bytes()
    ).hexdigest()
    assert result.payload["review_pack"]["optional_upload_zip_sha256_matches"] is True
    assert any("Preferred upload ZIP:" in step for step in result.payload["next_steps"])
    assert any("ZIP manifest:" in step for step in result.payload["next_steps"])
    assert any("Validator manifest:" in step for step in result.payload["next_steps"])
    assert any("DB-boundary drift triage supplement" in step for step in result.payload["next_steps"])
    assert any("DB-boundary supplemental review request" in step for step in result.payload["next_steps"])
    assert result.payload["watcher_mode"] == "read_only_no_import_no_launch_no_tmux_ping"
    assert sleep_calls == []
