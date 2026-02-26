from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import triage_exceptions as triage_mod
from scripts.run_daily_autopilot import EXCEPTION_POLICY


REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK_PATH = REPO_ROOT / "docs" / "ops" / "EXCEPTION_PLAYBOOK.md"


def _write_exceptions(path: Path, *, step: str, severity: str = "critical") -> None:
    payload = {
        "generated_at": "2026-02-26T00:00:00Z",
        "as_of": "2026-02-26",
        "status": "RED",
        "ok": False,
        "schema_version": "v1",
        "steps": [],
        "exceptions": [
            {
                "id": f"{step}:1:1",
                "step": step,
                "domain": "execution",
                "severity": severity,
                "owner": "ops-codex",
                "recommended_action": "fix it",
                "evidence_paths": ["exports/validation/example.md"],
                "rc": 1,
                "reason": "simulated failure",
            }
        ],
        "critical_count": 1 if severity == "critical" else 0,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_allowlist(path: Path, codes: dict[str, dict[str, str]]) -> None:
    payload = {"version": 1, "codes": codes}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_playbook_covers_all_exception_policy_codes() -> None:
    mapping = triage_mod._parse_playbook(PLAYBOOK_PATH)  # noqa: SLF001 - contract test
    missing = sorted(code for code in EXCEPTION_POLICY if code not in mapping)
    assert not missing, f"playbook missing policy codes: {missing}"


def test_triage_fails_on_unknown_step_strict(tmp_path: Path) -> None:
    exceptions_path = tmp_path / "exceptions.json"
    allowlist_path = tmp_path / "allowlist.json"
    _write_exceptions(exceptions_path, step="unknown_step", severity="critical")
    _write_allowlist(allowlist_path, {})

    with pytest.raises(RuntimeError, match="unknown_codes=1"):
        triage_mod.triage_exceptions(
            exceptions_path=exceptions_path,
            playbook_path=PLAYBOOK_PATH,
            allowlist_path=allowlist_path,
            output_json=tmp_path / "triage.json",
            output_md=tmp_path / "triage.md",
            strict=True,
        )


def test_triage_fails_when_critical_not_allowlisted(tmp_path: Path) -> None:
    exceptions_path = tmp_path / "exceptions.json"
    allowlist_path = tmp_path / "allowlist.json"
    _write_exceptions(exceptions_path, step="system_doctor", severity="critical")
    _write_allowlist(allowlist_path, {})

    with pytest.raises(RuntimeError, match="critical_unallowlisted=1"):
        triage_mod.triage_exceptions(
            exceptions_path=exceptions_path,
            playbook_path=PLAYBOOK_PATH,
            allowlist_path=allowlist_path,
            output_json=tmp_path / "triage.json",
            output_md=tmp_path / "triage.md",
            strict=True,
        )


def test_triage_passes_with_active_allowlist(tmp_path: Path) -> None:
    exceptions_path = tmp_path / "exceptions.json"
    allowlist_path = tmp_path / "allowlist.json"
    _write_exceptions(exceptions_path, step="system_doctor", severity="critical")
    _write_allowlist(
        allowlist_path,
        {
            "system_doctor": {
                "reason": "temporary runtime instability",
                "expires_on": "2026-03-15",
            }
        },
    )

    report = triage_mod.triage_exceptions(
        exceptions_path=exceptions_path,
        playbook_path=PLAYBOOK_PATH,
        allowlist_path=allowlist_path,
        output_json=tmp_path / "triage.json",
        output_md=tmp_path / "triage.md",
        strict=True,
    )

    assert report["ok"] is True
    assert report["status"] == "PASS"
    assert (tmp_path / "triage.json").exists()
    assert (tmp_path / "triage.md").exists()
