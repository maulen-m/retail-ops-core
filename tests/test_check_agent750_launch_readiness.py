import hashlib
import json
from pathlib import Path

from scripts.check_agent750_launch_readiness import (
    CURRENT_GATE_STATUS_PATH,
    check_readiness,
    current_answer_search_info,
)


GREEN_TOKEN = "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE"
YELLOW_TOKEN = "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
RED_TOKEN = "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_paths(tmp_path: Path) -> dict[str, Path]:
    answer_dir = tmp_path / "answer"
    answer_dir.mkdir()
    _write(answer_dir / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md", "instructions only")
    db_path = _write(tmp_path / "db" / "app.db", "db")
    workbook_path = _write(tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx", "workbook")
    handoff_root = tmp_path / "handoffs"
    orchestration_root = tmp_path / "runs" / "tmux_orchestration"
    registry = _write(
        tmp_path / "live_orchestrator_pane.json",
        json.dumps({"pane": "%71", "role": "orchestrator_live_chat"}),
    )
    visibility_kill_switch = _write(
        tmp_path / "config" / "tmux_orchestrator_visibility_disabled.flag",
        "wrong-pane incident: monitor-only\n",
    )
    completion_ping_kill_switch = _write(
        tmp_path / "config" / "tmux_orchestrator_pings_disabled.flag",
        "wrong-pane incident: monitor-only\n",
    )
    return {
        "answer_dir": answer_dir,
        "db_path": db_path,
        "workbook_path": workbook_path,
        "handoff_root": handoff_root,
        "orchestration_root": orchestration_root,
        "proof_window_lock": tmp_path / "config" / "proof_window.lock",
        "live_registry": registry,
        "tmux_visibility_kill_switch": visibility_kill_switch,
        "tmux_completion_ping_kill_switch": completion_ping_kill_switch,
    }


def test_readiness_passes_only_with_green_answer_and_clean_boundary(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is True
    assert result.decision_token == GREEN_TOKEN
    assert result.errors == []
    assert result.db_sha256 == _sha(paths["db_path"])
    assert result.workbook_sha256 == _sha(paths["workbook_path"])
    assert result.expected_db_sha256 == _sha(paths["db_path"])
    assert result.expected_workbook_sha256 == _sha(paths["workbook_path"])
    assert result.db_sha256_matches_expected is True
    assert result.workbook_sha256_matches_expected is True
    assert result.tmux_visibility_kill_switch_exists is True
    assert result.tmux_completion_ping_kill_switch_exists is True


def test_readiness_accepts_codecaptain_answer_filename_variant(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "CodeCaptain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is True
    assert result.decision_token == GREEN_TOKEN
    assert result.errors == []


def test_readiness_blocks_when_only_readme_is_present(tmp_path):
    paths = _base_paths(tmp_path)
    status = json.loads(CURRENT_GATE_STATUS_PATH.read_text(encoding="utf-8"))

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert "missing_codecaptain_answer_file" in result.errors
    assert result.latest_completion_audit == str(
        max(
            (
                REPO_ROOT
                / "docs"
                / "parallel_runs"
                / "2026-05-06_codecaptain_proscope_red_recovery"
            ).glob("ACTIVE_OBJECTIVE_COMPLETION_AUDIT_*.md")
        )
    )
    assert result.latest_answer_search["status"] == status["latest_answer_search"]["status"]
    assert (
        result.latest_answer_search["canonical_answer_folder"]
        == status["latest_answer_search"]["canonical_answer_folder"]
    )
    assert (
        result.latest_answer_search["canonical_answer_files"]
        == status["latest_answer_search"]["canonical_answer_files"]
    )
    assert result.latest_answer_search["canonical_answer_files_source"] == "live_filesystem"
    assert result.latest_answer_search["canonical_answer_files_match_status"] is True
    assert (
        result.latest_answer_search["canonical_answer_real_files"]
        == status["latest_answer_search"]["canonical_answer_real_files"]
    )
    assert (
        result.latest_answer_search["canonical_answer_files_from_status"]
        == status["latest_answer_search"]["canonical_answer_files"]
    )
    assert "canonical_answer_scan_observed_at_local" in result.latest_answer_search
    assert "~/Downloads" in result.latest_answer_search["searched_paths"]
    assert "~/Desktop" in result.latest_answer_search["searched_paths"]
    assert "Canonical Answer folder now contains exactly one real Agent750 answer" in result.latest_answer_search[
        "non_authoritative_hits_summary"
    ]
    assert "Exactly one real CodeCaptain answer Markdown file" in result.latest_answer_search[
        "launch_rule"
    ]


def test_answer_search_helper_fails_closed_on_status_json_not_object(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text("[]", encoding="utf-8")

    payload = current_answer_search_info(status_path)

    assert payload["status_path"] == str(status_path)
    assert payload["status_path_exists"] is True
    assert payload["status_path_json_valid"] is True
    assert payload["status_path_error"] == "status_json_not_object"


def test_answer_search_helper_refreshes_canonical_answer_folder_live(tmp_path):
    answer_dir = tmp_path / "Answer"
    answer_dir.mkdir()
    _write(answer_dir / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md", "instructions\n")
    _write(answer_dir / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    status_path = tmp_path / "current_status.json"
    status_path.write_text(
        json.dumps(
            {
                "latest_answer_search": {
                    "status": "NO_REAL_AGENT750_CODECAPTAIN_ANSWER_FOUND",
                    "canonical_answer_folder": str(answer_dir),
                    "canonical_answer_files": ["README_SAVE_CODECAPTAIN_ANSWER_HERE.md"],
                    "searched_paths": [str(tmp_path)],
                    "content_scan_terms": [GREEN_TOKEN],
                    "non_authoritative_hits_summary": "stale status evidence",
                    "launch_rule": "Only exactly one real CodeCaptain answer Markdown file.",
                }
            }
        ),
        encoding="utf-8",
    )

    payload = current_answer_search_info(status_path)

    assert payload["canonical_answer_files"] == [
        "Code_Captain_AGENT750.md",
        "README_SAVE_CODECAPTAIN_ANSWER_HERE.md",
    ]
    assert payload["canonical_answer_real_files"] == ["Code_Captain_AGENT750.md"]
    assert payload["canonical_answer_files_source"] == "live_filesystem"
    assert payload["canonical_answer_files_match_status"] is False
    assert payload["canonical_answer_files_from_status"] == [
        "README_SAVE_CODECAPTAIN_ANSWER_HERE.md"
    ]


def test_readiness_reports_misplaced_parent_answer_file(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"].parent / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert "missing_codecaptain_answer_file" in result.errors
    assert "misplaced_codecaptain_answer_files_present" in result.errors
    assert any("Code_Captain_AGENT750.md" in item for item in result.misplaced_answer_files)


def test_readiness_reports_misplaced_nested_answer_file(tmp_path):
    paths = _base_paths(tmp_path)
    _write(
        paths["answer_dir"].parent / "wrong_answer_folder" / "Code_Captain_AGENT750.md",
        f"Decision: {GREEN_TOKEN}\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert "missing_codecaptain_answer_file" in result.errors
    assert "misplaced_codecaptain_answer_files_present" in result.errors
    assert any("wrong_answer_folder" in item for item in result.misplaced_answer_files)


def test_readiness_blocks_green_token_in_unexpected_answer_filename(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "NOTES.md", f"Decision: {GREEN_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.answer_files == []
    assert result.decision_token is None
    assert "unexpected_codecaptain_answer_files_present" in result.errors


def test_readiness_ignores_green_token_inside_readme_placeholder(tmp_path):
    paths = _base_paths(tmp_path)
    _write(
        paths["answer_dir"] / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md",
        f"Required token reference only: {GREEN_TOKEN}\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.answer_files == []
    assert result.decision_token is None
    assert "missing_codecaptain_answer_file" in result.errors


def test_readiness_blocks_yellow_answer_before_launch(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {YELLOW_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token == YELLOW_TOKEN
    assert "codecaptain_answer_requires_fix_before_launch" in result.errors


def test_readiness_blocks_red_answer_before_launch(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {RED_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token == RED_TOKEN
    assert "codecaptain_answer_red_stopline" in result.errors


def test_readiness_blocks_answer_without_decision_token(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", "Looks fine, proceed.\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token is None
    assert "missing_codecaptain_decision_token" in result.errors


def test_readiness_ignores_green_token_outside_decision_or_gate_line(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Do not use {GREEN_TOKEN} yet.\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token is None
    assert "missing_codecaptain_decision_token" in result.errors


def test_readiness_ignores_negated_green_token_on_gate_line(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Gate: do not use {GREEN_TOKEN} yet.\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token is None
    assert "missing_codecaptain_decision_token" in result.errors


def test_readiness_ignores_green_token_inside_fenced_code_block(tmp_path):
    paths = _base_paths(tmp_path)
    _write(
        paths["answer_dir"] / "Code_Captain_AGENT750.md",
        f"Example only:\n```text\nGate: {GREEN_TOKEN}\n```\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token is None
    assert "missing_codecaptain_decision_token" in result.errors


def test_readiness_uses_real_decision_not_fenced_green_example(tmp_path):
    paths = _base_paths(tmp_path)
    _write(
        paths["answer_dir"] / "Code_Captain_AGENT750.md",
        f"Example only:\n```text\nGate: {GREEN_TOKEN}\n```\nDecision: {YELLOW_TOKEN}\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token == YELLOW_TOKEN
    assert "codecaptain_answer_requires_fix_before_launch" in result.errors
    assert "multiple_codecaptain_decision_tokens_found" not in result.errors


def test_readiness_accepts_gate_line_decision_token(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Gate: `{GREEN_TOKEN}`\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is True
    assert result.decision_token == GREEN_TOKEN


def test_readiness_blocks_multiple_real_answer_files_even_with_same_green_token(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750_first.md", f"Decision: {GREEN_TOKEN}\n")
    _write(paths["answer_dir"] / "Code_Captain_AGENT750_second.md", f"Decision: {GREEN_TOKEN}\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token == GREEN_TOKEN
    assert "multiple_codecaptain_answer_files_found" in result.errors


def test_readiness_blocks_conflicting_decision_tokens_in_one_answer_file(tmp_path):
    paths = _base_paths(tmp_path)
    _write(
        paths["answer_dir"] / "Code_Captain_AGENT750.md",
        f"Decision: {GREEN_TOKEN}\nGate: {YELLOW_TOKEN}\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.decision_token == GREEN_TOKEN
    assert "multiple_codecaptain_decision_tokens_found" in result.errors


def test_readiness_blocks_downstream_artifacts(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    _write(paths["handoff_root"] / "agent_751_option_c_validate_only_runner_contract_closeout.md", "Gate: GREEN\n")

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert "downstream_agent_artifacts_already_exist" in result.errors


def test_readiness_child_mode_reports_but_allows_downstream_artifacts(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    closeout = _write(
        paths["handoff_root"] / "agent_751_option_c_validate_only_runner_contract_closeout.md",
        "Gate: RED\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        allow_existing_downstream_artifacts=True,
        **paths,
    )

    assert result.ok is True
    assert result.errors == []
    assert result.allow_existing_downstream_artifacts is True
    assert str(closeout) in result.downstream_artifacts


def test_readiness_blocks_downstream_tmux_run_artifacts(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    _write(
        paths["orchestration_root"]
        / "codecaptain_agent751_752_753_validate_only_wave_20260510"
        / "orchestration_manifest.json",
        "{}\n",
    )

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert "downstream_agent_artifacts_already_exist" in result.errors
    assert any("agent751_752_753" in item for item in result.downstream_artifacts)


def test_readiness_blocks_boundary_drift_and_lock(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    _write(paths["proof_window_lock"], "active")

    result = check_readiness(
        expected_db_sha256="wrong-db-sha",
        expected_workbook_sha256="wrong-workbook-sha",
        **paths,
    )

    assert result.ok is False
    assert "production_db_sha_mismatch" in result.errors
    assert "protected_workbook_sha_mismatch" in result.errors
    assert "proof_window_lock_exists" in result.errors
    assert result.db_sha256 == _sha(paths["db_path"])
    assert result.workbook_sha256 == _sha(paths["workbook_path"])
    assert result.expected_db_sha256 == "wrong-db-sha"
    assert result.expected_workbook_sha256 == "wrong-workbook-sha"
    assert result.db_sha256_matches_expected is False
    assert result.workbook_sha256_matches_expected is False


def test_readiness_blocks_missing_tmux_visibility_kill_switch(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    paths["tmux_visibility_kill_switch"].unlink()

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.tmux_visibility_kill_switch_exists is False
    assert result.tmux_completion_ping_kill_switch_exists is True
    assert "tmux_visibility_kill_switch_missing" in result.errors


def test_readiness_blocks_missing_tmux_completion_ping_kill_switch(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    paths["tmux_completion_ping_kill_switch"].unlink()

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is False
    assert result.tmux_visibility_kill_switch_exists is True
    assert result.tmux_completion_ping_kill_switch_exists is False
    assert "tmux_completion_ping_kill_switch_missing" in result.errors


def test_readiness_does_not_require_live_registry_by_default(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    paths["live_registry"].unlink()

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        **paths,
    )

    assert result.ok is True
    assert result.live_pane_check_required is False


def test_readiness_can_opt_into_live_registry_blocking_check(tmp_path):
    paths = _base_paths(tmp_path)
    _write(paths["answer_dir"] / "Code_Captain_AGENT750.md", f"Decision: {GREEN_TOKEN}\n")
    paths["live_registry"].unlink()

    result = check_readiness(
        expected_db_sha256=_sha(paths["db_path"]),
        expected_workbook_sha256=_sha(paths["workbook_path"]),
        require_live_pane_check=True,
        **paths,
    )

    assert result.ok is False
    assert result.live_pane_check_required is True
    assert "live_orchestrator_registry_missing" in result.errors
