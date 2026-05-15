import json
from pathlib import Path
from types import SimpleNamespace

from scripts import resume_agent750_to_753 as resume


REPO_ROOT = Path(__file__).resolve().parents[1]


def _result(returncode: int, payload: dict):
    return SimpleNamespace(returncode=returncode, stdout=json.dumps(payload), stderr="")


def _raw_result(returncode: int, stdout: str, stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _has(cmd: list[str], needle: str) -> bool:
    return any(needle in part for part in cmd)


def test_resume_blocks_before_pane_listing_when_readiness_is_missing(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _result(
            2,
            {
                "ok": False,
                "errors": ["missing_codecaptain_answer_file"],
                "answer_files": [],
            },
        )

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_READINESS"
    assert payload["local_action_state"] == "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
    assert payload["blocked_until"] == "codecaptain_agent750_exact_green_answer"
    assert payload["waiting_pointer"].endswith("WAITING_FOR_EXTERNAL_REVIEW_AGENT750.md")
    assert payload["readiness"]["errors"] == ["missing_codecaptain_answer_file"]
    assert len(calls) == 1
    assert _has(calls[0], "check_agent750_launch_readiness.py")


def test_resume_combines_missing_answer_and_db_boundary_block(monkeypatch, capsys):
    calls = []
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))

    def fake_run(cmd):
        calls.append(cmd)
        return _result(
            2,
            {
                "ok": False,
                "errors": ["missing_codecaptain_answer_file", "production_db_sha_mismatch"],
                "answer_files": [],
                "db_sha256": "current-db-sha",
                "workbook_sha256": "current-workbook-sha",
                "expected_db_sha256": "reviewed-db-sha",
                "expected_workbook_sha256": "current-workbook-sha",
                "db_sha256_matches_expected": False,
                "workbook_sha256_matches_expected": True,
            },
        )

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_READINESS"
    assert payload["local_action_state"] == "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
    assert payload["blocked_until"] == "codecaptain_agent750_exact_green_answer_and_db_boundary_review"
    assert payload["db_sha256"] == "current-db-sha"
    assert payload["workbook_sha256"] == "current-workbook-sha"
    assert payload["expected_db_sha256"] == "reviewed-db-sha"
    assert payload["expected_workbook_sha256"] == "current-workbook-sha"
    assert payload["db_sha256_matches_expected"] is False
    assert payload["workbook_sha256_matches_expected"] is True
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
    assert payload["latest_db_boundary_drift_triage"].endswith(
        "DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md"
    )
    assert payload["latest_db_boundary_supplemental_review_request"].endswith(
        "CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md"
    )
    assert payload["review_pack"]["path"] == status["review_pack"]["path"]
    assert payload["review_pack"]["prompt_sha256"] == status["review_pack"]["prompt_sha256"]
    assert payload["review_pack"]["optional_upload_zip"] == status["review_pack"][
        "optional_upload_zip"
    ]
    assert payload["review_pack"]["optional_upload_zip_sha256"] == status["review_pack"][
        "optional_upload_zip_sha256"
    ]
    assert payload["review_pack"]["optional_upload_zip_actual_sha256"] == status[
        "review_pack"
    ]["optional_upload_zip_sha256"]
    assert payload["review_pack"]["optional_upload_zip_sha256_matches"] is True
    assert payload["review_pack"]["optional_upload_zip_manifest"] == status["review_pack"][
        "optional_upload_zip_manifest"
    ]
    assert payload["review_pack"]["latest_validator_manifest"] == status["review_pack"][
        "latest_validator_manifest"
    ]
    assert payload["review_pack"]["status_path_json_valid"] is True
    assert payload["review_pack"]["status_path_error"] is None
    assert payload["review_pack"]["optional_upload_zip_exists"] is True
    assert payload["review_pack"]["optional_upload_zip_manifest_exists"] is True
    assert payload["review_pack"]["latest_validator_manifest_exists"] is True
    assert payload["review_pack"]["latest_validator_manifest_json_valid"] is True
    assert payload["review_pack"]["latest_validator_manifest_ok"] is True
    assert payload["review_pack"]["latest_validator_manifest_errors"] == []
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
    assert payload["readiness"]["errors"] == [
        "missing_codecaptain_answer_file",
        "production_db_sha_mismatch",
    ]
    assert len(calls) == 1
    assert _has(calls[0], "check_agent750_launch_readiness.py")


def test_resume_surfaces_db_boundary_review_without_missing_answer(monkeypatch, capsys):
    def fake_run(cmd):
        return _result(
            2,
            {
                "ok": False,
                "errors": ["production_db_sha_mismatch"],
                "answer_files": ["/tmp/Code_Captain_AGENT750.md"],
            },
        )

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_READINESS"
    assert payload["local_action_state"] == "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED"
    assert payload["blocked_until"] == "current_production_db_boundary_review_resolved"
    assert payload["latest_completion_audit"].endswith(
        "ACTIVE_OBJECTIVE_COMPLETION_AUDIT_20260510_090511.md"
    )
    assert payload["latest_stopline_triage"].endswith(
        "STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_20260510_124512.md"
    )
    assert payload["latest_db_boundary_drift_triage"].endswith(
        "DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md"
    )
    assert payload["latest_db_boundary_supplemental_review_request"].endswith(
        "CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md"
    )


def test_resume_rejects_apply_import_without_source(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(resume, "run_command", lambda cmd: calls.append(cmd))

    rc = resume.main(["--apply-import"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "INVALID_ARGUMENTS"
    assert payload["errors"] == ["apply_import_requires_source"]
    assert calls == []


def test_resume_rejects_replace_without_source(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(resume, "run_command", lambda cmd: calls.append(cmd))

    rc = resume.main(["--replace"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "INVALID_ARGUMENTS"
    assert payload["errors"] == ["replace_requires_source"]
    assert calls == []


def test_resume_rejects_apply_import_and_launch_same_run(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(resume, "run_command", lambda cmd: calls.append(cmd))

    rc = resume.main(
        [
            "--source",
            "/tmp/Code_Captain_AGENT750.md",
            "--apply-import",
            "--launch",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "INVALID_ARGUMENTS"
    assert payload["errors"] == ["launch_requires_separate_run_after_apply_import"]
    assert calls == []


def test_resume_source_dry_run_stops_before_readiness_until_apply(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _result(
            0,
            {
                "ok": True,
                "action": "dry_run",
                "decision_token": "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE",
            },
        )

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--source", "/tmp/Code_Captain_AGENT750.md"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "IMPORT_DRY_RUN_OK_NOT_APPLIED"
    assert len(calls) == 1
    assert _has(calls[0], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" not in calls[0]


def test_resume_apply_import_runs_import_then_readiness_without_launch(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "ingest_agent750_codecaptain_answer.py"):
            if "--apply" not in cmd:
                return _result(
                    0,
                    {
                        "ok": True,
                        "action": "dry_run",
                        "decision_token": resume.GREEN_TOKEN,
                    },
                )
            return _result(
                0,
                {
                    "ok": True,
                    "action": "copied",
                    "decision_token": resume.GREEN_TOKEN,
                },
            )
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            return _result(
                0,
                {
                    "ok": True,
                    "ready_for_launch_selection": True,
                    "suggested_reuse_panes": "%329,%326,%327",
                },
            )
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            assert "--dry-run" in cmd
            return _result(
                0,
                {
                    "ok": True,
                    "dry_run": True,
                    "reuse_pane_identities": [
                        {"pane": "%329", "command": "codex", "path": str(resume.REPO_ROOT)},
                        {"pane": "%326", "command": "codex", "path": str(resume.REPO_ROOT)},
                        {"pane": "%327", "command": "codex", "path": str(resume.REPO_ROOT)},
                    ],
                },
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--source", "/tmp/Code_Captain_AGENT750.md", "--apply-import"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "READY_FOR_GUARDED_LAUNCH"
    assert payload["did_launch"] is False
    assert payload["next_resume_command"] == [
        "python3",
        "scripts/resume_agent750_to_753.py",
        "--launch",
    ]
    assert _has(calls[0], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" not in calls[0]
    assert "--replace" not in calls[0]
    assert _has(calls[1], "check_agent750_launch_readiness.py")
    assert _has(calls[2], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" in calls[2]
    assert "--replace" not in calls[2]
    assert _has(calls[3], "check_agent750_launch_readiness.py")
    assert _has(calls[4], "list_agent751_753_candidate_panes.py")
    assert _has(calls[5], "launch_agent751_753_after_agent750.py")
    assert "--dry-run" in calls[5]
    assert payload["launch_preflight"]["ok"] is True
    assert [step["name"] for step in payload["steps"]] == [
        "answer_import_dry_run",
        "pre_import_boundary_readiness",
        "answer_import_apply",
        "readiness",
        "pane_candidates",
        "guarded_launch_dry_run_preflight",
    ]
    assert len(calls) == 6


def test_resume_apply_import_blocks_before_apply_when_pre_import_db_boundary_mismatch(
    monkeypatch,
    capsys,
):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "ingest_agent750_codecaptain_answer.py"):
            assert "--apply" not in cmd
            return _result(
                0,
                {
                    "ok": True,
                    "action": "dry_run",
                    "decision_token": resume.GREEN_TOKEN,
                },
            )
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(
                2,
                {
                    "ok": False,
                    "decision_token": resume.GREEN_TOKEN,
                    "errors": [
                        "missing_codecaptain_answer_file",
                        "production_db_sha_mismatch",
                        "protected_workbook_sha_mismatch",
                    ],
                    "answer_files": [],
                    "db_sha256": "current-db-sha",
                    "workbook_sha256": "current-workbook-sha",
                    "expected_db_sha256": "reviewed-db-sha",
                    "expected_workbook_sha256": "reviewed-workbook-sha",
                    "db_sha256_matches_expected": False,
                    "workbook_sha256_matches_expected": False,
                },
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--source", "/tmp/Code_Captain_AGENT750.md", "--apply-import"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "IMPORT_BLOCKED_BY_DB_BOUNDARY_REVIEW"
    assert payload["errors"] == [
        "production_db_sha_mismatch",
        "protected_workbook_sha_mismatch",
    ]
    assert payload["local_action_state"] == "EXTERNAL_INPUT_REQUIRED_NO_SAFE_LOCAL_ACTION"
    assert payload["blocked_until"] == "codecaptain_agent750_exact_green_answer_and_db_boundary_review"
    assert payload["db_sha256"] == "current-db-sha"
    assert payload["workbook_sha256"] == "current-workbook-sha"
    assert payload["expected_db_sha256"] == "reviewed-db-sha"
    assert payload["expected_workbook_sha256"] == "reviewed-workbook-sha"
    assert payload["db_sha256_matches_expected"] is False
    assert payload["workbook_sha256_matches_expected"] is False
    assert payload["readiness"]["errors"] == [
        "missing_codecaptain_answer_file",
        "production_db_sha_mismatch",
        "protected_workbook_sha_mismatch",
    ]
    assert [step["name"] for step in payload["steps"]] == [
        "answer_import_dry_run",
        "pre_import_boundary_readiness",
    ]
    assert _has(calls[0], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" not in calls[0]
    assert _has(calls[1], "check_agent750_launch_readiness.py")
    assert len(calls) == 2


def test_resume_apply_import_green_still_blocks_on_db_boundary_mismatch(monkeypatch, capsys):
    calls = []
    readiness_calls = 0

    def fake_run(cmd):
        nonlocal readiness_calls
        calls.append(cmd)
        if _has(cmd, "ingest_agent750_codecaptain_answer.py"):
            if "--apply" not in cmd:
                return _result(
                    0,
                    {
                        "ok": True,
                        "action": "dry_run",
                        "decision_token": resume.GREEN_TOKEN,
                    },
                )
            return _result(
                0,
                {
                    "ok": True,
                    "action": "copied",
                    "decision_token": resume.GREEN_TOKEN,
                },
            )
        if _has(cmd, "check_agent750_launch_readiness.py"):
            readiness_calls += 1
            if readiness_calls == 1:
                return _result(
                    2,
                    {
                        "ok": False,
                        "decision_token": resume.GREEN_TOKEN,
                        "errors": ["missing_codecaptain_answer_file"],
                        "answer_files": [],
                    },
                )
            return _result(
                2,
                {
                    "ok": False,
                    "decision_token": resume.GREEN_TOKEN,
                    "errors": ["production_db_sha_mismatch"],
                    "answer_files": ["/tmp/Code_Captain_AGENT750.md"],
                },
            )
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            raise AssertionError("DB boundary mismatch must block before pane listing")
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            raise AssertionError("DB boundary mismatch must block before launch")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--source", "/tmp/Code_Captain_AGENT750.md", "--apply-import"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_READINESS"
    assert payload["local_action_state"] == "LOCAL_DB_BOUNDARY_REVIEW_REQUIRED"
    assert payload["blocked_until"] == "current_production_db_boundary_review_resolved"
    assert payload["readiness"]["decision_token"] == resume.GREEN_TOKEN
    assert payload["readiness"]["errors"] == ["production_db_sha_mismatch"]
    assert _has(calls[0], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" not in calls[0]
    assert _has(calls[1], "check_agent750_launch_readiness.py")
    assert _has(calls[2], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" in calls[2]
    assert _has(calls[3], "check_agent750_launch_readiness.py")
    assert len(calls) == 4


def test_resume_apply_import_with_replace_forwards_replace_without_pane_listing(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "ingest_agent750_codecaptain_answer.py"):
            if "--apply" not in cmd:
                return _result(
                    0,
                    {
                        "ok": True,
                        "action": "dry_run",
                        "decision_token": resume.GREEN_TOKEN,
                    },
                )
            return _result(
                0,
                {
                    "ok": True,
                    "action": "copied",
                    "decision_token": resume.GREEN_TOKEN,
                },
            )
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            raise AssertionError("explicit reuse panes should skip pane listing")
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            assert "--dry-run" in cmd
            return _result(0, {"ok": True, "dry_run": True})
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(
        [
            "--source",
            "/tmp/Code_Captain_AGENT750.md",
            "--apply-import",
            "--replace",
            "--reuse-panes",
            "%329,%326,%327",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "READY_FOR_GUARDED_LAUNCH"
    assert payload["did_launch"] is False
    assert payload["launch_command"] == [
        "python3",
        "scripts/launch_agent751_753_after_agent750.py",
        "--reuse-panes",
        "%329,%326,%327",
    ]
    assert "--apply" not in calls[0]
    assert "--replace" in calls[0]
    assert _has(calls[1], "check_agent750_launch_readiness.py")
    assert _has(calls[2], "ingest_agent750_codecaptain_answer.py")
    assert "--apply" in calls[2]
    assert "--replace" in calls[2]
    assert _has(calls[3], "check_agent750_launch_readiness.py")
    assert _has(calls[4], "launch_agent751_753_after_agent750.py")
    assert "--dry-run" in calls[4]
    assert len(calls) == 5


def test_resume_blocks_invalid_explicit_reuse_panes_before_launch(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            raise AssertionError("invalid reuse panes must block before launch")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%1,%2", "--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_REUSE_PANES"
    assert payload["errors"] == ["exactly_three_reuse_panes_required"]
    assert len(calls) == 1


def test_resume_blocks_current_tmux_pane_reuse_before_launch(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("TMUX_PANE", "%2")

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            raise AssertionError("current tmux pane reuse must block before launch")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%1,%2,%3", "--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_REUSE_PANES"
    assert payload["errors"] == ["reuse_panes_include_current_tmux_pane"]
    assert len(calls) == 1


def test_resume_ready_without_launch_returns_guarded_command(monkeypatch, capsys):
    calls = []
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            return _result(
                0,
                {
                    "ok": True,
                    "ready_for_launch_selection": True,
                    "suggested_reuse_panes": "%329,%326,%327",
                },
            )
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            assert "--dry-run" in cmd
            return _result(0, {"ok": True, "dry_run": True})
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "READY_FOR_GUARDED_LAUNCH"
    assert payload["did_launch"] is False
    assert payload["launch_command"] == [
        "python3",
        "scripts/launch_agent751_753_after_agent750.py",
        "--reuse-panes",
        "%329,%326,%327",
    ]
    assert payload["launch_preflight"] == {"ok": True, "dry_run": True}
    assert _has(calls[2], "launch_agent751_753_after_agent750.py")
    assert "--dry-run" in calls[2]
    assert len(calls) == 3

    calls.clear()

    def fake_pane_block_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            return _result(
                2,
                {
                    "ok": False,
                    "status": "INSUFFICIENT_CANDIDATE_PANES",
                    "errors": ["fewer_than_three_candidate_panes"],
                    "ready_for_launch_selection": False,
                    "candidate_count": 2,
                    "suggested_reuse_panes": "",
                    "guarded_launch_command": "",
                    "readiness": {"ok": True, "decision_token": resume.GREEN_TOKEN},
                    "review_pack": status["review_pack"],
                },
            )
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            raise AssertionError("pane selection must block before launch preflight")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_pane_block_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_PANE_SELECTION"
    assert payload["local_action_state"] == "LOCAL_PANE_SELECTION_REQUIRED"
    assert payload["blocked_until"] == "three_reusable_codex_panes_selected"
    assert payload["errors"] == ["fewer_than_three_candidate_panes"]
    assert payload["readiness"] == {"ok": True, "decision_token": resume.GREEN_TOKEN}
    assert payload["review_pack"] == status["review_pack"]
    assert payload["pane_candidates"]["status"] == "INSUFFICIENT_CANDIDATE_PANES"
    assert payload["pane_candidates"]["candidate_count"] == 2
    assert payload["pane_candidates"]["guarded_launch_command"] == ""
    assert len(calls) == 2


def test_resume_blocks_when_guarded_launch_dry_run_rejects_panes(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            assert "--dry-run" in cmd
            return _result(
                2,
                {
                    "ok": False,
                    "errors": ["reuse_pane_not_codex"],
                    "reuse_pane_identities": [{"pane": "%329", "command": "zsh"}],
                },
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%329,%326,%327"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_LAUNCH_PREFLIGHT"
    assert payload["launch_preflight"]["errors"] == ["reuse_pane_not_codex"]
    assert len(calls) == 2


def test_resume_launch_runs_dry_run_preflight_before_actual_launch(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py") and "--dry-run" in cmd:
            return _result(0, {"ok": True, "dry_run": True})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            return _result(0, {"ok": True, "launched": True})
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%329,%326,%327", "--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "LAUNCH_COMMAND_COMPLETED"
    assert [step["name"] for step in payload["steps"]] == [
        "readiness",
        "guarded_launch_dry_run_preflight",
        "guarded_launch",
    ]
    assert "--dry-run" in calls[1]
    assert "--dry-run" not in calls[2]


def test_resume_launch_requires_explicit_json_ok_from_launcher(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py") and "--dry-run" in cmd:
            return _result(0, {"ok": True, "dry_run": True})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            return _raw_result(0, "")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%329,%326,%327", "--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert payload["status"] == "LAUNCH_COMMAND_FAILED"
    assert payload["launch"] == {}
    assert payload["steps"][-1]["parse_errors"] == []


def test_resume_launch_preserves_structured_launcher_failure(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "launch_agent751_753_after_agent750.py") and "--dry-run" in cmd:
            return _result(0, {"ok": True, "dry_run": True})
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            return _result(
                7,
                {
                    "ok": False,
                    "launched": False,
                    "tmux_launcher_returncode": 7,
                    "tmux_launcher_stderr": "tmux launcher failed",
                },
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--reuse-panes", "%329,%326,%327", "--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["ok"] is False
    assert payload["status"] == "LAUNCH_COMMAND_FAILED"
    assert payload["launch"]["launched"] is False
    assert payload["launch"]["tmux_launcher_returncode"] == 7
    assert payload["launch"]["tmux_launcher_stderr"] == "tmux launcher failed"


def test_resume_blocks_if_readiness_ok_lacks_exact_green_token(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            raise AssertionError("pane listing must not run without exact green token")
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main([])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "BLOCKED_BY_DECISION_TOKEN"
    assert payload["expected_decision_token"] == resume.GREEN_TOKEN
    assert payload["actual_decision_token"] == "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
    assert len(calls) == 1


def test_resume_launch_requires_explicit_launch_flag(monkeypatch, capsys):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if _has(cmd, "check_agent750_launch_readiness.py"):
            return _result(0, {"ok": True, "decision_token": resume.GREEN_TOKEN})
        if _has(cmd, "list_agent751_753_candidate_panes.py"):
            return _result(
                0,
                {
                    "ok": True,
                    "ready_for_launch_selection": True,
                    "suggested_reuse_panes": "%329,%326,%327",
                },
            )
        if _has(cmd, "launch_agent751_753_after_agent750.py"):
            return _result(0, {"ok": True, "dry_run": False})
        raise AssertionError(cmd)

    monkeypatch.setattr(resume, "run_command", fake_run)

    rc = resume.main(["--launch"])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "LAUNCH_COMMAND_COMPLETED"
    assert _has(calls[-1], "launch_agent751_753_after_agent750.py")
