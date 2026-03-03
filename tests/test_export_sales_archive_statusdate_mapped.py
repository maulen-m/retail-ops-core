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
