from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from scripts.run_google_ops_board_publish_scheduler import (
    build_source_refresh_commands,
    inspect_activeorders_source,
    is_source_refresh_slot,
    source_snapshot_path,
    write_source_snapshot,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _write_activeorders_workbook(path: Path, planned_dates: list[str]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["№ заказа", "Плановая дата передачи курьеру", "Название товара в Kaspi Магазине"])
    for idx, planned_date in enumerate(planned_dates, start=1):
        worksheet.append([f"OID-{idx}", planned_date, f"Offer {idx}"])
    workbook.save(path)


def test_is_source_refresh_slot_true_only_for_0700_almaty() -> None:
    assert is_source_refresh_slot(datetime(2026, 4, 17, 7, 0, tzinfo=ALMATY_TZ)) is True
    assert is_source_refresh_slot(datetime(2026, 4, 17, 7, 1, tzinfo=ALMATY_TZ)) is False
    assert is_source_refresh_slot(datetime(2026, 4, 17, 14, 1, tzinfo=ALMATY_TZ)) is False


def test_inspect_activeorders_source_marks_fresh_with_today_rows_and_today_mtime(tmp_path: Path) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    _write_activeorders_workbook(workbook_path, ["17.04.2026", "17.04.2026"])
    fresh_ts = datetime(2026, 4, 17, 7, 5, tzinfo=ALMATY_TZ).timestamp()
    Path(workbook_path).touch()
    import os

    os.utime(workbook_path, (fresh_ts, fresh_ts))

    report = inspect_activeorders_source(workbook_path, target_date=date(2026, 4, 17))

    assert report["exists"] is True
    assert report["mtime_date"] == "2026-04-17"
    assert report["row_count"] == 2
    assert report["target_row_count"] == 2
    assert report["contains_target_date"] is True
    assert report["fresh"] is True


def test_inspect_activeorders_source_is_not_fresh_when_target_date_missing(tmp_path: Path) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    _write_activeorders_workbook(workbook_path, ["16.04.2026", "16.04.2026"])
    fresh_ts = datetime(2026, 4, 17, 7, 5, tzinfo=ALMATY_TZ).timestamp()
    import os

    os.utime(workbook_path, (fresh_ts, fresh_ts))

    report = inspect_activeorders_source(workbook_path, target_date=date(2026, 4, 17))

    assert report["mtime_date"] == "2026-04-17"
    assert report["row_count"] == 2
    assert report["target_row_count"] == 0
    assert report["contains_target_date"] is False
    assert report["fresh"] is False


def test_build_source_refresh_commands_covers_export_sync_enrich(tmp_path: Path) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"

    commands = build_source_refresh_commands(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        python_executable="/usr/bin/python3",
        lookback_days=5,
    )

    assert commands[0] == [
        "/usr/bin/python3",
        "~/Docs/Autonomous_business/scripts/export_api_orders.py",
        "--all-stores",
        "--state",
        "KASPI_DELIVERY",
        "--days",
        "5",
        "--include-overdue",
        "--refetch-missing-costs",
        "--no-archive",
        "--output",
        str(workbook_path),
        "--verbose",
    ]
    assert commands[1] == [
        "/usr/bin/python3",
        "~/Docs/Autonomous_business/scripts/validate_activeorders_columns.py",
        str(workbook_path),
    ]
    assert commands[2] == [
        "/usr/bin/python3",
        "~/Docs/Autonomous_business/scripts/sync_kaspi_orders.py",
        "--all",
        "--since",
        "2026-04-12",
        "-v",
    ]
    assert commands[3] == [
        "/usr/bin/python3",
        "~/Docs/Autonomous_business/scripts/enrich_kaspi_orders_from_activeorders.py",
        "--apply",
        "--file",
        str(workbook_path),
        "--target-date",
        "2026-04-17",
    ]


def test_write_source_snapshot_records_fingerprint_and_freshness(tmp_path: Path) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    snapshot_root = tmp_path / "snapshots"
    _write_activeorders_workbook(workbook_path, ["17.04.2026"])

    snapshot = write_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        refresh_slot=True,
    )

    assert Path(snapshot["path"]) == source_snapshot_path(date(2026, 4, 17), snapshot_root=snapshot_root)
    assert snapshot["target_date"] == "2026-04-17"
    assert snapshot["refresh_slot"] is True
    assert snapshot["source_state"]["fresh"] is True
    assert snapshot["source_fingerprint"]["sha256"]
    assert Path(snapshot["path"]).exists()


def test_publish_scheduler_runs_publish_inside_shared_automation_lock(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    service_account_json = tmp_path / "service-account.json"
    service_account_json.write_text("{}", encoding="utf-8")
    events: list[str] = []
    subprocess_calls: list[dict[str, object]] = []

    class FakeLock:
        def __enter__(self):
            events.append("lock_enter")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            events.append("lock_exit")
            return False

    class FakeResult:
        returncode = 0

    def fake_run(command, *, cwd=None, env=None):
        subprocess_calls.append(
            {
                "command": list(command),
                "events": list(events),
                "held_env": (env or {}).get("AB_GOOGLE_OPS_BOARD_LOCK_HELD"),
                "cwd": cwd,
            }
        )
        return FakeResult()

    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_LOCK_HELD", raising=False)
    monkeypatch.setattr(scheduler, "GoogleOpsBoardAutomationLock", FakeLock, raising=False)
    monkeypatch.setattr(scheduler, "load_ops_board_contract", lambda path: object())
    monkeypatch.setattr(scheduler, "resolve_service_account_json", lambda contract: service_account_json)
    monkeypatch.setattr(scheduler, "resolve_spreadsheet_id", lambda override, contract: "sheet-id")
    monkeypatch.setattr(scheduler, "today_almaty", lambda: date(2026, 4, 17))
    monkeypatch.setattr(scheduler, "is_source_refresh_slot", lambda: False)
    monkeypatch.setattr(
        scheduler,
        "inspect_activeorders_source",
        lambda workbook_path, *, target_date: {"fresh": True},
    )
    monkeypatch.setattr(scheduler, "ensure_prewindow_health", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    assert scheduler.main() == 0

    publish_call = next(
        call for call in subprocess_calls if call["command"][1].endswith("sync_google_ops_board.py")
    )
    assert publish_call["events"] == ["lock_enter"]
    assert publish_call["held_env"] == "1"
    assert events == ["lock_enter", "lock_exit"]


def test_publish_scheduler_skips_cleanly_when_shared_lock_is_busy(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    service_account_json = tmp_path / "service-account.json"
    service_account_json.write_text("{}", encoding="utf-8")
    subprocess_calls: list[list[str]] = []

    class BusyLock:
        def __enter__(self):
            raise RuntimeError("Another Google Ops Board automation instance is already running.")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def fake_run(command, *, cwd=None, env=None):
        subprocess_calls.append(list(command))
        raise AssertionError("publish scheduler must not run subprocesses while the shared lock is busy")

    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_LOCK_HELD", raising=False)
    monkeypatch.setattr(scheduler, "GoogleOpsBoardAutomationLock", BusyLock)
    monkeypatch.setattr(scheduler, "load_ops_board_contract", lambda path: object())
    monkeypatch.setattr(scheduler, "resolve_service_account_json", lambda contract: service_account_json)
    monkeypatch.setattr(scheduler, "resolve_spreadsheet_id", lambda override, contract: "sheet-id")
    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)

    assert scheduler.main() == 0

    captured = capsys.readouterr()
    assert "Another Google Ops Board automation instance is already running." in captured.err
    assert subprocess_calls == []
