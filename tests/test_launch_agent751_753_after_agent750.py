from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import launch_agent751_753_after_agent750 as launcher


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FakeReadiness:
    ok: bool
    errors: list[str] = field(default_factory=list)
    decision_token: str | None = launcher.GREEN_TOKEN
    db_sha256: str | None = None
    workbook_sha256: str | None = None
    expected_db_sha256: str | None = None
    expected_workbook_sha256: str | None = None
    db_sha256_matches_expected: bool | None = None
    workbook_sha256_matches_expected: bool | None = None


def assert_monitor_only_command(command: list[str]) -> None:
    assert "--orchestrator-ping-mode" in command
    assert command[command.index("--orchestrator-ping-mode") + 1] == "monitor-only"

    forbidden_tokens = {
        "--visibility-pane",
        "--orchestrator-pane",
        "--auto-create-orchestrator-receiver",
        "LIVE",
        "receiver",
        "chat",
    }
    assert forbidden_tokens.isdisjoint(command)


def assert_review_pack_matches_status(payload: dict) -> None:
    status_path = (
        REPO_ROOT
        / "docs"
        / "parallel_runs"
        / "2026-05-06_codecaptain_proscope_red_recovery"
        / "current_gate_status_agent750_waiting_codecaptain.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
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
    assert payload["review_pack"]["status_review_pack_errors"] == []
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


def test_launcher_refuses_when_readiness_checker_is_not_green(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        launcher,
        "run_readiness_check",
        lambda: FakeReadiness(
            ok=False,
            errors=["missing_codecaptain_answer_file"],
            db_sha256="current-db-sha",
            workbook_sha256="current-workbook-sha",
            expected_db_sha256="reviewed-db-sha",
            expected_workbook_sha256="current-workbook-sha",
            db_sha256_matches_expected=False,
            workbook_sha256_matches_expected=True,
        ),
    )
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "readiness"
    assert payload["errors"] == ["missing_codecaptain_answer_file"]
    assert payload["readiness"]["errors"] == ["missing_codecaptain_answer_file"]
    assert payload["db_sha256"] == "current-db-sha"
    assert payload["workbook_sha256"] == "current-workbook-sha"
    assert payload["expected_db_sha256"] == "reviewed-db-sha"
    assert payload["expected_workbook_sha256"] == "current-workbook-sha"
    assert payload["db_sha256_matches_expected"] is False
    assert payload["workbook_sha256_matches_expected"] is True
    assert_review_pack_matches_status(payload)


def test_launcher_blocked_payload_survives_status_json_not_object(monkeypatch, capsys, tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(launcher, "CURRENT_GATE_STATUS_PATH", status_path)
    monkeypatch.setattr(
        launcher,
        "run_readiness_check",
        lambda: FakeReadiness(ok=False, errors=["missing_codecaptain_answer_file"]),
    )

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "readiness"
    assert payload["latest_completion_audit"].endswith(
        "ACTIVE_OBJECTIVE_COMPLETION_AUDIT_20260510_090511.md"
    )
    assert payload["latest_answer_search"]["status_path_json_valid"] is True
    assert payload["latest_answer_search"]["status_path_error"] == "status_json_not_object"
    assert payload["review_pack"]["status_path_json_valid"] is True
    assert payload["review_pack"]["status_path_error"] == "status_json_not_object"


def test_launcher_requires_reuse_panes_when_ready(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))

    rc = launcher.main([])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["reuse_panes_required"]
    assert payload["readiness"]["ok"] is True
    assert payload["reuse_pane_count"] == 0
    assert_review_pack_matches_status(payload)


def test_launcher_blocks_if_readiness_ok_lacks_exact_green_token(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        launcher,
        "run_readiness_check",
        lambda: FakeReadiness(ok=True, decision_token="YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"),
    )
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "decision_token"
    assert payload["errors"] == ["readiness_decision_token_not_exact_green"]
    assert payload["expected_decision_token"] == launcher.GREEN_TOKEN
    assert payload["actual_decision_token"] == "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE"
    assert_review_pack_matches_status(payload)


def test_launcher_blocks_ready_green_when_review_pack_unhealthy(monkeypatch, capsys):
    calls = []
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
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher, "_current_review_pack_info", lambda: bad_review_pack)
    monkeypatch.setattr(launcher.subprocess, "check_output", lambda *a, **k: calls.append("tmux"))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append("run"))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "review_pack"
    assert "status_review_pack_optional_upload_zip_not_string" in payload["errors"]
    assert "optional_upload_zip_missing" in payload["errors"]
    assert "latest_validator_manifest_missing" in payload["errors"]
    assert payload["review_pack"] == bad_review_pack


def test_launcher_requires_exactly_three_reuse_panes(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["exactly_three_reuse_panes_required"]
    assert payload["reuse_pane_count"] == 1
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_too_many_reuse_panes(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3,%4"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["exactly_three_reuse_panes_required"]
    assert payload["reuse_pane_count"] == 4
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_duplicate_reuse_panes(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%1,%2"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["unique_reuse_panes_required"]
    assert payload["reuse_pane_count"] == 3
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_non_pane_reuse_targets(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "autonomous_business:1.1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["pane_ids_must_be_percent_ids"]
    assert payload["reuse_pane_count"] == 3
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_reuse_panes_that_include_current_tmux_pane(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("TMUX_PANE", "%2")
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "reuse_panes"
    assert payload["errors"] == ["reuse_panes_include_current_tmux_pane"]
    assert payload["reuse_pane_count"] == 3
    assert_review_pack_matches_status(payload)


def test_launcher_dry_run_prints_safe_monitor_only_command(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tcodex\t~/Docs/Autonomous_business\n",
    )

    rc = launcher.main(["--reuse-panes", "%1,%2,%3", "--run-id", "test_run", "--dry-run"])

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert_monitor_only_command(payload["command"])
    assert "--orchestrator-ping-mode" in out
    assert "monitor-only" in out
    assert "receiver" not in out
    assert "--auto-create-orchestrator-receiver" not in out
    assert "--orchestrator-pane" not in out
    assert "--visibility-pane" not in out
    assert "LIVE" not in out
    assert "--agents" in out
    assert "751,752,753" in out
    assert "reuse_pane_identities" in out


def test_launcher_dry_run_validates_live_reuse_panes(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tzsh\t~/Docs/Autonomous_business\n",
    )

    rc = launcher.main(["--reuse-panes", "%1,%2,%3", "--run-id", "test_run", "--dry-run"])

    out = capsys.readouterr().out
    assert rc == 2
    payload = json.loads(out)
    assert payload["stage"] == "live_reuse_panes"
    assert payload["errors"] == ["reuse_pane_not_codex"]
    assert "dry_run" not in payload
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_reuse_pane_that_is_not_codex(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tzsh\t~/Docs/Autonomous_business\n",
    )
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "live_reuse_panes"
    assert payload["errors"] == ["reuse_pane_not_codex"]
    assert_review_pack_matches_status(payload)


def test_launcher_rejects_reuse_pane_outside_repo(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tcodex\t~\n",
    )
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    rc = launcher.main(["--reuse-panes", "%1,%2,%3"])

    assert rc == 2
    assert calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "live_reuse_panes"
    assert payload["errors"] == ["reuse_pane_not_in_repo"]
    assert_review_pack_matches_status(payload)


def test_launcher_real_launch_validates_reuse_panes_before_subprocess_run(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tcodex\t~/Docs/Autonomous_business\n",
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *a, **k: calls.append((a, k)) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    rc = launcher.main(["--reuse-panes", "%1,%2,%3", "--run-id", "test_run"])

    assert rc == 0
    assert len(calls) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["launched"] is True
    assert payload["tmux_launcher_returncode"] == 0
    assert "command" in payload
    assert_monitor_only_command(payload["command"])


def test_launcher_real_launch_failure_emits_structured_json(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "run_readiness_check", lambda: FakeReadiness(ok=True))
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda *a, **k: "%1\tcodex\t~/Docs/Autonomous_business\n",
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=7,
            stdout="partial stdout",
            stderr="tmux launcher failed",
        ),
    )

    rc = launcher.main(["--reuse-panes", "%1,%2,%3", "--run-id", "test_run"])

    assert rc == 7
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["launched"] is False
    assert payload["tmux_launcher_returncode"] == 7
    assert payload["tmux_launcher_stdout"] == "partial stdout"
    assert payload["tmux_launcher_stderr"] == "tmux launcher failed"
    assert_monitor_only_command(payload["command"])
