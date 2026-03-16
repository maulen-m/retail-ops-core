from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.profile_webui_normalized_status_change import (
    profile_webui_normalized_status_change,
)
from scripts.profile_webui_status_change_source import (
    profile_webui_status_change_source,
)
from scripts.webui_archive_truth_utils import PACK_NORMALIZED_COLUMNS


def _write_raw_xlsx(path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "№ заказа": "1001",
                "Дата поступления заказа": "01.01.2026",
                "Название товара в Kaspi Магазине": "Item A",
                "Название в системе продавца": "Item A",
                "Артикул": "SKU-A",
                "Сумма": "1000",
                "Категория": "Test",
                "Адрес самовывоза/доставки": "",
                "Дата изменения статуса": "",
                "Статус": "Завершен",
                "Причина отмены": "",
                "Способ оплаты": "",
                "Способ доставки": "",
                "Курьерская служба": "",
                "Принял": "",
                "Выдал": "",
                "Отменил": "",
                "Оценка покупателя": "",
                "Отзыв покупателя": "",
                "Дата публикации отзыва": "",
                "Оформил": "",
                "Количество": "1",
                "Стоимость доставки для покупателя": "0",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
                "Требуется подписание": "",
                "Плановая дата передачи курьеру": "",
                "Телефон": "",
                "Склад передачи КД": "ACMEWEAR",
            },
            {
                "№ заказа": "1002",
                "Дата поступления заказа": "02.01.2026",
                "Название товара в Kaspi Магазине": "Item B",
                "Название в системе продавца": "Item B",
                "Артикул": "SKU-B",
                "Сумма": "1500",
                "Категория": "Test",
                "Адрес самовывоза/доставки": "",
                "Дата изменения статуса": "05.01.2026",
                "Статус": "Завершен",
                "Причина отмены": "",
                "Способ оплаты": "",
                "Способ доставки": "",
                "Курьерская служба": "",
                "Принял": "",
                "Выдал": "",
                "Отменил": "",
                "Оценка покупателя": "",
                "Отзыв покупателя": "",
                "Дата публикации отзыва": "",
                "Оформил": "",
                "Количество": "1",
                "Стоимость доставки для покупателя": "0",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
                "Требуется подписание": "",
                "Плановая дата передачи курьеру": "",
                "Телефон": "",
                "Склад передачи КД": "ACMEWEAR",
            },
            {
                "№ заказа": "1003",
                "Дата поступления заказа": "03.01.2026",
                "Название товара в Kaspi Магазине": "Item C",
                "Название в системе продавца": "Item C",
                "Артикул": "SKU-C",
                "Сумма": "500",
                "Категория": "Test",
                "Адрес самовывоза/доставки": "",
                "Дата изменения статуса": "04.01.2026",
                "Статус": "Возвращен",
                "Причина отмены": "",
                "Способ оплаты": "",
                "Способ доставки": "",
                "Курьерская служба": "",
                "Принял": "",
                "Выдал": "",
                "Отменил": "",
                "Оценка покупателя": "",
                "Отзыв покупателя": "",
                "Дата публикации отзыва": "",
                "Оформил": "",
                "Количество": "1",
                "Стоимость доставки для покупателя": "0",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
                "Требуется подписание": "",
                "Плановая дата передачи курьеру": "",
                "Телефон": "",
                "Склад передачи КД": "ACMEWEAR",
            },
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(path, index=False)


def _write_pack(root: Path) -> Path:
    pack_root = root / "pack"
    pack_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "pack_id": "pack-1",
        "files": [],
    }
    (pack_root / "source_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    rows: list[dict[str, str]] = []
    for order_id, store_code, status_change_at in [
        ("1001", "ACMEWEAR", ""),
        ("1002", "ACMEWEAR", "2026-01-05"),
        ("1003", "MELVIS", ""),
    ]:
        row = {column: "" for column in PACK_NORMALIZED_COLUMNS}
        row.update(
            {
                "pack_id": "pack-1",
                "store_code": store_code,
                "source_file": f"{store_code}.xlsx",
                "source_file_sha256": f"sha-{order_id}",
                "source_file_format": "xlsx",
                "source_row_number": "2",
                "order_id": order_id,
                "created_at": "2026-01-01",
                "status_change_at": status_change_at,
                "status_raw": "Завершен",
                "status_internal": "DELIVERED",
                "quantity": "1",
                "net_rev_kzt": "1000",
                "warehouse_code": store_code,
                "status_change_required": "True",
                "status_change_missing": "True" if not status_change_at else "",
                "row_fingerprint": f"fp-{order_id}",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
            }
        )
        rows.append(row)
    pd.DataFrame(rows, columns=PACK_NORMALIZED_COLUMNS).to_csv(
        pack_root / "normalized_rows.csv",
        index=False,
        encoding="utf-8",
    )
    return pack_root


def test_profile_webui_status_change_source_reports_examples(tmp_path: Path) -> None:
    raw_file = tmp_path / "store_ACMEWEAR" / "raw" / "ArchiveOrders_ACMEWEAR.xlsx"
    _write_raw_xlsx(raw_file)

    report = profile_webui_status_change_source(
        inputs=[raw_file],
        store_code="ACMEWEAR",
        output_dir=tmp_path / "out",
    )

    assert report["status"] == "PASS"
    assert report["viability_hint"] == "RAW_HAS_DELIVERED_STATUS_CHANGE_VALUES"
    profile = pd.read_csv(report["profile_csv"], dtype=object, keep_default_na=False)
    summary = profile[
        (profile["record_type"] == "SUMMARY")
        & (profile["scope"] == "STATUS")
        & (profile["status_internal"] == "DELIVERED")
    ].iloc[0]
    assert summary["detected_status_change_headers"] == "Дата изменения статуса"
    assert int(summary["total_rows"]) == 2
    assert int(summary["status_change_nonblank_count"]) == 1
    blank_examples = profile[profile["record_type"] == "EXAMPLE_DELIVERED_BLANK"]
    present_examples = profile[profile["record_type"] == "EXAMPLE_DELIVERED_PRESENT"]
    assert blank_examples["order_id"].tolist() == ["1001"]
    assert present_examples["order_id"].tolist() == ["1002"]
    md_text = Path(report["profile_md"]).read_text(encoding="utf-8")
    assert "Дата изменения статуса" in md_text
    assert "No delivered rows with present status-change values" not in md_text


def test_profile_webui_normalized_status_change_by_store(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path)

    report = profile_webui_normalized_status_change(
        pack_root=pack_root,
        output_dir=tmp_path / "out",
    )

    assert report["status"] == "PASS"
    profile = pd.read_csv(report["profile_csv"], dtype=object, keep_default_na=False)
    total = profile[profile["scope"] == "PACK_TOTAL"].iloc[0]
    assert total["source_pack_id"] == "pack-1"
    assert int(total["delivered_rows"]) == 3
    assert int(total["status_change_nonblank_count"]) == 1
    by_store = profile[profile["scope"] == "STORE"].sort_values("store_code").reset_index(drop=True)
    assert by_store["store_code"].tolist() == ["MELVIS", "ACMEWEAR"]
    assert by_store["status_change_blank_count"].tolist() == ["1", "1"]
