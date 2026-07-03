from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.export_sales_archive_statusdate_mapped import ExportError, export_sales_archive_statusdate_mapped


def _write_base_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "№ заказа": "O1",
                "Дата поступления заказа": "10.01.2026",
                "Дата изменения статуса": "",
                "Статус": "Завершен",
                "Количество": "1",
                "Сумма": "12000",
                "Склад передачи КД": "30000001_PP1",
                "Артикул": "SKU_A",
                "Название в системе продавца": "Offer A",
                "mapped_sku_key": "SKU_A",
                "mapped_size": "L",
                "Стоимость доставки для продавца": "500",
                "Компенсация за доставку": "0",
            },
            {
                "№ заказа": "O2",
                "Дата поступления заказа": "20.07.2025",
                "Дата изменения статуса": "",
                "Статус": "ВЫДАН",
                "Количество": "2",
                "Сумма": "10000",
                "Склад передачи КД": "30137883_PP1",
                "Артикул": "SKU_B",
                "Название в системе продавца": "Offer B",
                "mapped_sku_key": "SKU_B",
                "mapped_size": "M",
                "Стоимость доставки для продавца": "600",
                "Компенсация за доставку": "100",
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def _write_ui_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "№ заказа": "O1",
                "Статус": "Завершен",
                "Дата изменения статуса": "11.01.2026",
                "Склад передачи КД": "30000001_PP1",
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def test_export_sales_archive_statusdate_mapped_outputs_expected_sources(tmp_path: Path) -> None:
    base_csv = tmp_path / "base.csv"
    ui_csv = tmp_path / "ui.csv"
    _write_base_csv(base_csv)
    _write_ui_csv(ui_csv)

    report = export_sales_archive_statusdate_mapped(
        since=date(2025, 6, 6),
        until=date(2026, 3, 2),
        ocean_drop_path=base_csv,
        output_root=tmp_path / "out",
        ui_sources=[ui_csv],
        strict=True,
    )

    out_csv = Path(report["output_csv"])
    assert out_csv.exists()

    df = pd.read_csv(out_csv, dtype=str)
    assert len(df) == 2

    o1 = df[df["order_id"] == "O1"].iloc[0]
    assert o1["transaction_date"] == "2026-01-11"
    assert o1["transaction_date_source"] == "ui_override_status_date"

    o2 = df[df["order_id"] == "O2"].iloc[0]
    assert o2["transaction_date"] == "2025-07-20"
    assert o2["transaction_date_source"] == "creation_date_fallback"

    manifest = json.loads(Path(report["manifest_json"]).read_text(encoding="utf-8"))
    assert int(manifest["output"]["rows"]) == 2


def test_export_sales_archive_statusdate_mapped_strict_requires_ui_source(tmp_path: Path) -> None:
    base_csv = tmp_path / "base.csv"
    _write_base_csv(base_csv)

    with pytest.raises(ExportError, match="requires at least one UI source"):
        export_sales_archive_statusdate_mapped(
            since=date(2025, 6, 6),
            until=date(2026, 3, 2),
            ocean_drop_path=base_csv,
            output_root=tmp_path / "out",
            ui_sources=[],
            strict=True,
        )


def test_export_sales_archive_statusdate_mapped_overrides_status_from_ui(tmp_path: Path) -> None:
    base_csv = tmp_path / "base.csv"
    pd.DataFrame(
        [
            {
                "№ заказа": "O3",
                "Дата поступления заказа": "03.03.2026",
                "Дата изменения статуса": "",
                "Статус": "Ожидает передачи курьеру",
                "Количество": "1",
                "Сумма": "9000",
                "Склад передачи КД": "30000001_PP1",
                "Артикул": "SKU_C",
                "Название в системе продавца": "Offer C",
                "mapped_sku_key": "SKU_C",
                "mapped_size": "L",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
            }
        ]
    ).to_csv(base_csv, index=False, encoding="utf-8")

    ui_csv = tmp_path / "ui.csv"
    pd.DataFrame(
        [
            {
                "№ заказа": "O3",
                "Статус": "Завершен",
                "Дата изменения статуса": "03.03.2026",
                "Склад передачи КД": "30000001_PP1",
            }
        ]
    ).to_csv(ui_csv, index=False, encoding="utf-8")

    report = export_sales_archive_statusdate_mapped(
        since=date(2025, 6, 6),
        until=date(2026, 3, 4),
        ocean_drop_path=base_csv,
        output_root=tmp_path / "out",
        ui_sources=[ui_csv],
        strict=True,
    )
    df = pd.read_csv(Path(report["output_csv"]), dtype=str)
    row = df[df["order_id"] == "O3"].iloc[0]
    assert row["status_internal"] == "DELIVERED"
    assert row["transaction_date"] == "2026-03-03"
    assert row["transaction_date_source"] == "ui_override_status_date"

    manifest = json.loads(Path(report["manifest_json"]).read_text(encoding="utf-8"))
    assert int(manifest["ui_status_values_updated"]) == 1


def test_export_sales_archive_statusdate_mapped_overlays_blank_warehouse_rows_with_store_fallbacks(
    tmp_path: Path,
) -> None:
    base_csv = tmp_path / "base.csv"
    pd.DataFrame(
        [
            {
                "№ заказа": "O-MAPPING",
                "Дата поступления заказа": "01.03.2026",
                "Дата изменения статуса": "02.03.2026",
                "Статус": "Ожидает передачи курьеру",
                "Количество": "1",
                "Сумма": "14990",
                "Склад передачи КД": "",
                "Оформил": "",
                "mapping_source_store_code": "ACMEWEAR",
                "Артикул": "SKU_ACMEWEAR",
                "Название в системе продавца": "Offer AcmeWear",
                "mapped_sku_key": "SKU_ACMEWEAR",
                "mapped_size": "XL",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
            },
            {
                "№ заказа": "O-ALIAS",
                "Дата поступления заказа": "01.03.2026",
                "Дата изменения статуса": "02.03.2026",
                "Статус": "Ожидает передачи курьеру",
                "Количество": "2",
                "Сумма": "19990",
                "Склад передачи КД": "",
                "Оформил": "STORE-B",
                "mapping_source_store_code": "",
                "Артикул": "SKU_STOREB",
                "Название в системе продавца": "Offer MGroup",
                "mapped_sku_key": "SKU_STOREB",
                "mapped_size": "L",
                "Стоимость доставки для продавца": "0",
                "Компенсация за доставку": "0",
            },
        ]
    ).to_csv(base_csv, index=False, encoding="utf-8")

    ui_csv = tmp_path / "ui.csv"
    pd.DataFrame(
        [
            {
                "order_id": "O-MAPPING",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-03-04",
                "warehouse_code": "30137883_PP1",
                "store_code": "ACMEWEAR",
            },
            {
                "order_id": "O-ALIAS",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-03-05",
                "warehouse_code": "30000002_PP2",
                "store_code": "STOREB",
            },
        ]
    ).to_csv(ui_csv, index=False, encoding="utf-8")

    report = export_sales_archive_statusdate_mapped(
        since=date(2026, 3, 1),
        until=date(2026, 3, 31),
        ocean_drop_path=base_csv,
        output_root=tmp_path / "out",
        ui_sources=[ui_csv],
        strict=True,
    )

    df = pd.read_csv(Path(report["output_csv"]), dtype=str)
    by_order = df.set_index("order_id").to_dict(orient="index")

    assert by_order["O-MAPPING"]["store_code"] == "ACMEWEAR"
    assert by_order["O-MAPPING"]["kd_warehouse"] == "30137883_PP1"
    assert by_order["O-MAPPING"]["transaction_date"] == "2026-03-04"
    assert by_order["O-MAPPING"]["transaction_date_source"] == "ui_override_status_date"
    assert by_order["O-MAPPING"]["status_internal"] == "DELIVERED"

    assert by_order["O-ALIAS"]["store_code"] == "STOREB"
    assert by_order["O-ALIAS"]["kd_warehouse"] == "30000002_PP1"
    assert by_order["O-ALIAS"]["transaction_date"] == "2026-03-05"
    assert by_order["O-ALIAS"]["transaction_date_source"] == "ui_override_status_date"
    assert by_order["O-ALIAS"]["quantity"] == "2.0"

    manifest = json.loads(Path(report["manifest_json"]).read_text(encoding="utf-8"))
    assert int(manifest["ui_status_dates_filled"]) == 2
    assert int(manifest["ui_status_values_updated"]) == 2
    assert int(manifest["ui_blank_warehouses_backfilled"]) == 2
