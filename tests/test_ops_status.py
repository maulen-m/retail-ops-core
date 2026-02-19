from __future__ import annotations

from pathlib import Path

from scripts.ops_status import run_ops_status


def test_ops_status_passes_when_all_checks_green(monkeypatch) -> None:
    def _fake_anchor(**_kwargs):
        return 0, ["anchor health PASS"]

    def _fake_validate_only(*_args, **_kwargs):
        return 0, "validate-only PASS"

    monkeypatch.setattr("scripts.ops_status.check_anchor_health", _fake_anchor)
    monkeypatch.setattr("scripts.ops_status.run_scheduler_validate_only", _fake_validate_only)

    code, summary = run_ops_status(project_root=Path("/tmp/repo"))

    assert code == 0
    assert "PASS" in summary


def test_ops_status_fails_when_anchor_health_fails(monkeypatch) -> None:
    def _fake_anchor(**_kwargs):
        return 1, ["anchor health FAIL", "ERROR: stale workbook mtime"]

    def _fake_validate_only(*_args, **_kwargs):
        return 0, "validate-only PASS"

    monkeypatch.setattr("scripts.ops_status.check_anchor_health", _fake_anchor)
    monkeypatch.setattr("scripts.ops_status.run_scheduler_validate_only", _fake_validate_only)

    code, summary = run_ops_status(project_root=Path("/tmp/repo"))

    assert code != 0
    assert "anchor health" in summary.lower()


def test_ops_status_fails_when_validate_only_fails(monkeypatch) -> None:
    def _fake_anchor(**_kwargs):
        return 0, ["anchor health PASS"]

    def _fake_validate_only(*_args, **_kwargs):
        return 2, "validate-only FAIL"

    monkeypatch.setattr("scripts.ops_status.check_anchor_health", _fake_anchor)
    monkeypatch.setattr("scripts.ops_status.run_scheduler_validate_only", _fake_validate_only)

    code, summary = run_ops_status(project_root=Path("/tmp/repo"))

    assert code != 0
    assert "validate-only" in summary.lower()
