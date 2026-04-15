from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.integrations.google_ops_board import load_ops_board_contract
from scripts import run_google_ops_board_closeout_scheduler as closeout_scheduler_mod
from scripts import run_google_ops_board_closeout_watch_scheduler as watch_mod
from scripts import run_google_ops_board_size_writeback_scheduler as writeback_scheduler_mod


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])


def _write_creds(tmp_path: Path) -> Path:
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    return creds


def test_early_closeout_watch_arms_debounce_when_board_first_becomes_ready(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    now = datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty"))

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "now_almaty", lambda: now)
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["target_date"] == "2026-04-15"
    assert state["armed_at"] == now.isoformat()


def test_early_closeout_watch_triggers_scheduler_only_after_debounce_elapsed(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 12, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[str(watch_mod.sys.executable), str(watch_mod.SCRIPT_PATH)]]
    assert not state_path.exists()


def test_early_closeout_watch_skips_when_board_is_not_ready(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "adil", "", "", "", "", ""],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": False,
            "blank_size_count": 3,
            "invalid_size_count": 0,
        },
    )
    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    assert not state_path.exists()


def test_closeout_scheduler_skips_when_closeout_already_completed(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main()

    assert rc == 0
    assert calls == []


def test_closeout_scheduler_returns_zero_when_lock_is_busy(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _BusyLock:
        def __enter__(self):
            raise RuntimeError("busy")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _BusyLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main()

    assert rc == 0
    assert calls == []


def test_size_writeback_scheduler_skips_after_successful_closeout(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        writeback_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        writeback_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = writeback_scheduler_mod.main()

    assert rc == 0
    assert calls == []
