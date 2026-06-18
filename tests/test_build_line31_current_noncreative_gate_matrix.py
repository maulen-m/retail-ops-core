from __future__ import annotations

import json
from pathlib import Path
import sys

from scripts.build_line31_current_noncreative_gate_matrix import (
    DEFAULT_VALIDATORS,
    ValidatorSpec,
    build_matrix,
)


def _spec(name: str, code: int) -> ValidatorSpec:
    return ValidatorSpec(
        gate=name,
        command=(sys.executable, "-c", f"import sys; print('{name}'); sys.exit({code})"),
        retained_blocker=f"{name}_blocker",
        evidence_summary_ok=f"{name} ok",
        evidence_summary_fail=f"{name} failed",
    )


def test_current_noncreative_matrix_green_when_all_validators_pass(tmp_path: Path) -> None:
    matrix = build_matrix(
        output_root=tmp_path,
        run_id="green",
        validators=(_spec("gate_a", 0), _spec("gate_b", 0)),
    )

    assert matrix["overall_gate"] == "GREEN"
    assert matrix["can_use_green_except_creative"] is True
    assert matrix["retained_noncreative_blockers"] == []
    assert matrix["advisory_repo_blockers"] == []
    written = json.loads((tmp_path / "CURRENT_NONCREATIVE_GATE_MATRIX.json").read_text())
    assert written["overall_gate"] == "GREEN"
    assert (tmp_path / "CURRENT_NONCREATIVE_GATE_MATRIX.md").exists()
    assert (tmp_path / "COMMANDS_RUN.tsv").exists()


def test_current_noncreative_matrix_yellow_when_validator_fails(tmp_path: Path) -> None:
    matrix = build_matrix(
        output_root=tmp_path,
        run_id="yellow",
        validators=(_spec("gate_a", 0), _spec("gate_b", 1)),
    )

    assert matrix["overall_gate"] == "YELLOW"
    assert matrix["can_use_green_except_creative"] is False
    assert matrix["retained_noncreative_blockers"] == ["gate_b_blocker"]
    assert matrix["advisory_repo_blockers"] == []
    assert matrix["final_status"][1]["exit_code"] == 1


def test_current_noncreative_matrix_keeps_advisory_failures_visible_without_blocking(
    tmp_path: Path,
) -> None:
    advisory = ValidatorSpec(
        gate="strict_repo_gate",
        command=(sys.executable, "-c", "import sys; print('strict'); sys.exit(1)"),
        retained_blocker="strict_repo_gate",
        evidence_summary_ok="strict ok",
        evidence_summary_fail="strict failed",
        blocking_for_green_except_creative=False,
        scope="repo_wide_advisory",
    )

    matrix = build_matrix(
        output_root=tmp_path,
        run_id="advisory",
        validators=(advisory, _spec("line31_gate", 0)),
    )

    assert matrix["overall_gate"] == "GREEN"
    assert matrix["can_use_green_except_creative"] is True
    assert matrix["retained_noncreative_blockers"] == []
    assert matrix["advisory_repo_blockers"] == ["strict_repo_gate"]
    assert matrix["final_status"][0]["status"] == "YELLOW_ADVISORY"
    assert matrix["final_status"][0]["blocking_for_green_except_creative"] is False


def test_default_validators_use_active_interpreter() -> None:
    assert DEFAULT_VALIDATORS
    assert all(spec.command[0] == sys.executable for spec in DEFAULT_VALIDATORS)
