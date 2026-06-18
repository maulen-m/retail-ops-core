from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import subprocess
import sys

from scripts.ingest_line31_expert_launch_answer import (
    DECISION_CHANGE_BEFORE_START,
    DECISION_HOLD_PAUSED,
    DECISION_START_AS_IS,
    run,
)


def _oracle_pack(tmp_path: Path, answer_texts: list[tuple[str, str]] | None = None) -> Path:
    pack = tmp_path / "oracle_pack"
    answer = pack / "Answer"
    answer.mkdir(parents=True)
    for name, text in answer_texts or []:
        path = answer / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return pack


def _final_start_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "validation" / "line31_final_start_decision_packet_20260604_110520"
    path.mkdir(parents=True)
    manifest = path / "final_start_decision_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "gate": "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE",
                "checks_failed": 0,
                "meta_write_attempted": False,
                "decision_options": [
                    {
                        "option": "START_AS_IS",
                        "requires_exact_phrase_path": "/tmp/activation_phrase.txt",
                        "activation_command_template": "python3 activate.py --execute-approved-activation",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _args(tmp_path: Path, pack: Path, manifest: Path | None = None, run_id: str = "run") -> Namespace:
    return Namespace(
        oracle_pack=pack,
        output_root=tmp_path / "validation",
        final_start_manifest=manifest,
        run_id=run_id,
        json=False,
    )


def test_empty_answer_folder_is_pending_no_write(tmp_path: Path) -> None:
    payload = run(_args(tmp_path, _oracle_pack(tmp_path), _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE"
    assert payload["decision"] == "PENDING_ANSWER"
    assert payload["meta_write_attempted"] is False
    assert payload["external_write_attempted"] is False
    assert Path(payload["manifest_path"]).exists()
    assert Path(payload["summary_md"]).exists()
    assert Path(payload["next_safe_action_md"]).exists()


def test_multiple_answers_fail_red(tmp_path: Path) -> None:
    pack = _oracle_pack(
        tmp_path,
        [
            ("answer_a.md", "Decision: START_AS_IS"),
            ("answer_b.md", "Decision: HOLD_PAUSED"),
        ],
    )

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "RED_LINE31_EXPERT_ANSWER_AMBIGUOUS_NO_WRITE"
    assert payload["decision"] == "UNCLASSIFIED"
    assert payload["meta_write_attempted"] is False


def test_explicit_start_as_is_becomes_green_when_preflight_is_ready(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Decision: START_AS_IS\n\nLaunch is acceptable.")])

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE"
    assert payload["decision"] == DECISION_START_AS_IS
    assert payload["decision_confidence"] == "HIGH"
    assert payload["next_safe_action"]["activation_allowed_after_exact_owner_phrase"] is True
    assert payload["next_safe_action"]["activation_phrase_path"] == "/tmp/activation_phrase.txt"


def test_nested_answer_folder_is_ingested(tmp_path: Path) -> None:
    pack = _oracle_pack(
        tmp_path,
        [("answer/Strategy_expert_04.06.2026.md", "Decision: START_AS_IS\n")],
    )

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE"
    assert payload["decision"] == DECISION_START_AS_IS
    assert payload["answer_path"].endswith("answer/Strategy_expert_04.06.2026.md")
    assert len(payload["answer_candidates"]) == 1


def test_start_as_is_without_preflight_stays_yellow(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Decision: START_AS_IS")])

    payload = run(_args(tmp_path, pack, None))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_START_AS_IS_PREFLIGHT_REFRESH_REQUIRED_NO_WRITE"
    assert payload["decision"] == DECISION_START_AS_IS
    assert payload["next_safe_action"]["action"] == "RERUN_PREFLIGHT_BEFORE_ANY_ACTIVATION"


def test_change_before_start_stops_activation(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Decision: CHANGE_BEFORE_START")])

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE"
    assert payload["decision"] == DECISION_CHANGE_BEFORE_START
    assert payload["next_safe_action"]["activation_allowed_after_exact_owner_phrase"] is False
    assert payload["next_safe_action"]["action"] == "DO_NOT_ACTIVATE__SCOPE_CHANGES_AND_RERUN_PREFLIGHT"


def test_start_after_changes_alias_stops_activation(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Verdict: START_AFTER_CHANGES")])

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE"
    assert payload["decision"] == DECISION_CHANGE_BEFORE_START
    assert payload["decision_matches"] == ["START_AFTER_CHANGES"]
    assert payload["next_safe_action"]["activation_allowed_after_exact_owner_phrase"] is False
    assert payload["next_safe_action"]["action"] == "DO_NOT_ACTIVATE__SCOPE_CHANGES_AND_RERUN_PREFLIGHT"


def test_start_after_changes_phrase_stops_activation(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "My operator answer: Start after changes.")])

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE"
    assert payload["decision"] == DECISION_CHANGE_BEFORE_START
    assert payload["decision_confidence"] == "MEDIUM"
    assert payload["next_safe_action"]["activation_allowed_after_exact_owner_phrase"] is False


def test_hold_paused_stops_activation(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Verdict: HOLD_PAUSED")])

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_HOLD_PAUSED_NO_WRITE"
    assert payload["decision"] == DECISION_HOLD_PAUSED
    assert payload["next_safe_action"]["action"] == "DO_NOT_ACTIVATE__KEEP_PAUSED"


def test_ambiguous_answer_stays_yellow_unclassified(tmp_path: Path) -> None:
    pack = _oracle_pack(
        tmp_path,
        [
            (
                "expert.md",
                "The setup looks promising, but budget and tracking should be considered carefully.",
            )
        ],
    )

    payload = run(_args(tmp_path, pack, _final_start_manifest(tmp_path)))

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_DECISION_UNCLASSIFIED_NO_WRITE"
    assert payload["decision"] == "UNCLASSIFIED"
    assert payload["next_safe_action"]["action"] == "DO_NOT_ACTIVATE__ANSWER_NEEDS_HUMAN_REVIEW"


def test_cli_writes_intake_packet(tmp_path: Path) -> None:
    pack = _oracle_pack(tmp_path, [("expert.md", "Decision: HOLD_PAUSED")])
    manifest = _final_start_manifest(tmp_path)
    output_root = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/ingest_line31_expert_launch_answer.py",
            "--oracle-pack",
            str(pack),
            "--output-root",
            str(output_root),
            "--final-start-manifest",
            str(manifest),
            "--run-id",
            "cli_run",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["gate"] == "YELLOW_LINE31_EXPERT_HOLD_PAUSED_NO_WRITE"
    assert (output_root / "cli_run" / "expert_answer_intake_manifest.json").exists()
    assert (output_root / "cli_run" / "expert_answer_summary.md").exists()
    assert (output_root / "cli_run" / "NEXT_SAFE_ACTION.md").exists()
