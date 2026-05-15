from dataclasses import dataclass, field
import json
import subprocess

from scripts import list_agent751_753_candidate_panes as lister
from scripts.list_agent751_753_candidate_panes import parse_tmux_panes, summarize_candidates


@dataclass
class FakeReadiness:
    ok: bool
    errors: list[str] = field(default_factory=list)
    decision_token: str | None = lister.GREEN_TOKEN
    db_sha256: str | None = None
    workbook_sha256: str | None = None
    expected_db_sha256: str | None = None
    expected_workbook_sha256: str | None = None
    db_sha256_matches_expected: bool | None = None
    workbook_sha256_matches_expected: bool | None = None


def _healthy_review_pack() -> dict:
    return {
        "path": "review-pack",
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": None,
        "status_review_pack_errors": [],
        "optional_upload_zip_exists": True,
        "optional_upload_zip_sha256_matches": True,
        "optional_upload_zip_manifest_exists": True,
        "latest_validator_manifest_exists": True,
        "latest_validator_manifest_json_valid": True,
        "latest_validator_manifest_ok": True,
        "latest_validator_manifest_errors": [],
        "latest_validator_manifest_status_pointer_error": None,
        "latest_validator_manifest_status_pointer_terms_match_status": True,
        "latest_validator_manifest_optional_upload_zip_sha256_matches_status": True,
        "latest_validator_manifest_optional_upload_zip_source_bytes_match": True,
    }


def test_parse_tmux_panes_finds_codex_panes_in_repo():
    raw = "\n".join(
        [
            "%1\tcodex\t~/Docs/Autonomous_business\tautonomous_business:1.1\tagent",
            "%2\tzsh\t~/Docs/Autonomous_business\tautonomous_business:1.2\tshell",
            "%3\tcodex\t~\tautonomous_business:1.3\twrong path",
            "%4\tcodex-aarch64-a\t~/Docs/Autonomous_business\tautonomous_business:1.4\tagent",
        ]
    )

    panes = parse_tmux_panes(raw)
    summary = summarize_candidates(panes, repo_path="~/Docs/Autonomous_business")

    assert [pane["pane_id"] for pane in summary["candidate_panes"]] == ["%1", "%4"]
    assert summary["candidate_count"] == 2
    assert summary["ready_for_launch_selection"] is False


def test_parse_tmux_panes_requires_three_candidates_for_ready_selection(monkeypatch, capsys):
    status = json.loads(
        (
            lister.REPO_ROOT
            / "docs"
            / "parallel_runs"
            / "2026-05-06_codecaptain_proscope_red_recovery"
            / "current_gate_status_agent750_waiting_codecaptain.json"
        ).read_text(encoding="utf-8")
    )
    raw = "\n".join(
        [
            "%1\tcodex\t/repo\ts:1.1\tA",
            "%2\tcodex\t/repo\ts:1.2\tB",
            "%3\tcodex-aarch64-a\t/repo\ts:1.3\tC",
        ]
    )

    summary = summarize_candidates(parse_tmux_panes(raw), repo_path="/repo")

    assert summary["ready_for_launch_selection"] is True
    assert summary["suggested_reuse_panes"] == "%1,%2,%3"
    assert "launch_agent751_753_after_agent750.py --reuse-panes %1,%2,%3" in summary[
        "guarded_launch_command"
    ]

    tmux_calls = []
    monkeypatch.setattr(
        lister,
        "run_readiness_check",
        lambda: FakeReadiness(
            ok=False,
            errors=[
                "missing_codecaptain_answer_file",
                "production_db_sha_mismatch",
                "protected_workbook_sha_mismatch",
            ],
            decision_token=None,
            db_sha256="current-db-sha",
            workbook_sha256="current-workbook-sha",
            expected_db_sha256="reviewed-db-sha",
            expected_workbook_sha256="reviewed-workbook-sha",
            db_sha256_matches_expected=False,
            workbook_sha256_matches_expected=False,
        ),
    )
    monkeypatch.setattr(lister, "_current_review_pack_info", lambda: {"path": "review-pack"})
    monkeypatch.setattr(lister, "list_tmux_panes", lambda: tmux_calls.append("tmux") or raw)

    rc = lister.main(["--repo", "/repo", "--json-only"])

    assert rc == 2
    assert tmux_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED_BY_READINESS"
    assert payload["errors"] == [
        "missing_codecaptain_answer_file",
        "production_db_sha_mismatch",
        "protected_workbook_sha_mismatch",
    ]
    assert payload["db_sha256"] == "current-db-sha"
    assert payload["workbook_sha256"] == "current-workbook-sha"
    assert payload["expected_db_sha256"] == "reviewed-db-sha"
    assert payload["expected_workbook_sha256"] == "reviewed-workbook-sha"
    assert payload["db_sha256_matches_expected"] is False
    assert payload["workbook_sha256_matches_expected"] is False
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
    assert payload["review_pack"]["path"] == "review-pack"
    assert payload["candidate_count"] == 0
    assert payload["ready_for_launch_selection"] is False
    assert payload["candidate_panes"] == []
    assert payload["suggested_reuse_panes"] == ""
    assert payload["guarded_launch_command"] == ""
    assert "tmux panes were not listed" in payload["note"]

    monkeypatch.setattr(
        lister,
        "run_readiness_check",
        lambda: FakeReadiness(
            ok=True,
            decision_token="YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE",
        ),
    )

    rc = lister.main(["--repo", "/repo", "--json-only"])

    assert rc == 2
    assert tmux_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED_BY_DECISION_TOKEN"
    assert payload["errors"] == ["readiness_decision_token_not_exact_green"]
    assert payload["expected_decision_token"] == lister.GREEN_TOKEN
    assert payload["actual_decision_token"] == "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
    assert payload["candidate_count"] == 0
    assert payload["ready_for_launch_selection"] is False
    assert payload["candidate_panes"] == []
    assert payload["suggested_reuse_panes"] == ""
    assert payload["guarded_launch_command"] == ""
    assert "requires the exact Agent750 GREEN token" in payload["note"]

    monkeypatch.setattr(lister, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        lister,
        "_current_review_pack_info",
        lambda: {
            "path": "review-pack",
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": None,
            "status_review_pack_errors": [
                "status_review_pack_latest_validator_manifest_not_string"
            ],
            "optional_upload_zip_exists": True,
            "optional_upload_zip_sha256_matches": True,
            "optional_upload_zip_manifest_exists": True,
            "latest_validator_manifest_exists": False,
            "latest_validator_manifest_json_valid": False,
            "latest_validator_manifest_ok": None,
            "latest_validator_manifest_errors": [],
            "latest_validator_manifest_status_pointer_error": None,
            "latest_validator_manifest_status_pointer_terms_match_status": False,
            "latest_validator_manifest_optional_upload_zip_sha256_matches_status": False,
            "latest_validator_manifest_optional_upload_zip_source_bytes_match": False,
        },
    )

    rc = lister.main(["--repo", "/repo", "--json-only"])

    assert rc == 2
    assert tmux_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED_BY_REVIEW_PACK"
    assert "status_review_pack_latest_validator_manifest_not_string" in payload["errors"]
    assert "latest_validator_manifest_missing" in payload["errors"]
    assert payload["candidate_count"] == 0
    assert payload["ready_for_launch_selection"] is False
    assert payload["candidate_panes"] == []
    assert payload["suggested_reuse_panes"] == ""
    assert payload["guarded_launch_command"] == ""
    assert "review pack" in payload["note"]

    two_candidate_raw = "\n".join(
        [
            "%1\tcodex\t/repo\ts:1.1\tA",
            "%2\tcodex\t/repo\ts:1.2\tB",
        ]
    )
    tmux_calls.clear()
    monkeypatch.setattr(lister, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(lister, "_current_review_pack_info", _healthy_review_pack)
    monkeypatch.setattr(
        lister,
        "list_tmux_panes",
        lambda: tmux_calls.append("tmux") or two_candidate_raw,
    )

    rc = lister.main(["--repo", "/repo", "--json-only"])

    assert rc == 2
    assert tmux_calls == ["tmux"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status"] == "INSUFFICIENT_CANDIDATE_PANES"
    assert payload["errors"] == ["fewer_than_three_candidate_panes"]
    assert payload["review_pack"]["path"] == "review-pack"
    assert payload["candidate_count"] == 2
    assert payload["ready_for_launch_selection"] is False
    assert payload["suggested_reuse_panes"] == ""
    assert payload["guarded_launch_command"] == ""
    assert "fewer than three reusable Codex panes" in payload["note"]

    tmux_calls.clear()
    monkeypatch.setattr(
        lister,
        "list_tmux_panes",
        lambda: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["tmux", "list-panes"], output="no tmux")
        ),
    )

    rc = lister.main(["--repo", "/repo", "--json-only"])

    assert rc == 2
    assert tmux_calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "TMUX_LIST_PANES_FAILED"
    assert payload["errors"] == ["tmux_list_panes_failed"]
    assert payload["review_pack"]["path"] == "review-pack"
    assert payload["candidate_count"] == 0
    assert payload["ready_for_launch_selection"] is False
    assert payload["candidate_panes"] == []
    assert payload["suggested_reuse_panes"] == ""
    assert payload["guarded_launch_command"] == ""
    assert "no launch command was suggested" in payload["note"]


def test_parse_tmux_panes_tolerates_titles_with_tabs():
    raw = "%9\tcodex\t/repo\ts:1.9\ttitle\twith\ttabs"

    panes = parse_tmux_panes(raw)

    assert panes[0]["pane_title"] == "title\twith\ttabs"


def test_summarize_candidates_reports_rejected_panes():
    raw = "\n".join(
        [
            "%1\tzsh\t/repo\ts:1.1\tshell",
            "%2\tcodex\t/other\ts:1.2\twrong path",
        ]
    )

    summary = summarize_candidates(parse_tmux_panes(raw), repo_path="/repo")

    assert summary["candidate_panes"] == []
    assert summary["rejected_panes"][0]["reject_reason"] == "not_codex"
    assert summary["rejected_panes"][1]["reject_reason"] == "wrong_path"


def test_summarize_candidates_prefers_autonomous_business_high_windows():
    raw = "\n".join(
        [
            "%218\tcodex\t/repo\tab_c3_readonly_20260503:8.1\told",
            "%70\tcodex\t/repo\tautonomous_business:1.6\told current session",
            "%326\tcodex\t/repo\tautonomous_business:18.1\tnewer",
            "%327\tcodex\t/repo\tautonomous_business:18.2\tnewer",
            "%329\tcodex\t/repo\tautonomous_business:20.1\tnewest",
        ]
    )

    summary = summarize_candidates(parse_tmux_panes(raw), repo_path="/repo")

    assert summary["suggested_reuse_panes"] == "%329,%326,%327"
    assert summary["candidate_panes"][0]["location"] == "autonomous_business:20.1"


def test_summarize_candidates_excludes_current_orchestrator_pane():
    raw = "\n".join(
        [
            "%70\tcodex\t/repo\tautonomous_business:20.0\tcurrent orchestrator",
            "%326\tcodex\t/repo\tautonomous_business:20.1\tagent",
            "%327\tcodex\t/repo\tautonomous_business:20.2\tagent",
            "%329\tcodex\t/repo\tautonomous_business:20.3\tagent",
        ]
    )

    summary = summarize_candidates(
        parse_tmux_panes(raw),
        repo_path="/repo",
        excluded_panes={"%70"},
    )

    assert summary["ready_for_launch_selection"] is True
    assert summary["suggested_reuse_panes"] == "%326,%327,%329"
    assert summary["excluded_panes"] == ["%70"]
    rejected = [pane for pane in summary["rejected_panes"] if pane["pane_id"] == "%70"]
    assert rejected[0]["reject_reason"] == "excluded_pane"
