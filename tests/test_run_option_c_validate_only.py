from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import scripts.run_option_c_validate_only as runner


def _seed_sqlite_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO marker (id) VALUES (1)")


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def test_proof_window_lock_blocks_before_source_db_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "proof_window.lock"
    lock_path.write_text("protected proof window\n", encoding="utf-8")
    evidence_dir = tmp_path / "evidence"

    def _forbidden_db_touch(*_args, **_kwargs):
        raise AssertionError("proof-window lock must block before source DB touch")

    monkeypatch.setenv("AB_PROOF_WINDOW_LOCK_PATH", str(lock_path))
    monkeypatch.setattr(runner, "_copy_source_db", _forbidden_db_touch)
    monkeypatch.setattr(runner, "_integrity_check_readonly", _forbidden_db_touch)

    result = runner.run_validate_only(
        runner.ValidateOnlyConfig(
            as_of="2026-05-10",
            evidence_dir=evidence_dir,
            mode="copy-production",
            source_db_path=tmp_path / "must_not_open.db",
            copied_db_path=None,
            execute_validators=False,
        )
    )

    assert result.exit_code == runner.PROOF_WINDOW_BLOCK_EXIT_CODE
    assert runner.PROOF_WINDOW_BLOCK_TOKEN in result.message
    assert str(lock_path) in result.message
    assert not evidence_dir.exists()


def test_validator_matrix_targets_copied_db_or_blocks(tmp_path: Path) -> None:
    copied_db = tmp_path / "copied.db"
    evidence_dir = tmp_path / "evidence"

    commands = runner.build_validator_commands(
        copied_db_path=copied_db,
        as_of="2026-05-04",
        evidence_dir=evidence_dir,
    )

    assert commands
    for item in commands:
        assert runner.validator_has_explicit_db_target(item, copied_db)
        assert str(runner.DEFAULT_PRODUCTION_DB) not in [str(part) for part in item.command]

    unsupported = runner.ValidatorCommand(
        name="legacy_validator_without_db_flag",
        command=["python3", "scripts/legacy_validator.py"],
        supports_explicit_db_target=False,
    )
    target_check = runner.validate_validator_commands(
        [unsupported],
        copied_db_path=copied_db,
        evidence_dir=evidence_dir,
    )

    assert target_check.ok is False
    assert target_check.code == "BLOCKED_UNSUPPORTED_VALIDATOR_DB_TARGET"
    assert "legacy_validator_without_db_flag" in target_check.message


def test_ads_validators_are_forced_into_evidence_dir(tmp_path: Path) -> None:
    copied_db = tmp_path / "copied.db"
    evidence_dir = tmp_path / "evidence"

    commands = runner.build_validator_commands(
        copied_db_path=copied_db,
        as_of="2026-05-04",
        evidence_dir=evidence_dir,
    )
    by_name = {command.name: command for command in commands}

    readiness = by_name["ads_sidecar_readiness"]
    assert "--db" in readiness.command
    assert readiness.command[readiness.command.index("--db") + 1] == str(copied_db)
    assert "--output-root" in readiness.command
    assert readiness.command[readiness.command.index("--output-root") + 1] == str(
        (evidence_dir / "04_validator_outputs" / "ads_sidecar_readiness").resolve()
    )
    assert runner.validator_output_paths_inside_evidence(readiness, evidence_dir)

    offer_universe = by_name["ads_offer_universe_coverage"]
    assert "--db-path" in offer_universe.command
    assert offer_universe.command[offer_universe.command.index("--db-path") + 1] == str(copied_db)
    assert "--output-dir" in offer_universe.command
    assert offer_universe.command[offer_universe.command.index("--output-dir") + 1] == str(
        (evidence_dir / "04_validator_outputs" / "ads_offer_universe").resolve()
    )
    assert runner.validator_has_explicit_db_target(offer_universe, copied_db)
    assert runner.validator_output_paths_inside_evidence(offer_universe, evidence_dir)

    target_check = runner.validate_validator_commands(
        commands,
        copied_db_path=copied_db,
        evidence_dir=evidence_dir,
    )
    assert target_check.ok is True


def test_ads_validator_without_output_containment_blocks(tmp_path: Path) -> None:
    copied_db = tmp_path / "copied.db"
    evidence_dir = tmp_path / "evidence"

    unsafe = runner.ValidatorCommand(
        name="ads_without_output_containment",
        command=[
            "python3",
            "scripts/validate_ads_sidecar_readiness.py",
            "--db",
            str(copied_db),
            "--as-of",
            "2026-05-04",
        ],
        requires_output_containment=True,
    )
    target_check = runner.validate_validator_commands(
        [unsafe],
        copied_db_path=copied_db,
        evidence_dir=evidence_dir,
    )

    assert target_check.ok is False
    assert target_check.code == "BLOCKED_UNCONTAINED_VALIDATOR_OUTPUT"
    assert "ads_without_output_containment" in target_check.message


def test_owner_draft_and_trust_banner_stay_inside_evidence_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied_db = tmp_path / "copied" / "app.db"
    evidence_dir = tmp_path / "evidence"
    _seed_sqlite_db(copied_db)

    def _fake_run_validator(command: runner.ValidatorCommand, *, project_root: Path) -> runner.ValidatorRunResult:
        assert runner.validator_has_explicit_db_target(command, copied_db)
        return runner.ValidatorRunResult(
            name=command.name,
            command=command.command,
            exit_code=0,
            status="PASS",
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(runner, "_run_validator_command", _fake_run_validator)

    result = runner.run_validate_only(
        runner.ValidateOnlyConfig(
            as_of="2026-05-10",
            evidence_dir=evidence_dir,
            mode="existing-copy",
            source_db_path=None,
            copied_db_path=copied_db,
            execute_validators=True,
        )
    )

    assert result.exit_code == 0
    assert result.banner_path is not None
    assert result.owner_draft_path is not None
    assert result.written_files
    for path in result.written_files:
        assert _is_relative_to(path, evidence_dir)

    banner = json.loads(result.banner_path.read_text(encoding="utf-8"))
    assert banner["surface"] == "Cash Risk Daily"
    assert banner["mode"] == "validate_only"
    assert banner["banner_status"] == "GREEN"
    assert banner["copied_db_path"] == str(copied_db)
    assert "cash_movement" in banner["blocked_decisions"]
    assert isinstance(banner["warning_cohorts"], list)

    draft_text = result.owner_draft_path.read_text(encoding="utf-8")
    assert "Cash Risk Daily" in draft_text
    assert "Draft only" in draft_text
    assert str(result.banner_path) in draft_text
