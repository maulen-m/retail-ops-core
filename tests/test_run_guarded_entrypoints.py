from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import google_ops_board_automation_common as common_mod


@pytest.mark.parametrize(
    ("path", "entry_name"),
    [
        ("scripts/run_kaspi_import_scheduler.py", "run_kaspi_import_scheduler"),
        (
            "scripts/run_google_ops_board_publish_scheduler.py",
            "run_google_ops_board_publish_scheduler",
        ),
        (
            "scripts/run_google_ops_board_closeout_watch_scheduler.py",
            "run_google_ops_board_closeout_watch_scheduler",
        ),
        (
            "scripts/run_google_ops_board_closeout_scheduler.py",
            "run_google_ops_board_closeout_scheduler",
        ),
        (
            "scripts/run_google_ops_board_prewindow_health_scheduler.py",
            "run_google_ops_board_prewindow_health_scheduler",
        ),
    ],
)
def test_scheduler_entrypoints_use_common_guard(path: str, entry_name: str) -> None:
    source = Path(path).read_text(encoding="utf-8")
    assert "if __name__ == \"__main__\":" in source
    assert re.search(rf'run_guarded\(\s*"{re.escape(entry_name)}"', source)


def test_run_guarded_records_stopline_and_critical_alert_on_uncaught_exception(
    monkeypatch,
    tmp_path: Path,
) -> None:
    stopline_root = tmp_path / "runs" / "ops_stoplines"
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(common_mod, "DEFAULT_OPS_STOPLINE_ROOT", stopline_root)
    monkeypatch.setattr(
        common_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )
    monkeypatch.setattr(common_mod.sys, "argv", ["entry.py", "--flag"])
    monkeypatch.chdir(tmp_path)

    def _raise() -> int:
        raise RuntimeError("scheduler exploded")

    assert common_mod.run_guarded("sample_scheduler", _raise) == 1
    stoplines = list(stopline_root.glob("*_sample_scheduler.json"))
    assert len(stoplines) == 1
    payload = json.loads(stoplines[0].read_text(encoding="utf-8"))
    assert payload["exception"] == "RuntimeError: scheduler exploded"
    assert "raise RuntimeError" in payload["traceback"]
    assert payload["argv"] == ["entry.py", "--flag"]
    assert payload["cwd"] == str(tmp_path)
    assert alerts[0]["severity"] == "CRITICAL"
    assert str(stoplines[0]) in alerts[0]["lines"][1]


def test_run_guarded_preserves_success_return_path(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(common_mod, "DEFAULT_OPS_STOPLINE_ROOT", tmp_path / "stoplines")
    monkeypatch.setattr(
        common_mod,
        "enqueue_alert",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no alert on success")),
    )

    assert common_mod.run_guarded("healthy_scheduler", lambda: calls.append("main") or 75) == 75
    assert calls == ["main"]
    assert not (tmp_path / "stoplines").exists()


def test_lock_contention_alerts_every_tenth_and_resets_after_acquisition(
    monkeypatch,
    tmp_path: Path,
) -> None:
    counter_path = tmp_path / "runtime" / "state" / "ops_lock_contention_counters.json"
    lock_path = tmp_path / "runtime" / "locks" / "board.lock"
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(common_mod, "DEFAULT_LOCK_CONTENTION_COUNTER_PATH", counter_path)
    monkeypatch.setattr(
        common_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )

    for expected in range(1, 21):
        assert common_mod.record_lock_contention("publish") == expected
    assert [alert["lines"][1] for alert in alerts] == [
        "Consecutive lock-contention exits: 10",
        "Consecutive lock-contention exits: 20",
    ]

    with common_mod.GoogleOpsBoardAutomationLock(lock_path, entry_name="publish"):
        pass
    assert common_mod.record_lock_contention("publish") == 1
    state = json.loads(counter_path.read_text(encoding="utf-8"))
    assert state["entries"]["publish"] == 1
