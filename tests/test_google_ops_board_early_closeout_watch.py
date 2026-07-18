from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.integrations.google_ops_board import load_ops_board_contract
from scripts import google_ops_board_automation_common as common_mod
from scripts import run_google_ops_board_closeout_scheduler as closeout_scheduler_mod
from scripts import run_google_ops_board_closeout_watch_scheduler as watch_mod
from scripts import run_google_ops_board_size_writeback_scheduler as writeback_scheduler_mod


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values
        self.update_calls: list[dict[str, object]] = []

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])

    def update_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, object]]) -> None:
        if rows:
            self.update_calls.append({"tab_name": tab_name, "headers": headers, "rows": rows})
        matrix = self._tab_values.setdefault(tab_name, [headers])
        for update in rows:
            sheet_row = int(update["sheet_row"])
            while len(matrix) < sheet_row:
                matrix.append([""] * len(headers))
            matrix[sheet_row - 1] = [str(update["row"].get(header, "")) for header in headers]

    def update_cells(self, updates: list[dict[str, object]]) -> None:
        if updates:
            self.update_calls.append({"cells": updates})
        for update in updates:
            tab_name, cell = str(update["range"]).split("!", 1)
            column_letters = "".join(character for character in cell if character.isalpha())
            sheet_row = int("".join(character for character in cell if character.isdigit()))
            column_index = 0
            for character in column_letters:
                column_index = column_index * 26 + (ord(character.upper()) - 64)
            matrix = self._tab_values[tab_name]
            while len(matrix) < sheet_row:
                matrix.append([])
            while len(matrix[sheet_row - 1]) < column_index:
                matrix[sheet_row - 1].append("")
            matrix[sheet_row - 1][column_index - 1] = str(update.get("value", ""))


def _write_creds(tmp_path: Path) -> Path:
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    return creds


def _stub_closeout_health_green(monkeypatch, tmp_path: Path) -> None:
    return None


@pytest.fixture(autouse=True)
def _isolate_live_closeout_halt_barrier(monkeypatch):
    common_mod.resolved_auto_probable_closeout_time.cache_clear()
    common_mod.resolved_early_closeout_watch_window.cache_clear()
    common_mod.resolved_ready_debounce_seconds.cache_clear()

    def _allow_automation(**_kwargs):
        return {
            "blocked": False,
            "reason": "NO_HALT_BARRIER",
            "request_halted": False,
            "barrier": {},
        }

    monkeypatch.setattr(watch_mod, "evaluate_closeout_halt_barrier", _allow_automation)
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "evaluate_closeout_halt_barrier",
        _allow_automation,
    )
    monkeypatch.setattr(common_mod, "flush_held", lambda _reason: {"attempted": 0, "delivered": 0})
    monkeypatch.setattr(common_mod, "enqueue_alert", lambda **_kwargs: False)
    monkeypatch.setattr(watch_mod, "enqueue_alert", lambda **_kwargs: False)
    monkeypatch.setattr(closeout_scheduler_mod, "reset_lock_contention", lambda _entry: None)
    monkeypatch.setattr(closeout_scheduler_mod, "record_lock_contention", lambda _entry: 1)
    yield
    common_mod.resolved_auto_probable_closeout_time.cache_clear()
    common_mod.resolved_early_closeout_watch_window.cache_clear()
    common_mod.resolved_ready_debounce_seconds.cache_clear()


def test_early_closeout_watch_window_starts_for_morning_employee_ready() -> None:
    tz = ZoneInfo("Asia/Almaty")

    assert common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 9, 0, tzinfo=tz))
    assert common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 10, 0, tzinfo=tz))
    assert common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 19, 6, tzinfo=tz))
    assert common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 20, 30, tzinfo=tz))
    assert common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 23, 59, tzinfo=tz))
    assert not common_mod.within_early_closeout_watch_window(datetime(2026, 4, 15, 8, 59, tzinfo=tz))


def test_watch_window_and_ready_debounce_defaults_remain_unchanged(monkeypatch) -> None:
    monkeypatch.delenv(common_mod.EARLY_CLOSEOUT_WATCH_START_HOUR_ENV, raising=False)
    monkeypatch.delenv(common_mod.EARLY_CLOSEOUT_WATCH_END_HOUR_ENV, raising=False)
    monkeypatch.delenv(common_mod.READY_DEBOUNCE_SECONDS_ENV, raising=False)
    common_mod.resolved_early_closeout_watch_window.cache_clear()
    common_mod.resolved_ready_debounce_seconds.cache_clear()

    assert common_mod.resolved_early_closeout_watch_window() == (9, 24)
    assert common_mod.resolved_ready_debounce_seconds() == 60


def test_watch_window_honors_environment(monkeypatch) -> None:
    tz = ZoneInfo("Asia/Almaty")
    monkeypatch.setenv(common_mod.EARLY_CLOSEOUT_WATCH_START_HOUR_ENV, "10")
    monkeypatch.setenv(common_mod.EARLY_CLOSEOUT_WATCH_END_HOUR_ENV, "22")
    common_mod.resolved_early_closeout_watch_window.cache_clear()

    assert common_mod.resolved_early_closeout_watch_window() == (10, 22)
    assert not common_mod.within_early_closeout_watch_window(
        datetime(2026, 4, 15, 9, 59, tzinfo=tz)
    )
    assert common_mod.within_early_closeout_watch_window(
        datetime(2026, 4, 15, 10, 0, tzinfo=tz)
    )
    assert not common_mod.within_early_closeout_watch_window(
        datetime(2026, 4, 15, 22, 0, tzinfo=tz)
    )


def test_ready_debounce_honors_environment(monkeypatch) -> None:
    tz = ZoneInfo("Asia/Almaty")
    target_date = date(2026, 4, 15)
    armed_at = datetime(2026, 4, 15, 17, 0, tzinfo=tz)
    state = {
        "target_date": target_date.isoformat(),
        "ready_set_at": "ready-1",
        "armed_at": armed_at.isoformat(),
    }
    monkeypatch.setenv(common_mod.READY_DEBOUNCE_SECONDS_ENV, "90")
    common_mod.resolved_ready_debounce_seconds.cache_clear()

    waiting = common_mod.evaluate_ready_debounce(
        state=state,
        target_date=target_date,
        now=datetime(2026, 4, 15, 17, 1, tzinfo=tz),
        ready=True,
        ready_set_at="ready-1",
    )
    triggered = common_mod.evaluate_ready_debounce(
        state=state,
        target_date=target_date,
        now=datetime(2026, 4, 15, 17, 1, 30, tzinfo=tz),
        ready=True,
        ready_set_at="ready-1",
    )

    assert waiting["action"] == "wait"
    assert waiting["remaining_seconds"] == 30
    assert triggered["action"] == "trigger"


def test_invalid_watch_window_environment_warns_once_and_uses_default(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv(common_mod.EARLY_CLOSEOUT_WATCH_START_HOUR_ENV, "24")
    monkeypatch.setenv(common_mod.EARLY_CLOSEOUT_WATCH_END_HOUR_ENV, "9")
    common_mod.resolved_early_closeout_watch_window.cache_clear()

    assert common_mod.resolved_early_closeout_watch_window() == (9, 24)
    assert common_mod.resolved_early_closeout_watch_window() == (9, 24)
    captured = capsys.readouterr()
    assert captured.err.count("WARN:") == 1
    assert "using default 09:00-24:00" in captured.err


def test_invalid_ready_debounce_environment_warns_once_and_uses_default(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv(common_mod.READY_DEBOUNCE_SECONDS_ENV, "invalid")
    common_mod.resolved_ready_debounce_seconds.cache_clear()

    assert common_mod.resolved_ready_debounce_seconds() == 60
    assert common_mod.resolved_ready_debounce_seconds() == 60
    captured = capsys.readouterr()
    assert captured.err.count("WARN:") == 1
    assert "using default 60" in captured.err


def test_auto_probable_closeout_defaults_remain_1857(monkeypatch) -> None:
    tz = ZoneInfo("Asia/Almaty")
    monkeypatch.delenv(common_mod.AUTO_PROBABLE_FILL_HOUR_ENV, raising=False)
    monkeypatch.delenv(common_mod.AUTO_PROBABLE_FILL_MINUTE_ENV, raising=False)
    common_mod.resolved_auto_probable_closeout_time.cache_clear()

    assert common_mod.resolved_auto_probable_closeout_time() == (18, 57)
    assert not common_mod.auto_probable_closeout_cutoff_reached(
        datetime(2026, 4, 15, 18, 56, tzinfo=tz)
    )
    assert common_mod.auto_probable_closeout_cutoff_reached(
        datetime(2026, 4, 15, 18, 57, tzinfo=tz)
    )


def test_auto_probable_closeout_honors_1945_environment(monkeypatch) -> None:
    tz = ZoneInfo("Asia/Almaty")
    monkeypatch.setenv(common_mod.AUTO_PROBABLE_FILL_HOUR_ENV, "19")
    monkeypatch.setenv(common_mod.AUTO_PROBABLE_FILL_MINUTE_ENV, "45")
    common_mod.resolved_auto_probable_closeout_time.cache_clear()

    assert common_mod.resolved_auto_probable_closeout_time() == (19, 45)
    assert not common_mod.auto_probable_closeout_cutoff_reached(
        datetime(2026, 4, 15, 18, 57, tzinfo=tz)
    )
    assert not common_mod.auto_probable_closeout_cutoff_reached(
        datetime(2026, 4, 15, 19, 44, tzinfo=tz)
    )
    assert common_mod.auto_probable_closeout_cutoff_reached(
        datetime(2026, 4, 15, 19, 45, tzinfo=tz)
    )


def test_invalid_auto_probable_closeout_environment_warns_once_and_uses_default(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv(common_mod.AUTO_PROBABLE_FILL_HOUR_ENV, "24")
    monkeypatch.setenv(common_mod.AUTO_PROBABLE_FILL_MINUTE_ENV, "invalid")
    common_mod.resolved_auto_probable_closeout_time.cache_clear()

    assert common_mod.resolved_auto_probable_closeout_time() == (18, 57)
    assert common_mod.resolved_auto_probable_closeout_time() == (18, 57)
    captured = capsys.readouterr()
    assert captured.err.count("WARN:") == 1
    assert "using default 18:57" in captured.err


def test_auto_prepare_warning_is_silent_when_nothing_was_applied(monkeypatch) -> None:
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(watch_mod, "enqueue_alert", lambda **kwargs: alerts.append(kwargs) or False)

    emitted = watch_mod._enqueue_auto_prepare_warning(
        target_date=date(2026, 4, 15),
        auto_prepare={
            "salesraw_updates_applied": 0,
            "applied_rows": [],
            "run_control_updated": False,
        },
    )

    assert emitted is False
    assert alerts == []


def test_hold_fast_path_reads_only_run_control_and_skips_deep_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    target_date = date(2026, 4, 15)
    contract = load_ops_board_contract()
    headers = contract.tabs["Run_Control"].headers
    row = {header: "" for header in headers}
    row.update(
        {
            "target_date": target_date.isoformat(),
            "ready_for_closeout": "HOLD",
        }
    )

    class _CountingClient(_FakeClient):
        def __init__(self):
            super().__init__({"Run_Control": [headers, [row[header] for header in headers]]})
            self.read_tabs: list[str] = []

        def get_tab_values(self, tab_name: str):
            self.read_tabs.append(tab_name)
            return super().get_tab_values(tab_name)

    client = _CountingClient()
    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_ALLOW_AUTO_PROBABLE_FILL", raising=False)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: target_date)
    monkeypatch.setattr(
        watch_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        watch_mod,
        "closeout_completion_state",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("HOLD must not inspect manifest or ledger completion")
        ),
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("HOLD must not read SalesRaw or DB readiness")
        ),
    )

    assert watch_mod.main() == 0
    assert client.read_tabs == ["Run_Control"]


def test_missing_target_run_control_row_fails_after_only_run_control_read(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    target_date = date(2026, 4, 15)
    contract = load_ops_board_contract()

    class _CountingClient(_FakeClient):
        def __init__(self):
            super().__init__({"Run_Control": [contract.tabs["Run_Control"].headers]})
            self.read_tabs: list[str] = []

        def get_tab_values(self, tab_name: str):
            self.read_tabs.append(tab_name)
            return super().get_tab_values(tab_name)

    client = _CountingClient()
    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_ALLOW_AUTO_PROBABLE_FILL", raising=False)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: target_date)
    monkeypatch.setattr(
        watch_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        watch_mod,
        "closeout_completion_state",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing Run_Control must not inspect completion evidence")
        ),
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing Run_Control must not read SalesRaw or DB")
        ),
    )

    assert watch_mod.main() == 1
    assert client.read_tabs == ["Run_Control"]


def test_halt_barrier_requires_hold_or_strictly_fresh_ready_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    held_flush_reasons: list[str] = []
    monkeypatch.setattr(
        common_mod,
        "flush_held",
        lambda reason: held_flush_reasons.append(reason) or {"attempted": 0, "delivered": 0},
    )
    tz = ZoneInfo("Asia/Almaty")
    barrier_path = tmp_path / "halt_barrier.json"
    target_date = date(2026, 4, 15)
    common_mod.persist_closeout_halt_barrier(
        target_date=target_date,
        requested_at=datetime(2026, 4, 15, 17, 0, tzinfo=tz),
        source="test:/halt",
        path=barrier_path,
    )

    stale = common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-04-15T16:59:00+05:00",
        },
        request_ready_set_at="2026-04-15T16:59:00+05:00",
        path=barrier_path,
    )
    assert stale["blocked"] is True
    assert stale["request_halted"] is True

    hold = common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "HOLD",
            "ready_set_at": "",
        },
        path=barrier_path,
    )
    assert hold["blocked"] is True
    assert hold["barrier"]["state"] == "HOLD_CONFIRMED"

    blank_fresh = common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "",
        },
        path=barrier_path,
    )
    assert blank_fresh["blocked"] is True
    assert blank_fresh["allow_fresh_blank_ready"] is True

    fresh = common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-04-15T17:01:00+05:00",
        },
        request_ready_set_at="2026-04-15T17:01:00+05:00",
        path=barrier_path,
    )
    assert fresh["blocked"] is False
    assert fresh["barrier"]["state"] == "SUPERSEDED_BY_FRESH_READY"
    assert held_flush_reasons == [
        "halt barrier superseded by fresh READY for 2026-04-15"
    ]

    old_in_flight = common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-04-15T17:01:00+05:00",
        },
        request_ready_set_at="2026-04-15T16:59:00+05:00",
        path=barrier_path,
    )
    assert old_in_flight["blocked"] is True
    assert old_in_flight["request_halted"] is True


def test_unreadable_halt_barrier_enqueues_hourly_deduplicated_critical_alert(
    monkeypatch,
    tmp_path: Path,
) -> None:
    barrier_path = tmp_path / "halt_barrier.json"
    barrier_path.write_text("{not-json", encoding="utf-8")
    alerts: list[dict[str, object]] = []
    monkeypatch.setattr(
        common_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )
    now = datetime(2026, 7, 18, 10, 30, tzinfo=ZoneInfo("Asia/Almaty"))

    for _ in range(2):
        gate = common_mod.evaluate_closeout_halt_barrier(
            target_date=date(2026, 7, 18),
            run_control_row={},
            now=now,
            path=barrier_path,
        )
        assert gate["blocked"] is True
        assert gate["reason"] == "HALT_BARRIER_UNREADABLE"

    assert len(alerts) == 2
    assert alerts[0]["severity"] == "CRITICAL"
    assert alerts[0]["dedup_key"] == alerts[1]["dedup_key"]
    assert alerts[0]["dedup_key"].endswith(str(barrier_path))


def test_newer_halt_supersedes_prior_halt_after_intervening_ready(
    tmp_path: Path,
) -> None:
    tz = ZoneInfo("Asia/Almaty")
    barrier_path = tmp_path / "halt_barrier.json"
    target_date = date(2026, 4, 15)
    common_mod.persist_closeout_halt_barrier(
        target_date=target_date,
        requested_at=datetime(2026, 4, 15, 17, 0, tzinfo=tz),
        source="test:/halt",
        request_key="telegram_update:1",
        path=barrier_path,
    )
    first_ready = {
        "target_date": "2026-04-15",
        "ready_for_closeout": "READY",
        "ready_set_at": "2026-04-15T17:01:00+05:00",
    }
    assert common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row=first_ready,
        request_ready_set_at=first_ready["ready_set_at"],
        path=barrier_path,
    )["blocked"] is False

    second = common_mod.persist_closeout_halt_barrier(
        target_date=target_date,
        requested_at=datetime(2026, 4, 15, 17, 2, tzinfo=tz),
        source="test:/halt",
        request_key="telegram_update:2",
        path=barrier_path,
    )
    assert second["state"] == "PENDING_HOLD"
    assert second["halt_requested_at"] == "2026-04-15T17:02:00+05:00"
    assert second["supersedes_halt_request_key"] == "telegram_update:1"
    assert common_mod.evaluate_closeout_halt_barrier(
        target_date=target_date,
        run_control_row=first_ready,
        request_ready_set_at=first_ready["ready_set_at"],
        path=barrier_path,
    )["blocked"] is True

    replay = common_mod.persist_closeout_halt_barrier(
        target_date=target_date,
        requested_at=datetime(2026, 4, 15, 17, 3, tzinfo=tz),
        source="test:/halt",
        request_key="telegram_update:2",
        path=barrier_path,
    )
    assert replay["halt_requested_at"] == "2026-04-15T17:02:00+05:00"


def test_prior_day_pending_halt_allows_new_day_blank_ready_stamp_only(
    tmp_path: Path,
) -> None:
    tz = ZoneInfo("Asia/Almaty")
    barrier_path = tmp_path / "halt_barrier.json"
    common_mod.persist_closeout_halt_barrier(
        target_date=date(2026, 4, 14),
        requested_at=datetime(2026, 4, 14, 18, 0, tzinfo=tz),
        source="test:/halt",
        request_key="telegram_update:10",
        path=barrier_path,
    )
    blank_new_day = common_mod.evaluate_closeout_halt_barrier(
        target_date=date(2026, 4, 15),
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "",
        },
        path=barrier_path,
    )
    assert blank_new_day["blocked"] is True
    assert blank_new_day["allow_fresh_blank_ready"] is True

    stamped_new_day = common_mod.evaluate_closeout_halt_barrier(
        target_date=date(2026, 4, 15),
        run_control_row={
            "target_date": "2026-04-15",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-04-15T09:01:00+05:00",
        },
        request_ready_set_at="2026-04-15T09:01:00+05:00",
        path=barrier_path,
    )
    assert stamped_new_day["blocked"] is False

    old_request = common_mod.evaluate_closeout_halt_barrier(
        target_date=date(2026, 4, 14),
        run_control_row={
            "target_date": "2026-04-14",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-04-14T17:00:00+05:00",
        },
        request_ready_set_at="2026-04-14T17:00:00+05:00",
        path=barrier_path,
    )
    assert old_request["blocked"] is True
    assert old_request["request_halted"] is True


def test_early_closeout_watcher_stops_before_readiness_when_halt_barrier_blocks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    target_date = date(2026, 4, 15)
    now = datetime(2026, 4, 15, 17, 0, tzinfo=ZoneInfo("Asia/Almaty"))
    contract = load_ops_board_contract()
    row = {
        "target_date": "2026-04-15",
        "ready_for_closeout": "READY",
        "ready_set_at": "2026-04-15T16:59:00+05:00",
    }
    headers = contract.tabs["Run_Control"].headers
    client = _FakeClient(
        {"Run_Control": [headers, [row.get(header, "") for header in headers]]}
    )
    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: target_date)
    monkeypatch.setattr(watch_mod, "now_almaty", lambda: now)
    monkeypatch.setattr(
        watch_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        watch_mod,
        "closeout_completion_state",
        lambda **_kwargs: {"row": row, "completed": False, "status": ""},
    )
    monkeypatch.setattr(
        watch_mod,
        "evaluate_closeout_halt_barrier",
        lambda **_kwargs: {
            "blocked": True,
            "reason": "REQUEST_HALTED",
            "allow_fresh_blank_ready": False,
        },
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("readiness must not run behind halt barrier")
        ),
    )

    assert watch_mod.main() == 0


def test_ready_identity_stamp_never_writes_a_wrong_date_fallback_row() -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-14", "READY", "adil", "", "", "", "", ""],
            ]
        }
    )

    selected = watch_mod._stamp_blank_ready_identity(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 15),
        now=datetime(2026, 4, 15, 9, 0, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert selected == {}
    assert client.update_calls == []
    assert client.get_tab_values("Run_Control")[1][3] == ""


def test_auto_probable_closeout_never_writes_sizes_or_ready_to_wrong_date(
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-14", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY", "2026-04-15", "Universal", "", "", "1",
                    "Product", "1001", "", "L", "Offer", "SKU-1", "1",
                    "line-1", "DECLARED_ORDER", "HIGH",
                ],
            ],
        }
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["target_date_match"] is False
    assert report["salesraw_updates_applied"] == 0
    assert report["run_control_updated"] is False
    assert client.update_calls == []
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


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
    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    _stub_closeout_health_green(monkeypatch, tmp_path)
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
            "ready_set_at": now.isoformat(),
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
    assert state["ready_set_at"] == now.isoformat()
    assert state["armed_at"] == now.isoformat()


def test_early_closeout_watch_triggers_scheduler_only_after_debounce_elapsed(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", "BLOCKED"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    child_envs: list[dict[str, str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "ready_set_at": "2026-04-15T17:10:00+05:00",
                "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or child_envs.append(dict(env)) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[
        str(watch_mod.sys.executable),
        str(watch_mod.SCRIPT_PATH),
        "--expected-target-date",
        "2026-04-15",
        "--expected-ready-set-at",
        "2026-04-15T17:10:00+05:00",
    ]]
    assert child_envs[0]["KASPI_API_CALL_LEDGER_PATH"].endswith("runtime/api_ledger/kaspi_api_2026-04-15.jsonl")
    assert "AB_GOOGLE_OPS_BOARD_FORCE_FRESH_CLOSEOUT" not in child_envs[0]
    assert not state_path.exists()


def test_early_closeout_watch_skips_completed_exact_ready_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T09:00:00+05:00", "", "", "run-1", "OK"],
            ]
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    child_envs: list[dict[str, str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "ready_set_at": "2026-04-15T09:00:00+05:00",
                "armed_at": datetime(2026, 4, 15, 9, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
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
        lambda: datetime(2026, 4, 15, 9, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "closeout_completion_state",
        lambda **_kwargs: {
            "completed": True,
            "status": "OK",
            "target_date": "2026-04-15",
            "run_id": "run-1",
            "row": {
                "target_date": "2026-04-15",
                "ready_for_closeout": "READY",
                "ready_set_at": "2026-04-15T09:00:00+05:00",
            },
        },
    )
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
        lambda command, cwd, env: calls.append(command) or child_envs.append(dict(env)) or _Result(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    assert child_envs == []
    assert not state_path.exists()


def test_closeout_scheduler_ignores_stale_force_fresh_and_defers_fresh_run_to_watcher(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    inspected: list[bool] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_FORCE_FRESH_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **kwargs: inspected.append(True) or False,
    )

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Result:
        returncode = 0

    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = closeout_scheduler_mod.main([])

    assert rc == 0
    assert inspected == [True]
    assert calls == []


def test_closeout_scheduler_does_not_resume_invalid_pinned_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    def _invalid_checkpoint(**_kwargs):
        closeout_scheduler_mod._LAST_CLOSEOUT_STATE = {
            "status": "OK",
            "delivery_state": {
                "status": "PINNED_MANIFEST_SHA256_MISMATCH",
                "manifest_path": str(tmp_path / "send_batch_manifest.json"),
            },
            "request_identity": {
                "target_date": "2026-04-15",
                "ready_set_at": "2026-04-15T17:10:00+05:00",
            },
        }
        return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(closeout_scheduler_mod, "_closeout_already_completed", _invalid_checkpoint)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main([])

    assert rc == 0
    assert calls == []


def test_closeout_scheduler_does_not_resume_missing_telegram_ledger_after_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    def _uncertain_checkpoint(**_kwargs):
        closeout_scheduler_mod._LAST_CLOSEOUT_STATE = {
            "status": "OK",
            "delivery_resume_safe": False,
            "delivery_state": {
                "status": "TELEGRAM_LEDGER_MISSING_AFTER_ATTEMPT",
                "manifest_path": str(tmp_path / "send_batch_manifest.json"),
            },
            "request_identity": {
                "target_date": "2026-04-15",
                "ready_set_at": "2026-04-15T17:10:00+05:00",
            },
        }
        return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(
        closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15)
    )
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        _uncertain_checkpoint,
    )
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main([])

    assert rc == 0
    assert calls == []


def test_early_closeout_watch_delegates_health_gate_to_closeout_runner(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", "BLOCKED"],
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
                    "ready_set_at": "2026-04-15T17:10:00+05:00",
                    "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )
    monkeypatch.setattr(
        watch_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or type("Result", (), {"returncode": 0})(),
    )

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[
        str(watch_mod.sys.executable),
        str(watch_mod.SCRIPT_PATH),
        "--expected-target-date",
        "2026-04-15",
        "--expected-ready-set-at",
        "2026-04-15T17:10:00+05:00",
    ]]
    assert not state_path.exists()


def test_early_closeout_watch_auto_fills_blank_sizes_after_1857_and_triggers_without_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "2XL",
                    "Комплект ACMEWEAR OF_LINE51_BLK_2XL_58",
                    "CL_OC_MEN_LINE51_WHITE",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "HIGH",
                ],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    alerts: list[dict[str, object]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv(watch_mod.AUTO_PROBABLE_FILL_ENV, "1")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", tmp_path / "ready_watch_state.json")
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "product_type": "CL",
            }
        },
    )

    readiness_calls = {"count": 0}

    def _fake_readiness(**_kwargs):
        readiness_calls["count"] += 1
        if readiness_calls["count"] == 1:
            return {
                "ready": False,
                "run_control_ready_ok": False,
                "blank_size_count": 1,
                "invalid_size_count": 0,
            }
        return {
            "ready": True,
            "run_control_ready_ok": True,
            "ready_set_at": "2026-04-15T18:57:05+05:00",
            "blank_size_count": 0,
            "invalid_size_count": 0,
        }

    monkeypatch.setattr(watch_mod, "build_readiness_report", _fake_readiness)
    monkeypatch.setattr(
        watch_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
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
    assert calls == [[
        str(watch_mod.sys.executable),
        str(watch_mod.SCRIPT_PATH),
        "--expected-target-date",
        "2026-04-15",
        "--expected-ready-set-at",
        "2026-04-15T18:57:05+05:00",
    ]]
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "WARN"
    assert alerts[0]["dedup_key"] == "google-ops-board-auto-prepare:2026-04-15"
    assert alerts[0]["lines"] == [
        "Target date: 2026-04-15",
        "Fire time: 18:57 Asia/Almaty",
        "Auto-filled order IDs: 1001=2XL",
        "READY auto-stamped: yes",
    ]


def test_early_closeout_watch_does_not_auto_fill_probable_sizes_without_explicit_opt_in(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "2XL",
                    "Комплект ACMEWEAR OF_LINE51_BLK_2XL_58",
                    "CL_OC_MEN_LINE51_WHITE",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "HIGH",
                ],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.delenv(watch_mod.AUTO_PROBABLE_FILL_ENV, raising=False)
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", tmp_path / "ready_watch_state.json")
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "product_type": "CL",
            }
        },
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": False,
            "blank_size_count": 1,
            "blank_size_rows": [{"OrderID": "1001", "_db_row_id": "1"}],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = watch_mod.main()

    assert rc == 0
    assert calls == []
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_writes_auto_fill_audit_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "2XL",
                    "Комплект ACMEWEAR",
                    "CL_OC_MEN_LINE52_BLACK",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "HIGH",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    write_time = datetime(2026, 4, 15, 18, 57, 9, tzinfo=ZoneInfo("Asia/Almaty"))
    monkeypatch.setattr(watch_mod, "now_almaty", lambda: write_time)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE52_BLACK",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 1
    audit_files = list((audit_root / "2026-04-15").glob("auto_probable_closeout_*.json"))
    assert len(audit_files) == 1
    payload = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert payload["target_date"] == "2026-04-15"
    assert payload["applied_rows"][0]["OrderID"] == "1001"
    assert payload["applied_rows"][0]["MY_SIZE"] == "2XL"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == "2XL"
    assert client.get_tab_values("Run_Control")[1][1] == "READY"
    assert client.get_tab_values("Run_Control")[1][2] == watch_mod.AUTO_READY_SET_BY
    assert client.get_tab_values("Run_Control")[1][3] == write_time.isoformat()
    assert "AUTO_1857 probable backfill: 1 row(s)" in client.get_tab_values("Run_Control")[1][4]


def test_auto_probable_fill_aborts_before_salesraw_write_when_employee_sets_size_and_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    run_headers = contract.tabs["Run_Control"].headers
    sales_headers = contract.tabs["SalesRaw_Today"].headers

    class _EmployeeRaceClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__(
                {
                    "Run_Control": [
                        run_headers,
                        ["2026-04-15", "HOLD", "", "", "", "", "", ""],
                    ],
                    "SalesRaw_Today": [
                        sales_headers,
                        [
                            "TODAY", "2026-04-15", "Universal", "", "", "1",
                            "Line51", "1001", "", "2XL", "Offer", "CL_TEST", "1",
                            "line", "DECLARED_ORDER", "HIGH",
                        ],
                    ],
                }
            )
            self.run_control_reads = 0

        def get_tab_values(self, tab_name: str):
            if tab_name == "Run_Control":
                self.run_control_reads += 1
                if self.run_control_reads == 2:
                    self._tab_values["SalesRaw_Today"][1][sales_headers.index("MY_SIZE")] = "L"
                    row = self._tab_values["Run_Control"][1]
                    row[run_headers.index("ready_for_closeout")] = "READY"
                    row[run_headers.index("ready_set_by")] = "EMPLOYEE"
                    row[run_headers.index("ready_set_at")] = "2026-04-15T18:57:06+05:00"
            return super().get_tab_values(tab_name)

    client = _EmployeeRaceClient()
    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", tmp_path / "audit")
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {"sku_key": "CL_TEST", "product_type": "CL"}
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["employee_ready_freeze"] is True
    assert report["salesraw_updates_applied"] == 0
    assert client.get_tab_values("SalesRaw_Today")[1][sales_headers.index("MY_SIZE")] == "L"
    run_control = client.get_tab_values("Run_Control")[1]
    assert run_control[run_headers.index("ready_set_by")] == "EMPLOYEE"
    assert run_control[run_headers.index("ready_set_at")] == "2026-04-15T18:57:06+05:00"
    assert client.update_calls == []


def test_auto_probable_fill_aborts_before_identity_write_when_employee_sets_size_and_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    run_headers = contract.tabs["Run_Control"].headers
    sales_headers = contract.tabs["SalesRaw_Today"].headers

    class _EmployeeRaceClient(_FakeClient):
        def __init__(self) -> None:
            super().__init__(
                {
                    "Run_Control": [
                        run_headers,
                        ["2026-04-15", "HOLD", "", "", "", "", "", ""],
                    ],
                    "SalesRaw_Today": [
                        sales_headers,
                        [
                            "TODAY", "2026-04-15", "Universal", "", "", "1",
                            "Line51", "1001", "", "2XL", "Offer", "CL_TEST", "1",
                            "line", "DECLARED_ORDER", "HIGH",
                        ],
                    ],
                }
            )
            self.run_control_reads = 0

        def get_tab_values(self, tab_name: str):
            if tab_name == "Run_Control":
                self.run_control_reads += 1
                if self.run_control_reads == 3:
                    self._tab_values["SalesRaw_Today"][1][sales_headers.index("MY_SIZE")] = "L"
                    row = self._tab_values["Run_Control"][1]
                    row[run_headers.index("ready_for_closeout")] = "READY"
                    row[run_headers.index("ready_set_by")] = "EMPLOYEE"
                    row[run_headers.index("ready_set_at")] = "2026-04-15T18:57:07+05:00"
            return super().get_tab_values(tab_name)

    client = _EmployeeRaceClient()
    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", tmp_path / "audit")
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 8, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {"sku_key": "CL_TEST", "product_type": "CL"}
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["employee_ready_freeze"] is True
    assert report["salesraw_updates_applied"] == 1
    assert client.get_tab_values("SalesRaw_Today")[1][sales_headers.index("MY_SIZE")] == "L"
    run_control = client.get_tab_values("Run_Control")[1]
    assert run_control[run_headers.index("ready_set_by")] == "EMPLOYEE"
    assert run_control[run_headers.index("ready_set_at")] == "2026-04-15T18:57:07+05:00"
    assert all(
        not any(str(cell.get("range", "")).startswith("Run_Control!") for cell in call.get("cells", []))
        for call in client.update_calls
    )


def test_early_closeout_watch_requires_visible_probable_size_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "",
                    "Комплект ACMEWEAR OF_LINE51_BLK_2XL_58",
                    "CL_OC_MEN_LINE51_WHITE",
                    "1",
                    "line-1",
                    "",
                    "",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE51_WHITE",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 0
    assert report["run_control_updated"] is False
    assert report["blank_rows_remaining"][0]["OrderID"] == "1001"
    assert report["blank_rows_remaining"][0]["reason"] == "MISSING_PROBABLE_SIZE"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_rejects_invalid_probable_size_after_1857(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                [
                    "TODAY",
                    "2026-04-15",
                    "Universal",
                    "",
                    "",
                    "1",
                    "Принт_5в1_черный",
                    "1001",
                    "",
                    "NOT_A_SIZE",
                    "Комплект ACMEWEAR",
                    "CL_OC_MEN_LINE52_BLACK",
                    "1",
                    "line-1",
                    "DECLARED_ORDER",
                    "LOW",
                ],
            ],
        }
    )
    audit_root = tmp_path / "audit"

    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", audit_root, raising=False)
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_OC_MEN_LINE52_BLACK",
                "product_type": "CL",
            }
        },
    )

    report = watch_mod._maybe_auto_prepare_closeout(
        client=client,
        contract=contract,
        db_path=tmp_path / "app.db",
        target_date=date(2026, 4, 15),
        lookback_days=5,
        now=datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert report["salesraw_updates_applied"] == 0
    assert report["run_control_updated"] is False
    assert report["blank_rows_remaining"][0]["OrderID"] == "1001"
    assert report["blank_rows_remaining"][0]["reason"] == "INVALID_PROBABLE_SIZE"
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    assert client.get_tab_values("Run_Control")[1][1] == "HOLD"


def test_early_closeout_watch_blank_probable_size_after_1857_blocks_closeout(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Line51", "1001", "", "", "Offer", "CL_TEST", "1", "line", "", ""],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    alerts: list[dict[str, object]] = []

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv(watch_mod.AUTO_PROBABLE_FILL_ENV, "1")
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 18, 57, 5, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", tmp_path / "ready_watch_state.json")
    monkeypatch.setattr(watch_mod, "AUTO_PROBABLE_AUDIT_ROOT", tmp_path / "audit")
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )
    monkeypatch.setattr(
        watch_mod,
        "load_db_rows_for_writeback",
        lambda *_args, **_kwargs: {"1": {"assigned_size": "", "store_code": "UNIVERSAL", "sku_key": "CL_TEST", "product_type": "CL"}},
    )
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": False,
            "blank_size_count": 1,
            "blank_size_rows": [{"OrderID": "1001", "_db_row_id": "1"}],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = watch_mod.main()

    assert rc != 0
    assert calls == []
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "CRITICAL"
    assert alerts[0]["dedup_key"] == "2026-04-15"
    assert alerts[0]["dedup_window"].total_seconds() == 1800
    assert "1001=MISSING_PROBABLE_SIZE" in "\n".join(alerts[0]["lines"])
    assert client.get_tab_values("SalesRaw_Today")[1][8] == ""
    run_control = client.get_tab_values("Run_Control")[1]
    assert run_control[1] == "HOLD"
    assert run_control[7] == "BLOCKED_MISSING_OR_INVALID_PROBABLE_SIZE"
    assert "1001=MISSING_PROBABLE_SIZE" in run_control[4]


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
    _stub_closeout_health_green(monkeypatch, tmp_path)
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


def test_early_closeout_watch_marks_ready_with_missing_sizes_as_recoverable_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
                ["TODAY", "2026-04-15", "AcmeWear", "", "", "1", "Line51", "1002", "", "2XL", "Offer", "SKU-2", "2", "line", "DEFAULT", "LOW"],
            ],
        }
    )
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []
    state_path = tmp_path / "ready_watch_state.json"
    state_path.write_text('{"target_date":"2026-04-15","armed_at":"2026-04-15T17:10:00+05:00"}', encoding="utf-8")

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": False,
            "run_control_ready_ok": True,
            "blank_size_count": 2,
            "blank_size_rows": [
                {"OrderID": "1001", "STORE_NAME": "Universal", "_db_row_id": "1"},
                {"OrderID": "1002", "STORE_NAME": "AcmeWear", "_db_row_id": "2"},
            ],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )
    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command))

    rc = watch_mod.main()

    run_control = client.get_tab_values("Run_Control")[1]
    assert rc == 0
    assert calls == []
    assert run_control[1] == "READY"
    assert run_control[7] == "BLOCKED_MISSING_SIZES"
    assert "1001" in run_control[4]
    assert "1002" in run_control[4]
    assert not state_path.exists()


def test_early_closeout_watch_ready_block_marker_is_idempotent(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    note = "BLOCKED_MISSING_SIZES: fill MY_SIZE for orders 1001, 1002"
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", note, "2026-04-15T17:11:00+05:00", "", "BLOCKED_MISSING_SIZES"],
            ]
        }
    )

    watch_mod._mark_recoverable_ready_block(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 15),
        readiness={
            "ready": False,
            "run_control_ready_ok": True,
            "blank_size_count": 2,
            "blank_size_rows": [
                {"OrderID": "1001", "STORE_NAME": "Universal", "_db_row_id": "1"},
                {"OrderID": "1002", "STORE_NAME": "AcmeWear", "_db_row_id": "2"},
            ],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
        now=datetime(2026, 4, 15, 17, 11, 15, tzinfo=ZoneInfo("Asia/Almaty")),
    )

    assert client.update_calls == []


def test_early_closeout_watch_recovers_after_missing_sizes_are_fixed_while_ready_remains_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                    ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "BLOCKED_MISSING_SIZES: 1001", "", "", "BLOCKED_MISSING_SIZES"],
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
                    "ready_set_at": "2026-04-15T17:10:00+05:00",
                    "armed_at": datetime(2026, 4, 15, 17, 10, tzinfo=ZoneInfo("Asia/Almaty")).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    _stub_closeout_health_green(monkeypatch, tmp_path)
    monkeypatch.setattr(watch_mod, "_in_watch_window", lambda: True)
    monkeypatch.setattr(watch_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        watch_mod,
        "now_almaty",
        lambda: datetime(2026, 4, 15, 17, 11, 1, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    monkeypatch.setattr(watch_mod, "READY_DEBOUNCE_STATE_PATH", state_path)
    monkeypatch.setattr(watch_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(
        watch_mod,
        "build_readiness_report",
        lambda **_kwargs: {
            "ready": True,
            "run_control_ready_ok": True,
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "blank_size_count": 0,
            "blank_size_rows": [],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
        },
    )

    class _Result:
        returncode = 0

    monkeypatch.setattr(watch_mod.subprocess, "run", lambda command, cwd, env: calls.append(command) or _Result())

    rc = watch_mod.main()

    assert rc == 0
    assert calls == [[
        str(watch_mod.sys.executable),
        str(watch_mod.SCRIPT_PATH),
        "--expected-target-date",
        "2026-04-15",
        "--expected-ready-set-at",
        "2026-04-15T17:10:00+05:00",
    ]]
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

    rc = closeout_scheduler_mod.main([])

    assert rc == 0
    assert calls == []


def test_closeout_scheduler_runs_when_run_control_ok_but_delivery_incomplete(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    def _incomplete_checkpoint(**_kwargs):
        closeout_scheduler_mod._LAST_CLOSEOUT_STATE = {
            "status": "OK",
            "delivery_state": {
                "status": "TELEGRAM_LEDGER_INCOMPLETE",
                "manifest_path": str(tmp_path / "Today" / "MERGED" / "SEND" / "batch" / "send_batch_manifest.json"),
            },
            "request_identity": {
                "target_date": "2026-04-15",
                "ready_set_at": "2026-04-15T17:10:00+05:00",
            },
        }
        return False

    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        _incomplete_checkpoint,
    )
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_current_ready_identity",
        lambda **_kwargs: {
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "ready_for_closeout": "READY",
        },
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command) or _Result(),
    )

    rc = closeout_scheduler_mod.main([])

    assert rc == 0
    assert calls == [
        [
            closeout_scheduler_mod.sys.executable,
            str(closeout_scheduler_mod.DB_CHECK_PATH),
            "--db-path",
            str(closeout_scheduler_mod.PROJECT_ROOT / "db" / "app.db"),
        ],
        [
            closeout_scheduler_mod.sys.executable,
            str(closeout_scheduler_mod.SCRIPT_PATH),
            "--apply",
            "--resume",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
            "--spreadsheet-id",
            "sheet-id",
            "--service-account-json",
            str(creds),
        ],
    ]


def test_closeout_scheduler_active_halt_barrier_blocks_launch(monkeypatch, tmp_path: Path) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(closeout_scheduler_mod, "_closeout_already_completed", lambda **_kwargs: False)
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_current_ready_identity",
        lambda **_kwargs: {
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "ready_for_closeout": "READY",
        },
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "evaluate_closeout_halt_barrier",
        lambda **_kwargs: {
            "blocked": True,
            "reason": "HALT_BARRIER_ACTIVE",
            "request_halted": False,
            "barrier": {"state": "HOLD_CONFIRMED"},
        },
    )
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main(
        [
            "--expected-target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
        ]
    )

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
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_closeout_already_completed",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_current_ready_identity",
        lambda **_kwargs: {
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:10:00+05:00",
            "ready_for_closeout": "READY",
        },
    )
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _BusyLock)
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main(
        [
            "--expected-target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
        ]
    )

    assert rc == 0
    assert calls == []


def test_closeout_scheduler_stops_when_ready_identity_changes_before_launch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    creds = _write_creds(tmp_path)
    calls: list[list[str]] = []

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setattr(closeout_scheduler_mod, "today_almaty", lambda: date(2026, 4, 15))
    monkeypatch.setattr(closeout_scheduler_mod, "_closeout_already_completed", lambda **_kwargs: False)
    monkeypatch.setattr(closeout_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        closeout_scheduler_mod,
        "_current_ready_identity",
        lambda **_kwargs: {
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:11:00+05:00",
            "ready_for_closeout": "READY",
        },
    )
    monkeypatch.setattr(
        closeout_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append(command),
    )

    rc = closeout_scheduler_mod.main(
        [
            "--expected-target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
        ]
    )

    assert rc == 78
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


def test_size_writeback_scheduler_incomplete_closeout_runs_preview_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "sync_google_ops_board_sizes_to_db.py"
    db_check_path = tmp_path / "check_local_app_db.py"
    creds = _write_creds(tmp_path)
    script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    db_check_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, str]]] = []

    class _FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class _Result:
        returncode = 0

    monkeypatch.setenv("AB_GOOGLE_SERVICE_ACCOUNT_JSON", str(creds))
    monkeypatch.setenv("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_DB_WRITE", "1")
    monkeypatch.setattr(writeback_scheduler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(writeback_scheduler_mod, "SCRIPT_PATH", script_path)
    monkeypatch.setattr(writeback_scheduler_mod, "DB_CHECK_PATH", db_check_path)
    monkeypatch.setattr(writeback_scheduler_mod, "_closeout_already_completed", lambda **_kwargs: False)
    monkeypatch.setattr(writeback_scheduler_mod, "GoogleOpsBoardAutomationLock", _FakeLock)
    monkeypatch.setattr(
        writeback_scheduler_mod.subprocess,
        "run",
        lambda command, cwd, env: calls.append((command, dict(env))) or _Result(),
    )

    rc = writeback_scheduler_mod.main()

    assert rc == 0
    assert len(calls) == 2
    preview_command, preview_env = calls[1]
    assert preview_command[:2] == [writeback_scheduler_mod.sys.executable, str(script_path)]
    assert "--apply" not in preview_command
    assert "--allowed-order-scope-file" not in preview_command
    assert "ENABLE_GOOGLE_OPS_BOARD_DB_WRITE" not in preview_env
