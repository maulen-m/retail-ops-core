from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
import pytest

from scripts.run_google_ops_board_publish_scheduler import (
    PROJECT_ROOT,
    build_source_refresh_commands,
    inspect_activeorders_source,
    is_source_refresh_slot,
    load_committed_source_snapshot,
    run_source_refresh,
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


def test_inspect_activeorders_source_is_fresh_when_current_refresh_has_only_carryover(
    tmp_path: Path,
) -> None:
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
    assert report["fresh"] is True


def test_inspect_activeorders_source_is_fresh_for_current_zero_order_refresh(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    _write_activeorders_workbook(workbook_path, [])
    fresh_ts = datetime(2026, 4, 17, 7, 5, tzinfo=ALMATY_TZ).timestamp()
    import os

    os.utime(workbook_path, (fresh_ts, fresh_ts))

    report = inspect_activeorders_source(workbook_path, target_date=date(2026, 4, 17))

    assert report["row_count"] == 0
    assert report["target_row_count"] == 0
    assert report["fresh"] is True


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
        str(PROJECT_ROOT / "scripts" / "export_api_orders.py"),
        "--all-stores",
        "--require-complete",
        "--state",
        "KASPI_DELIVERY",
        "--days",
        "5",
        "--include-overdue",
        "--no-archive",
        "--output",
        str(workbook_path),
        "--verbose",
    ]
    assert commands[1] == [
        "/usr/bin/python3",
        str(PROJECT_ROOT / "scripts" / "validate_activeorders_columns.py"),
        str(workbook_path),
    ]
    assert commands[2] == [
        "/usr/bin/python3",
        str(PROJECT_ROOT / "scripts" / "sync_kaspi_orders.py"),
        "--all",
        "--since",
        "2026-04-12",
        "-v",
    ]
    assert commands[3] == [
        "/usr/bin/python3",
        str(PROJECT_ROOT / "scripts" / "enrich_kaspi_orders_from_activeorders.py"),
        "--apply",
        "--file",
        str(workbook_path),
        "--target-date",
        "2026-04-17",
    ]


def test_build_source_refresh_commands_entry_sync_is_explicitly_gated(tmp_path: Path) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"

    commands = build_source_refresh_commands(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        python_executable="/usr/bin/python3",
        lookback_days=5,
        enable_entry_sync=True,
    )

    assert commands[0][-2:] == [
        "--entry-sidecar-output",
        str(PROJECT_ROOT / "exports" / "google_ops_board" / "source_snapshots" / "2026-04-17" / "order_entries_sidecar.json"),
    ]
    assert commands[2] == [
        "/usr/bin/python3",
        str(PROJECT_ROOT / "scripts" / "sync_kaspi_orders.py"),
        "--all",
        "--since",
        "2026-04-12",
        "-v",
    ]


def test_run_source_refresh_passes_enrichment_write_gate_only_when_entry_sync_enabled(
    monkeypatch,
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    calls: list[tuple[list[str], dict[str, str]]] = []

    class FakeResult:
        returncode = 0

    def fake_run(command, *, cwd=None, env=None):
        calls.append((list(command), dict(env or {})))
        return FakeResult()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    monkeypatch.setattr(
        scheduler,
        "write_source_snapshot",
        lambda **kwargs: {"path": "/tmp/source_snapshot.json"},
    )
    monkeypatch.setattr(
        scheduler,
        "create_current_order_refresh_backup",
        lambda **kwargs: Path("/tmp/test-current-order-refresh-backup.db"),
    )
    sidecar_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        scheduler,
        "run_pinned_order_entry_sidecar_apply",
        lambda **kwargs: sidecar_calls.append(kwargs) or 0,
    )

    assert run_source_refresh(
        target_date=date(2026, 4, 17),
        env={"ENABLE_KASPI_CURRENT_ORDER_ENTRY_SYNC": "1"},
    ) == 0

    sync_command, sync_env = next(
        item for item in calls if item[0][1].endswith("sync_kaspi_orders.py")
    )
    assert "--enrich" not in sync_command
    assert sync_env["ENABLE_KASPI_ENRICHMENT"] == "1"
    assert len(sidecar_calls) == 1
    assert sidecar_calls[0]["target_date"] == date(2026, 4, 17)


def test_run_source_refresh_passes_status_event_write_gate_only_when_capture_enabled(
    monkeypatch,
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    calls: list[tuple[list[str], dict[str, str]]] = []

    class FakeResult:
        returncode = 0

    def fake_run(command, *, cwd=None, env=None):
        calls.append((list(command), dict(env or {})))
        return FakeResult()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    monkeypatch.setattr(
        scheduler,
        "write_source_snapshot",
        lambda **kwargs: {"path": "/tmp/source_snapshot.json"},
    )
    monkeypatch.setattr(
        scheduler,
        "create_current_order_refresh_backup",
        lambda **kwargs: Path("/tmp/test-current-order-refresh-backup.db"),
    )

    assert run_source_refresh(
        target_date=date(2026, 4, 17),
        env={"ENABLE_KASPI_CURRENT_ORDER_STATUS_EVENT_SYNC": "1"},
    ) == 0
    _, sync_env = next(
        item for item in calls if item[0][1].endswith("sync_kaspi_orders.py")
    )
    assert sync_env["ENABLE_ORDER_STATUS_EVENT_WRITE"] == "1"

    calls.clear()
    assert run_source_refresh(
        target_date=date(2026, 4, 17),
        env={"ENABLE_ORDER_STATUS_EVENT_WRITE": "1"},
    ) == 0
    _, default_sync_env = next(
        item for item in calls if item[0][1].endswith("sync_kaspi_orders.py")
    )
    assert "ENABLE_ORDER_STATUS_EVENT_WRITE" not in default_sync_env


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


def test_write_source_snapshot_pins_entry_sidecar_receipt_and_prewrite_backup(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    snapshot_root = tmp_path / "snapshots"
    backup_path = tmp_path / "app_before.db"
    _write_activeorders_workbook(workbook_path, ["17.04.2026"])
    backup_path.write_bytes(b"verified-test-backup")
    sidecar_path = snapshot_root / "2026-04-17" / "order_entries_sidecar.json"
    receipt_path = snapshot_root / "2026-04-17" / "order_entries_sidecar_apply_report.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text('{"schema_version":"kaspi_order_entry_sidecar_v1"}\n', encoding="utf-8")
    receipt_path.write_text(
        """{
          "payload_sha256": "abc",
          "store_count": 3,
          "order_count": 2,
          "entry_count": 2,
          "preexisting_entry_count": 0,
          "inserted_entry_count": 2,
          "readback_complete": true,
          "integrity_after": "ok",
          "non_target_hash_after": "def",
          "backup_path": "/tmp/app_before.db"
        }\n""",
        encoding="utf-8",
    )

    snapshot = write_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        refresh_slot=True,
        include_entry_sidecar=True,
        prewrite_backup_path=backup_path,
    )

    assert snapshot["order_entry_sidecar_fingerprint"]["sha256"]
    assert snapshot["order_entry_sidecar_receipt_fingerprint"]["sha256"]
    assert snapshot["order_entry_sidecar_receipt"]["readback_complete"] is True
    assert snapshot["prewrite_db_backup_fingerprint"]["sha256"]


def test_load_committed_source_snapshot_preserves_strong_refresh_evidence(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    snapshot_root = tmp_path / "snapshots"
    backup_path = tmp_path / "app_before.db"
    _write_activeorders_workbook(workbook_path, ["17.04.2026"])
    backup_path.write_bytes(b"verified-test-backup")
    dated_root = snapshot_root / "2026-04-17"
    dated_root.mkdir(parents=True)
    (dated_root / "order_entries_sidecar.json").write_text(
        '{"schema_version":"kaspi_order_entry_sidecar_v1"}\n', encoding="utf-8"
    )
    (dated_root / "order_entries_sidecar_apply_report.json").write_text(
        '{"readback_complete":true,"backup_path":"/tmp/app_before.db"}\n',
        encoding="utf-8",
    )
    strong = write_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        refresh_slot=True,
        include_entry_sidecar=True,
        prewrite_backup_path=backup_path,
    )

    loaded = load_committed_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
    )

    assert loaded == strong
    assert loaded["order_entry_sidecar_fingerprint"]["sha256"]
    assert loaded["order_entry_sidecar_receipt_fingerprint"]["sha256"]
    assert loaded["prewrite_db_backup_fingerprint"]["sha256"]


def test_load_committed_source_snapshot_rejects_weak_or_tampered_marker(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    snapshot_root = tmp_path / "snapshots"
    backup_path = tmp_path / "app_before.db"
    _write_activeorders_workbook(workbook_path, ["17.04.2026"])
    backup_path.write_bytes(b"verified-test-backup")
    marker = write_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        refresh_slot=False,
        prewrite_backup_path=backup_path,
    )
    assert marker["refresh_slot"] is False
    with pytest.raises(RuntimeError, match="strong refresh commit marker"):
        load_committed_source_snapshot(
            target_date=date(2026, 4, 17),
            workbook_path=workbook_path,
            snapshot_root=snapshot_root,
        )

    write_source_snapshot(
        target_date=date(2026, 4, 17),
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        refresh_slot=True,
        prewrite_backup_path=backup_path,
    )
    backup_path.write_bytes(b"tampered-after-commit")
    with pytest.raises(RuntimeError, match="backup fingerprint is invalid"):
        load_committed_source_snapshot(
            target_date=date(2026, 4, 17),
            workbook_path=workbook_path,
            snapshot_root=snapshot_root,
        )


def test_refresh_publish_cycle_does_not_overwrite_committed_source_snapshot(
    monkeypatch,
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    events: list[str] = []

    class FakeResult:
        returncode = 0

    monkeypatch.setattr(scheduler, "today_almaty", lambda: date(2026, 4, 17))
    monkeypatch.setattr(scheduler, "ensure_kaspi_api_call_ledger_env", lambda *a, **k: None)
    monkeypatch.setattr(scheduler.subprocess, "run", lambda *a, **k: FakeResult())
    monkeypatch.setattr(
        scheduler,
        "run_source_refresh",
        lambda **kwargs: events.append("refresh") or 0,
    )
    monkeypatch.setattr(
        scheduler,
        "inspect_activeorders_source",
        lambda *a, **k: {"fresh": True},
    )
    monkeypatch.setattr(
        scheduler,
        "load_committed_source_snapshot",
        lambda **kwargs: events.append("load_strong")
        or {"path": "/tmp/strong-source-snapshot.json"},
    )
    monkeypatch.setattr(
        scheduler,
        "write_source_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("refresh publish must not replace strong source snapshot")
        ),
    )
    monkeypatch.setattr(scheduler, "ensure_prewindow_health", lambda **kwargs: {"ok": True})

    rc = scheduler.run_publish_cycle(
        env={},
        service_account_json="/tmp/service-account.json",
        spreadsheet_id="sheet-id",
        force_source_refresh=True,
    )

    assert rc == 0
    assert events == ["refresh", "load_strong"]


def test_quiet_publish_cycle_reuses_committed_source_snapshot_without_overwrite(
    monkeypatch,
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    events: list[str] = []

    class FakeResult:
        returncode = 0

    monkeypatch.setattr(scheduler, "today_almaty", lambda: date(2026, 4, 17))
    monkeypatch.setattr(scheduler, "ensure_kaspi_api_call_ledger_env", lambda *a, **k: None)
    monkeypatch.setattr(scheduler.subprocess, "run", lambda *a, **k: FakeResult())
    monkeypatch.setattr(
        scheduler,
        "run_source_refresh",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("quiet publish must not refresh source")
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "inspect_activeorders_source",
        lambda *a, **k: {"fresh": True},
    )
    monkeypatch.setattr(
        scheduler,
        "load_committed_source_snapshot",
        lambda **kwargs: events.append("load_strong")
        or {"path": "/tmp/strong-source-snapshot.json"},
    )
    monkeypatch.setattr(
        scheduler,
        "write_source_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("quiet publish must not replace strong source snapshot")
        ),
    )
    monkeypatch.setattr(scheduler, "ensure_prewindow_health", lambda **kwargs: {"ok": True})

    rc = scheduler.run_publish_cycle(
        env={},
        service_account_json="/tmp/service-account.json",
        spreadsheet_id="sheet-id",
        force_source_refresh=False,
    )

    assert rc == 0
    assert events == ["load_strong"]


def test_inspect_activeorders_source_rejects_yesterday_header_only_workbook(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "ActiveOrders.xlsx"
    _write_activeorders_workbook(workbook_path, [])
    stale_ts = datetime(2026, 4, 16, 23, 59, tzinfo=ALMATY_TZ).timestamp()
    import os

    os.utime(workbook_path, (stale_ts, stale_ts))

    report = inspect_activeorders_source(workbook_path, target_date=date(2026, 4, 17))

    assert report["row_count"] == 0
    assert report["mtime_date"] == "2026-04-16"
    assert report["fresh"] is False


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
    monkeypatch.setattr(
        scheduler,
        "load_committed_source_snapshot",
        lambda **kwargs: {"path": "/tmp/source_snapshot.json"},
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


def test_force_source_refresh_runs_refresh_before_publish(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    service_account_json = tmp_path / "service-account.json"
    service_account_json.write_text("{}", encoding="utf-8")
    events: list[str] = []

    class FakeLock:
        def __enter__(self):
            events.append("lock_enter")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            events.append("lock_exit")
            return False

    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_LOCK_HELD", raising=False)
    monkeypatch.setattr(scheduler, "GoogleOpsBoardAutomationLock", FakeLock)
    monkeypatch.setattr(scheduler, "load_ops_board_contract", lambda path: object())
    monkeypatch.setattr(scheduler, "resolve_service_account_json", lambda contract: service_account_json)
    monkeypatch.setattr(scheduler, "resolve_spreadsheet_id", lambda override, contract: "sheet-id")
    monkeypatch.setattr(
        scheduler,
        "run_publish_cycle",
        lambda **kwargs: events.append(
            f"publish:{kwargs['force_source_refresh']}"
        ) or 0,
    )

    assert scheduler.main(["--force-source-refresh"]) == 0
    assert events == ["lock_enter", "publish:True", "lock_exit"]


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


def test_forced_source_refresh_returns_temporary_failure_when_shared_lock_is_busy(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    import scripts.run_google_ops_board_publish_scheduler as scheduler

    service_account_json = tmp_path / "service-account.json"
    service_account_json.write_text("{}", encoding="utf-8")

    class BusyLock:
        def __enter__(self):
            raise RuntimeError("Another Google Ops Board automation instance is already running.")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.delenv("AB_GOOGLE_OPS_BOARD_LOCK_HELD", raising=False)
    monkeypatch.setattr(scheduler, "GoogleOpsBoardAutomationLock", BusyLock)
    monkeypatch.setattr(scheduler, "load_ops_board_contract", lambda path: object())
    monkeypatch.setattr(scheduler, "resolve_service_account_json", lambda contract: service_account_json)
    monkeypatch.setattr(scheduler, "resolve_spreadsheet_id", lambda override, contract: "sheet-id")

    assert scheduler.main(["--force-source-refresh"]) == scheduler.LOCK_CONTENTION_EXIT_CODE
    assert "already running" in capsys.readouterr().err
