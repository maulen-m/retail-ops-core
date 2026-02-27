from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from core.sales.kaspi_etl_reference import build_reference_from_archive_dir


def _write_archive(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)


def test_reference_adapter_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "ArchiveOrders_a.xlsx",
        [
            {
                "№ заказа": "1001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1200",
                "Склад передачи КД": "30000001_PP1",
                "Артикул": "SKU_A",
                "Название товара в Kaspi Магазине": "A",
            }
        ],
    )
    first = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=None,
        explicit_store_map={"30000001_PP1": "UNIVERSAL"},
    )
    second = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=None,
        explicit_store_map={"30000001_PP1": "UNIVERSAL"},
    )
    assert first["status"] == "available"
    assert second["status"] == "available"
    assert first["lines"].to_dict("records") == second["lines"].to_dict("records")
    assert first["daily_by_store"].to_dict("records") == second["daily_by_store"].to_dict("records")


def test_reference_adapter_excludes_asof_day_by_default(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "ArchiveOrders_b.xlsx",
        [
            {
                "№ заказа": "2001",
                "Дата изменения статуса": "26.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1000",
                "Склад передачи КД": "30137883_PP1",
                "Артикул": "SKU_B",
                "Название товара в Kaspi Магазине": "B",
            }
        ],
    )
    report = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=None,
        explicit_store_map={"30137883_PP1": "ACMEWEAR"},
    )
    assert report["status"] == "missing"
    assert report["reason"] == "no_delivered_rows_in_window"

