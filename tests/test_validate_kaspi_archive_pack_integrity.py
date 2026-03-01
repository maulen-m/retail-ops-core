from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.validate_kaspi_archive_pack_integrity import validate_kaspi_archive_pack_integrity


def _write_fixture_pack(root: Path, *, missing_status_change_date: bool) -> Path:
    pack = root / "kaspi_archive_ui_history_2026-02-26_to_2026-02-26_fixture"
    store_dir = pack / "store_UNIVERSAL"
    store_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "since": "2026-02-26",
        "until": "2026-02-26",
        "results": [
            {
                "store_code": "UNIVERSAL",
                "date_mode": "statusChangeDate",
                "orders_dedup": 10,
                "orders_selected": 10,
            }
        ],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with (store_dir / "windows.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["since", "until", "status"])
        writer.writeheader()
        writer.writerow({"since": "2026-02-26", "until": "2026-02-26", "status": "ok"})

    status_change_value = "" if missing_status_change_date else "26.02.2026"
    with (store_dir / "ArchiveOrders_UNIVERSAL.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "№ заказа",
                "Дата поступления заказа",
                "Название товара в Kaspi Магазине",
                "Название в системе продавца",
                "Артикул",
                "Сумма",
                "Категория",
                "Адрес самовывоза/доставки",
                "Дата изменения статуса",
                "Статус",
                "Количество",
                "Склад передачи КД",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "№ заказа": "123456789",
                "Дата поступления заказа": "26.02.2026",
                "Название товара в Kaspi Магазине": "x",
                "Название в системе продавца": "x",
                "Артикул": "SKU-1",
                "Сумма": "1000",
                "Категория": "x",
                "Адрес самовывоза/доставки": "x",
                "Дата изменения статуса": status_change_value,
                "Статус": "Выдан",
                "Количество": "1",
                "Склад передачи КД": "30000001_PP1",
            }
        )
    return pack


def test_api_contract_allows_missing_status_change_date_for_completed(tmp_path: Path) -> None:
    pack = _write_fixture_pack(tmp_path, missing_status_change_date=True)
    report = validate_kaspi_archive_pack_integrity(
        source="api",
        export_root=pack,
        as_of="2026-02-26",
        since=None,
        until=None,
        strict=True,
        output_root=tmp_path / "out",
    )
    assert report["status"] == "PASS"


def test_ui_contract_fails_when_completed_status_change_date_missing(tmp_path: Path) -> None:
    pack = _write_fixture_pack(tmp_path, missing_status_change_date=True)
    with pytest.raises(RuntimeError, match="archive pack integrity failed for source=ui"):
        validate_kaspi_archive_pack_integrity(
            source="ui",
            export_root=pack,
            as_of="2026-02-26",
            since=None,
            until=None,
            strict=True,
            output_root=tmp_path / "out",
        )
