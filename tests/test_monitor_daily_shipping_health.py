from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts import monitor_daily_shipping_health as health_module
from scripts.monitor_daily_shipping_health import (
    evaluate_daily_shipping_health,
    persist_health_report,
    run_health_monitor,
    should_send_failure_alert,
)


TZ = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 7, 14, 18, 0, tzinfo=TZ)


def _manifest(
    tmp_path: Path, *, recovery_state: str = "candidate_not_installed"
) -> dict:
    project_root = tmp_path / "runtime"
    home = tmp_path / "home"
    return {
        "timezone": "Asia/Almaty",
        "project_root": str(project_root),
        "runtime_home": str(home),
        "recovery": {
            "minimum_disk_free_percent": 20,
            "automation": {
                "activation_state": recovery_state,
                "state_root": "${HOME}/Library/Application Support/AB/shipping_recovery",
            },
        },
        "observability": {
            "kaspi_api_daily_budget": {
                "warning_calls": 100,
                "hard_alert_calls": 200,
            },
            "health_monitor": {
                "recovery_max_age_seconds": 1800,
            },
        },
        "schedulers": [
            {
                "label": "calendar.job",
                "schedule": {"type": "calendar", "times": ["17:00"]},
                "stdout": "${PROJECT_ROOT}/runtime_logs/calendar.out",
                "stderr": "${PROJECT_ROOT}/runtime_logs/calendar.err",
                "health": {"mode": "calendar_log", "grace_minutes": 5},
            },
            {
                "label": "interval.job",
                "schedule": {"type": "interval", "seconds": 15},
                "stdout": "${PROJECT_ROOT}/runtime_logs/interval.out",
                "stderr": "${PROJECT_ROOT}/runtime_logs/interval.err",
                "health": {"mode": "interval_log", "max_age_seconds": 120},
            },
            {
                "label": "resident.job",
                "schedule": {"type": "interval", "seconds": 15},
                "stdout": "${PROJECT_ROOT}/runtime_logs/resident.out",
                "stderr": "${PROJECT_ROOT}/runtime_logs/resident.err",
                "health": {"mode": "running"},
            },
            {
                "label": "loaded.job",
                "schedule": {"type": "calendar", "times": ["18:20"]},
                "stdout": "${PROJECT_ROOT}/runtime_logs/loaded.out",
                "stderr": "${PROJECT_ROOT}/runtime_logs/loaded.err",
                "health": {"mode": "loaded"},
            },
        ],
    }


def _states(*, resident_running: bool = True) -> dict[str, dict]:
    return {
        "calendar.job": {"loaded": True, "running": False, "last_exit_status": 0},
        "interval.job": {"loaded": True, "running": False, "last_exit_status": 0},
        "resident.job": {
            "loaded": True,
            "running": resident_running,
            "last_exit_status": 0,
        },
        "loaded.job": {"loaded": True, "running": False, "last_exit_status": 0},
    }


def _mtimes(
    manifest: dict, *, interval_age_seconds: int = 30
) -> dict[str, float | None]:
    root = Path(manifest["project_root"])
    return {
        str(root / "runtime_logs/calendar.out"): (
            NOW - timedelta(minutes=1)
        ).timestamp(),
        str(root / "runtime_logs/calendar.err"): None,
        str(root / "runtime_logs/interval.out"): (
            NOW - timedelta(seconds=interval_age_seconds)
        ).timestamp(),
        str(root / "runtime_logs/interval.err"): None,
        str(root / "runtime_logs/resident.out"): None,
        str(root / "runtime_logs/resident.err"): None,
        str(root / "runtime_logs/loaded.out"): None,
        str(root / "runtime_logs/loaded.err"): None,
    }


def _evaluate(
    manifest: dict,
    *,
    now: datetime = NOW,
    states: dict[str, dict] | None = None,
    mtimes: dict[str, float | None] | None = None,
    disk_free_percent: float = 25.0,
    recovery_receipt: dict | None = None,
    api_total: int = 10,
    api_parse_errors: int = 0,
) -> dict:
    return evaluate_daily_shipping_health(
        manifest,
        now=now,
        scheduler_states=states if states is not None else _states(),
        log_mtimes=mtimes if mtimes is not None else _mtimes(manifest),
        disk_free_percent=disk_free_percent,
        recovery_receipt=recovery_receipt,
        api_ledger={
            "path": "/redacted/kaspi_api.jsonl",
            "total": api_total,
            "parse_errors": api_parse_errors,
        },
    )


def test_health_monitor_green_when_due_evidence_is_fresh(tmp_path: Path) -> None:
    report = _evaluate(_manifest(tmp_path))

    assert report["gate"] == "GREEN"
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["credential_values_read"] is False


def test_health_monitor_red_when_due_calendar_heartbeat_is_missing(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    mtimes = _mtimes(manifest)
    mtimes[str(Path(manifest["project_root"]) / "runtime_logs/calendar.out")] = None

    report = _evaluate(manifest, mtimes=mtimes)

    assert report["gate"] == "RED"
    assert any(
        "calendar.job" in item and "due heartbeat" in item for item in report["errors"]
    )


def test_health_monitor_distinguishes_not_due_from_failure(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    before_window = datetime(2026, 7, 14, 6, 0, tzinfo=TZ)
    mtimes = {key: None for key in _mtimes(manifest)}
    interval_path = str(Path(manifest["project_root"]) / "runtime_logs/interval.out")
    mtimes[interval_path] = (before_window - timedelta(seconds=30)).timestamp()

    report = _evaluate(manifest, now=before_window, mtimes=mtimes)

    assert report["gate"] == "YELLOW_NOT_DUE"
    assert report["ok"] is True
    assert report["errors"] == []


def test_health_monitor_red_when_interval_heartbeat_is_stale(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    report = _evaluate(manifest, mtimes=_mtimes(manifest, interval_age_seconds=121))

    assert report["gate"] == "RED"
    assert any("interval.job" in item and "stale" in item for item in report["errors"])


def test_health_monitor_red_when_required_resident_is_not_running(
    tmp_path: Path,
) -> None:
    report = _evaluate(_manifest(tmp_path), states=_states(resident_running=False))

    assert report["gate"] == "RED"
    assert any(
        "resident.job" in item and "not running" in item for item in report["errors"]
    )


def test_health_monitor_red_when_loaded_timer_last_exit_is_nonzero(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    timer = next(
        item for item in manifest["schedulers"] if item["label"] == "loaded.job"
    )
    timer["health"] = {"mode": "loaded_exit_zero"}
    states = _states()
    states["loaded.job"]["last_exit_status"] = 2

    report = _evaluate(manifest, states=states)

    assert report["gate"] == "RED"
    assert any(
        "loaded.job" in item and "last exit" in item for item in report["errors"]
    )


def test_health_monitor_red_below_disk_floor(tmp_path: Path) -> None:
    report = _evaluate(_manifest(tmp_path), disk_free_percent=19.99)

    assert report["gate"] == "RED"
    assert any("disk free" in item for item in report["errors"])


@pytest.mark.parametrize(
    ("total", "expected_gate"),
    [
        (99, "GREEN"),
        (100, "YELLOW_API_BUDGET"),
        (199, "YELLOW_API_BUDGET"),
        (200, "RED"),
    ],
)
def test_health_monitor_applies_api_budget_levels(
    tmp_path: Path, total: int, expected_gate: str
) -> None:
    report = _evaluate(_manifest(tmp_path), api_total=total)

    assert report["gate"] == expected_gate


def test_health_monitor_red_on_malformed_api_ledger(tmp_path: Path) -> None:
    report = _evaluate(_manifest(tmp_path), api_parse_errors=1)

    assert report["gate"] == "RED"
    assert any("API ledger" in item for item in report["errors"])


def test_recovery_freshness_is_skipped_until_canonical_activation(
    tmp_path: Path,
) -> None:
    report = _evaluate(_manifest(tmp_path, recovery_state="candidate_not_installed"))

    recovery_check = next(
        item for item in report["checks"] if item["check"] == "recovery_freshness"
    )
    assert recovery_check["status"] == "NOT_ACTIVE"


def test_active_recovery_requires_fresh_green_success_receipt(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, recovery_state="active_m1")
    stale = {
        "gate": "GREEN",
        "completed_at_utc": (
            NOW.astimezone(ZoneInfo("UTC")) - timedelta(seconds=1801)
        ).isoformat(),
        "credential_values_read": False,
    }

    report = _evaluate(manifest, recovery_receipt=stale)

    assert report["gate"] == "RED"
    assert any("recovery success receipt is stale" in item for item in report["errors"])


def test_active_recovery_accepts_fresh_green_success_receipt(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, recovery_state="active_m1")
    fresh = {
        "gate": "GREEN",
        "completed_at_utc": (
            NOW.astimezone(ZoneInfo("UTC")) - timedelta(minutes=5)
        ).isoformat(),
        "credential_values_read": False,
    }

    report = _evaluate(manifest, recovery_receipt=fresh)

    assert report["gate"] == "GREEN"


def test_health_report_is_owner_only_and_repo_internal_output_is_refused(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    report = {"gate": "GREEN", "ok": True}
    outside = tmp_path / "owner-state" / "latest.json"

    persist_health_report(report, path=outside, project_root=project_root)

    assert outside.exists()
    assert os.stat(outside).st_mode & 0o777 == 0o600
    assert os.stat(outside.parent).st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match="outside the repo"):
        persist_health_report(
            report, path=project_root / "latest.json", project_root=project_root
        )


def test_failure_alert_spam_guard_sends_on_transition_and_after_repeat_window() -> None:
    report = {"gate": "RED", "ok": False}

    assert (
        should_send_failure_alert({}, report, now_ts=1000, repeat_seconds=600) is True
    )
    state = {"last_gate": "RED", "last_alert_ts": 900}
    assert (
        should_send_failure_alert(state, report, now_ts=1000, repeat_seconds=600)
        is False
    )
    assert (
        should_send_failure_alert(state, report, now_ts=1500, repeat_seconds=600)
        is True
    )
    assert (
        should_send_failure_alert(
            state, {"gate": "GREEN"}, now_ts=1500, repeat_seconds=600
        )
        is False
    )


def test_alert_delivery_requires_cli_request_and_environment_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = _manifest(tmp_path)
    manifest["observability"]["health_monitor"].update(
        {"repeat_alert_seconds": 600, "state_root": str(tmp_path / "state")}
    )
    monkeypatch.setattr(
        health_module, "collect_scheduler_states", lambda *_args, **_kwargs: _states()
    )
    monkeypatch.setattr(
        health_module,
        "collect_log_mtimes",
        lambda *_args, **_kwargs: _mtimes(manifest),
    )
    monkeypatch.setattr(health_module, "collect_disk_free_percent", lambda *_args: 1.0)
    monkeypatch.setattr(health_module, "collect_recovery_receipt", lambda *_args: None)
    monkeypatch.setattr(
        health_module,
        "collect_api_ledger",
        lambda *_args, **_kwargs: {"path": "/redacted", "total": 0, "parse_errors": 0},
    )
    sent: list[str] = []
    monkeypatch.setattr(
        health_module,
        "_send_alert_best_effort",
        lambda _report: sent.append("sent") or True,
    )
    monkeypatch.delenv(health_module.ALERT_ENABLE_ENV, raising=False)
    output = tmp_path / "owner-state" / "latest.json"

    disabled = run_health_monitor(
        manifest,
        output_path=output,
        send_alert=True,
        now=NOW,
    )

    assert disabled["gate"] == "RED"
    assert disabled["alert"] == {"requested": True, "enabled": False, "sent": False}
    assert sent == []

    monkeypatch.setenv(health_module.ALERT_ENABLE_ENV, "1")
    enabled = run_health_monitor(
        manifest,
        output_path=output,
        send_alert=True,
        now=NOW + timedelta(seconds=1),
    )

    assert enabled["alert"] == {"requested": True, "enabled": True, "sent": True}
    assert sent == ["sent"]
