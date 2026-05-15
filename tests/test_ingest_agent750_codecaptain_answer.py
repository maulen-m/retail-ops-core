import hashlib
import json
from pathlib import Path

from scripts import ingest_agent750_codecaptain_answer as ingest


GREEN_TOKEN = "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE"
YELLOW_TOKEN = "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _json_out(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _assert_review_pack_matches_status(out: dict) -> None:
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert out["latest_completion_audit"] == status["latest_completion_audit"]
    assert out["latest_stopline_triage"] == status["latest_stopline_triage"]
    assert out["latest_answer_search"]["status"] == status["latest_answer_search"]["status"]
    assert (
        out["latest_answer_search"]["canonical_answer_folder"]
        == status["latest_answer_search"]["canonical_answer_folder"]
    )
    assert (
        out["latest_answer_search"]["canonical_answer_files"]
        == status["latest_answer_search"]["canonical_answer_files"]
    )
    assert "~/Downloads" in out["latest_answer_search"]["searched_paths"]
    assert "~/Desktop" in out["latest_answer_search"]["searched_paths"]
    assert "Canonical Answer folder now contains exactly one real Agent750 answer" in out["latest_answer_search"][
        "non_authoritative_hits_summary"
    ]
    assert "Exactly one real CodeCaptain answer Markdown file" in out[
        "latest_answer_search"
    ]["launch_rule"]
    assert out["review_pack"]["path"] == status["review_pack"]["path"]
    assert out["review_pack"]["prompt_sha256"] == status["review_pack"]["prompt_sha256"]
    assert out["review_pack"]["optional_upload_zip"] == status["review_pack"][
        "optional_upload_zip"
    ]
    assert out["review_pack"]["optional_upload_zip_sha256"] == status["review_pack"][
        "optional_upload_zip_sha256"
    ]
    assert out["review_pack"]["optional_upload_zip_actual_sha256"] == status["review_pack"][
        "optional_upload_zip_sha256"
    ]
    assert out["review_pack"]["status_path_json_valid"] is True
    assert out["review_pack"]["status_path_error"] is None
    assert out["review_pack"]["status_review_pack_errors"] == []
    assert out["review_pack_blocking_errors"] == []
    assert out["review_pack"]["optional_upload_zip_sha256_matches"] is True
    assert out["review_pack"]["latest_validator_manifest_json_valid"] is True
    assert out["review_pack"]["latest_validator_manifest_ok"] is True
    assert out["review_pack"]["latest_validator_manifest_errors"] == []
    assert out["review_pack"]["latest_validator_manifest_status_pointer_error"] is None
    assert status["latest_completion_audit"] in out["review_pack"][
        "latest_validator_manifest_status_pointer_terms"
    ]
    assert (
        out["review_pack"]["latest_validator_manifest_status_pointer_terms_match_status"]
        is True
    )
    assert (
        out["review_pack"]["latest_validator_manifest_optional_upload_zip_sha256"]
        == status["review_pack"]["optional_upload_zip_sha256"]
    )
    assert (
        out["review_pack"][
            "latest_validator_manifest_optional_upload_zip_sha256_matches_status"
        ]
        is True
    )
    assert (
        out["review_pack"][
            "latest_validator_manifest_optional_upload_zip_source_bytes_match"
        ]
        is True
    )


def test_ingest_answer_dry_run_validates_without_copying(tmp_path, capsys):
    source = _write(tmp_path / "answer.md", f"Decision: {GREEN_TOKEN}\n")
    answer_dir = tmp_path / "Answer"

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir)])

    out = _json_out(capsys)
    assert rc == 0
    assert out["ok"] is True
    assert out["action"] == "dry_run"
    assert out["applied"] is False
    assert out["decision_token"] == GREEN_TOKEN
    assert out["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    _assert_review_pack_matches_status(out)
    assert not (answer_dir / ingest.DEFAULT_DEST_NAME).exists()


def test_ingest_answer_apply_copies_to_standard_filename(tmp_path, capsys):
    source = _write(tmp_path / "answer.md", f"Gate: {YELLOW_TOKEN}\n")
    answer_dir = tmp_path / "Answer"

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply"])

    out = _json_out(capsys)
    destination = answer_dir / ingest.DEFAULT_DEST_NAME
    assert rc == 0
    assert out["ok"] is True
    assert out["action"] == "copied"
    assert out["applied"] is True
    assert out["decision_token"] == YELLOW_TOKEN
    assert out["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    _assert_review_pack_matches_status(out)
    assert destination.read_text(encoding="utf-8") == f"Gate: {YELLOW_TOKEN}\n"


def test_ingest_answer_apply_refreshes_answer_search_after_copy(tmp_path, capsys, monkeypatch):
    source = _write(tmp_path / "answer.md", f"Decision: {GREEN_TOKEN}\n")
    answer_dir = tmp_path / "Answer"
    destination = answer_dir / ingest.DEFAULT_DEST_NAME
    calls = []

    def fake_answer_search():
        calls.append(destination.exists())
        return {
            "status": "test_answer_search",
            "canonical_answer_folder": str(answer_dir),
            "canonical_answer_files": [destination.name] if destination.exists() else [],
            "canonical_answer_real_files": [destination.name] if destination.exists() else [],
        }

    monkeypatch.setattr(ingest, "current_answer_search_info", fake_answer_search)

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply"])

    out = _json_out(capsys)
    assert rc == 0
    assert out["ok"] is True
    assert out["applied"] is True
    assert calls == [False, True]
    assert out["latest_answer_search"]["canonical_answer_files"] == [destination.name]
    assert out["latest_answer_search"]["canonical_answer_real_files"] == [destination.name]
    assert destination.read_text(encoding="utf-8") == f"Decision: {GREEN_TOKEN}\n"


def test_ingest_answer_apply_blocks_canonical_copy_on_db_workbook_boundary_mismatch(
    tmp_path, capsys, monkeypatch
):
    source = _write(tmp_path / "answer.md", f"Decision: {GREEN_TOKEN}\n")
    answer_dir = tmp_path / "CanonicalAnswer"
    destination = answer_dir / ingest.DEFAULT_DEST_NAME
    calls = []

    def fake_check_readiness(**kwargs):
        calls.append(kwargs)
        return ingest.ReadinessResult(
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

    monkeypatch.setattr(ingest, "ANSWER_DIR", answer_dir)
    monkeypatch.setattr(ingest, "check_readiness", fake_check_readiness)

    rc = ingest.main(["--source", str(source), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert out["ok"] is False
    assert out["status"] == "APPLY_BLOCKED_BY_DB_WORKBOOK_BOUNDARY_REVIEW"
    assert out["errors"] == [
        "production_db_sha_mismatch",
        "protected_workbook_sha_mismatch",
    ]
    assert out["applied"] is False
    assert out["decision_token"] == GREEN_TOKEN
    assert out["boundary_readiness"]["errors"] == [
        "missing_codecaptain_answer_file",
        "production_db_sha_mismatch",
        "protected_workbook_sha_mismatch",
    ]
    assert out["boundary_readiness"]["db_sha256"] == "current-db-sha"
    assert out["boundary_readiness"]["workbook_sha256"] == "current-workbook-sha"
    assert out["boundary_readiness"]["expected_db_sha256"] == "reviewed-db-sha"
    assert out["boundary_readiness"]["expected_workbook_sha256"] == "reviewed-workbook-sha"
    assert calls[0]["answer_dir"] == answer_dir
    assert calls[0]["expected_db_sha256"] == ingest.DEFAULT_DB_SHA256
    assert calls[0]["expected_workbook_sha256"] == ingest.DEFAULT_WORKBOOK_SHA256
    _assert_review_pack_matches_status(out)
    assert not destination.exists()


def test_ingest_answer_preserves_codecaptain_filename_when_valid(tmp_path, capsys):
    source = _write(tmp_path / "CodeCaptain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    answer_dir = tmp_path / "Answer"

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply"])

    out = _json_out(capsys)
    assert rc == 0
    assert out["destination"].endswith("CodeCaptain_AGENT750.md")
    assert (answer_dir / "CodeCaptain_AGENT750.md").exists()


def test_ingest_answer_rejects_tokenless_answer(tmp_path, capsys):
    source = _write(tmp_path / "answer.md", "Looks approved but no exact decision line.\n")

    rc = ingest.main(["--source", str(source), "--answer-dir", str(tmp_path / "Answer"), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert out["ok"] is False
    assert "missing_codecaptain_decision_token" in out["errors"]
    assert out["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    _assert_review_pack_matches_status(out)


def test_ingest_answer_blocks_unhealthy_review_pack_before_copy(tmp_path, capsys, monkeypatch):
    source = _write(tmp_path / "answer.md", f"Decision: {GREEN_TOKEN}\n")
    answer_dir = tmp_path / "Answer"
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
    monkeypatch.setattr(ingest, "current_review_pack_info", lambda: bad_review_pack)

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert out["ok"] is False
    assert out["applied"] is False
    assert "review_pack_unhealthy" in out["errors"]
    assert "status_review_pack_optional_upload_zip_not_string" in out["errors"]
    assert "optional_upload_zip_missing" in out["errors"]
    assert "latest_validator_manifest_missing" in out["errors"]
    assert out["review_pack"] == bad_review_pack
    assert "status_review_pack_optional_upload_zip_not_string" in out[
        "review_pack_blocking_errors"
    ]
    assert not (answer_dir / ingest.DEFAULT_DEST_NAME).exists()


def test_ingest_answer_rejects_readme_even_with_valid_token(tmp_path, capsys):
    source = _write(tmp_path / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md", f"Decision: {GREEN_TOKEN}\n")

    rc = ingest.main(["--source", str(source), "--answer-dir", str(tmp_path / "Answer"), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert out["ok"] is False
    assert "source_filename_reserved_for_instructions" in out["errors"]


def test_ingest_answer_rejects_negated_green_on_gate_line(tmp_path, capsys):
    source = _write(tmp_path / "answer.md", f"Gate: do not use {GREEN_TOKEN} yet.\n")

    rc = ingest.main(["--source", str(source), "--answer-dir", str(tmp_path / "Answer"), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert "missing_codecaptain_decision_token" in out["errors"]


def test_ingest_answer_rejects_existing_answer_without_replace(tmp_path, capsys):
    answer_dir = tmp_path / "Answer"
    _write(answer_dir / "Code_Captain_existing.md", f"Decision: {YELLOW_TOKEN}\n")
    source = _write(tmp_path / "new_answer.md", f"Decision: {GREEN_TOKEN}\n")

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply"])

    out = _json_out(capsys)
    assert rc == 2
    assert "existing_codecaptain_answer_file_present" in out["errors"]
    _assert_review_pack_matches_status(out)
    assert not (answer_dir / ingest.DEFAULT_DEST_NAME).exists()


def test_ingest_answer_allows_replace_of_existing_answer(tmp_path, capsys):
    answer_dir = tmp_path / "Answer"
    _write(answer_dir / ingest.DEFAULT_DEST_NAME, f"Decision: {YELLOW_TOKEN}\n")
    source = _write(tmp_path / "new_answer.md", f"Decision: {GREEN_TOKEN}\n")

    rc = ingest.main(["--source", str(source), "--answer-dir", str(answer_dir), "--apply", "--replace"])

    out = _json_out(capsys)
    assert rc == 0
    assert out["action"] == "copied"
    assert (answer_dir / ingest.DEFAULT_DEST_NAME).read_text(encoding="utf-8") == f"Decision: {GREEN_TOKEN}\n"

    conflicting_answer_dir = tmp_path / "ConflictingAnswer"
    existing = _write(conflicting_answer_dir / "Code_Captain_existing.md", f"Decision: {YELLOW_TOKEN}\n")
    conflicting_source = _write(tmp_path / "new_conflicting_answer.md", f"Decision: {GREEN_TOKEN}\n")

    rc = ingest.main(
        [
            "--source",
            str(conflicting_source),
            "--answer-dir",
            str(conflicting_answer_dir),
            "--apply",
            "--replace",
        ]
    )

    out = _json_out(capsys)
    assert rc == 2
    assert "replace_would_leave_existing_codecaptain_answer_file" in out["errors"]
    _assert_review_pack_matches_status(out)
    assert not (conflicting_answer_dir / ingest.DEFAULT_DEST_NAME).exists()
    assert existing.read_text(encoding="utf-8") == f"Decision: {YELLOW_TOKEN}\n"

    directory_answer_dir = tmp_path / "DirectoryAnswer"
    blocked_destination = directory_answer_dir / ingest.DEFAULT_DEST_NAME
    blocked_destination.mkdir(parents=True)
    directory_source = _write(tmp_path / "directory_source.md", f"Decision: {GREEN_TOKEN}\n")

    rc = ingest.main(
        [
            "--source",
            str(directory_source),
            "--answer-dir",
            str(directory_answer_dir),
            "--apply",
            "--replace",
        ]
    )

    out = _json_out(capsys)
    assert rc == 2
    assert "destination_path_not_file" in out["errors"]
    _assert_review_pack_matches_status(out)
    assert not (blocked_destination / "directory_source.md").exists()
