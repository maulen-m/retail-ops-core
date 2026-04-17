from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from scripts.run_google_ops_board_publish_scheduler import (
    build_source_refresh_commands,
    inspect_activeorders_source,
    is_source_refresh_slot,
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
