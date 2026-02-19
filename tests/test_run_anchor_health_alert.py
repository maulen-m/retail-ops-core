from __future__ import annotations

from pathlib import Path

from scripts.run_anchor_health_alert import run_anchor_health_alert


def test_anchor_health_alert_returns_pass_when_check_is_green(monkeypatch) -> None:
    def _fake_check(**_kwargs):
        return 0, ["anchor health PASS"]

    monkeypatch.setattr("scripts.run_anchor_health_alert.check_anchor_health", _fake_check)

    code, summary = run_anchor_health_alert(project_root=Path("/tmp/repo"), send_alert=False)

    assert code == 0
    assert "PASS" in summary


def test_anchor_health_alert_sends_failure_alert_on_red(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _fake_check(**_kwargs):
        return 1, ["anchor health FAIL", "ERROR: stale workbook mtime"]

    def _fake_sender(*, error_message: str, script_name: str, context: str):
        calls.append((error_message, script_name, context))
        return True

    monkeypatch.setattr("scripts.run_anchor_health_alert.check_anchor_health", _fake_check)
    monkeypatch.setattr("scripts.run_anchor_health_alert.send_run_failure_alert", _fake_sender)

    code, summary = run_anchor_health_alert(project_root=Path("/tmp/repo"), send_alert=True)

    assert code == 1
    assert "FAIL" in summary
    assert len(calls) == 1
    assert calls[0][1] == "run_anchor_health_alert"


def test_anchor_health_alert_alert_failures_are_best_effort(monkeypatch) -> None:
    def _fake_check(**_kwargs):
        return 1, ["anchor health FAIL", "ERROR: stale workbook mtime"]

    def _fake_sender(**_kwargs):
        raise RuntimeError("telegram down")

    monkeypatch.setattr("scripts.run_anchor_health_alert.check_anchor_health", _fake_check)
    monkeypatch.setattr("scripts.run_anchor_health_alert.send_run_failure_alert", _fake_sender)

    code, summary = run_anchor_health_alert(project_root=Path("/tmp/repo"), send_alert=True)

    assert code == 1
    assert "FAIL" in summary
