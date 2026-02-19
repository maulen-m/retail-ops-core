from __future__ import annotations

from pathlib import Path

import pytest
import yaml


CONTRACT_DOC = Path("docs/WRITE_SIDE_GATING_CONTRACT.md")
MANIFEST = Path("config/write_side_gating_manifest.yaml")
VALIDATOR_SCRIPT = Path("scripts/validate_write_side_gating.py")


def _load_manifest() -> list[tuple[str, str, str]]:
    if not MANIFEST.exists():
        return []
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    rows = data.get("scripts") or []
    return [
        (
            str(row.get("path", "")),
            str(row.get("env_gate", "")),
            str(row.get("apply_flag", "")),
        )
        for row in rows
    ]


def test_write_side_contract_doc_exists_and_declares_fail_closed_policy() -> None:
    assert CONTRACT_DOC.exists(), "missing write-side gating contract doc"
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "fail-closed" in text.lower()
    assert "--apply" in text
    assert "ENABLE_" in text


def test_write_side_contract_has_manifest_and_validator() -> None:
    assert MANIFEST.exists(), "missing write-side manifest"
    assert VALIDATOR_SCRIPT.exists(), "missing write-side validator script"


@pytest.mark.parametrize(("script_path", "env_gate", "apply_flag"), _load_manifest())
def test_write_side_scripts_require_env_gate_and_apply_flag(
    script_path: str,
    env_gate: str,
    apply_flag: str,
) -> None:
    script = Path(script_path)
    text = script.read_text(encoding="utf-8")
    assert apply_flag in text, f"{script_path} missing apply flag {apply_flag}"
    assert env_gate in text, f"{script_path} missing env gate {env_gate}"
