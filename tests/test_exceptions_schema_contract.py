from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_exceptions_schema import validate_exceptions_schema


def _payload(*, ok: bool, status: str, exceptions: list[dict]) -> dict:
    return {
        "generated_at": "2026-02-26T10:00:00Z",
        "as_of": "2026-02-25",
        "status": status,
        "ok": ok,
        "steps": [],
        "exceptions": exceptions,
    }


def _good_exception() -> dict:
    return {
        "id": "build_domain_scorecards:1",
        "step": "build_domain_scorecards",
        "domain": "domain",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Fix domain scorecards and rerun strict gates.",
        "evidence_paths": ["exports/validation/board_v11_2026-02-26/V11-R2_exceptions_schema/targeted_tests_red.md"],
        "rc": 1,
        "reason": "domain scorecards failed",
    }


def test_validate_exceptions_schema_passes_on_valid_payload(tmp_path: Path) -> None:
    payload = _payload(ok=False, status="RED", exceptions=[_good_exception()])
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_exceptions_schema(path, strict=True)
    assert report["ok"] is True
    assert report["critical_count"] == 1


def test_validate_exceptions_schema_fails_on_missing_required_fields(tmp_path: Path) -> None:
    broken = _good_exception()
    broken.pop("owner")
    payload = _payload(ok=False, status="RED", exceptions=[broken])
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_exceptions_schema(path, strict=False)
    assert report["ok"] is False
    assert any("owner" in err for err in report["errors"])

    with pytest.raises(RuntimeError):
        validate_exceptions_schema(path, strict=True)


def test_validate_exceptions_schema_fails_when_ok_true_but_critical_exists(tmp_path: Path) -> None:
    payload = _payload(ok=True, status="GREEN", exceptions=[_good_exception()])
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_exceptions_schema(path, strict=False)
    assert report["ok"] is False
    assert any("critical exceptions" in err for err in report["errors"])
