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


def test_anchor_health_alert_spam_guard_suppresses_repeated_failure_within_window(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, str, str]] = []

    def _fake_check(**_kwargs):
        return 1, ["anchor health FAIL", "ERROR: stale workbook mtime"]

    def _fake_sender(*, error_message: str, script_name: str, context: str):
        calls.append((error_message, script_name, context))
        return True

    monkeypatch.setattr("scripts.run_anchor_health_alert.check_anchor_health", _fake_check)
    monkeypatch.setattr("scripts.run_anchor_health_alert.send_run_failure_alert", _fake_sender)

    state_path = tmp_path / "anchor_alert_state.json"
    code1, _ = run_anchor_health_alert(
        project_root=Path("/tmp/repo"),
        send_alert=True,
        state_path=state_path,
        repeat_alert_seconds=3600,
        now_ts=1700000000.0,
    )
    code2, _ = run_anchor_health_alert(
        project_root=Path("/tmp/repo"),
        send_alert=True,
        state_path=state_path,
        repeat_alert_seconds=3600,
        now_ts=1700000500.0,
    )

    assert code1 == 1
    assert code2 == 1
    assert len(calls) == 1


def test_anchor_health_alert_spam_guard_realerts_after_recovery(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []
    checks = iter(
        [
            (1, ["anchor health FAIL", "ERROR: stale workbook mtime"]),
            (0, ["anchor health PASS"]),
            (1, ["anchor health FAIL", "ERROR: stale workbook mtime"]),
        ]
    )

    def _fake_check(**_kwargs):
        return next(checks)

    def _fake_sender(*, error_message: str, script_name: str, context: str):
        calls.append((error_message, script_name, context))
        return True

    monkeypatch.setattr("scripts.run_anchor_health_alert.check_anchor_health", _fake_check)
    monkeypatch.setattr("scripts.run_anchor_health_alert.send_run_failure_alert", _fake_sender)

    state_path = tmp_path / "anchor_alert_state.json"
    run_anchor_health_alert(
        project_root=Path("/tmp/repo"),
        send_alert=True,
        state_path=state_path,
        repeat_alert_seconds=3600,
        now_ts=1700000000.0,
    )
    run_anchor_health_alert(
        project_root=Path("/tmp/repo"),
        send_alert=True,
        state_path=state_path,
        repeat_alert_seconds=3600,
        now_ts=1700000100.0,
    )
    run_anchor_health_alert(
        project_root=Path("/tmp/repo"),
        send_alert=True,
        state_path=state_path,
        repeat_alert_seconds=3600,
        now_ts=1700000200.0,
    )

    assert len(calls) == 2
