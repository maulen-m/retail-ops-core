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


def test_reference_adapter_accepts_store_named_xlsx_files(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "store-b.xlsx",
        [
            {
                "№ заказа": "3001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "2",
                "Сумма": "3600",
                "Склад передачи КД": "30000002_PP1",
                "Артикул": "SKU_M",
                "Название товара в Kaspi Магазине": "M",
            }
        ],
    )
    report = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=None,
        explicit_store_map={"30000002_PP1": "STOREB"},
    )
    assert report["status"] == "available"
    records = report["daily_by_store"].to_dict("records")
    assert records == [
        {
            "sale_date": "2026-02-25",
            "store_code": "STOREB",
            "units_delivered": 2.0,
            "gross_rev_kzt": 3600.0,
            "orders_delivered": 1,
        }
    ]


def test_reference_adapter_normalizes_prefixed_article_identity(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "store-b.xlsx",
        [
            {
                "№ заказа": "4001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "1460",
                "Склад передачи КД": "30000002_PP1",
                "Артикул": "135277314CL_NEW-CLO_MEN_RUSH-PRO_BLACK_L_135277314",
                "Название товара в Kaspi Магазине": "Рашгард черный L",
            }
        ],
    )
    report = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=None,
        explicit_store_map={"30000002_PP1": "STOREB"},
    )
    assert report["status"] == "available"
    rec = report["lines"].to_dict("records")[0]
    assert rec["resolved_sku_key"] == "CL_NEW-CLO_MEN_RUSH-PRO_BLACK"
    assert rec["resolved_sku_id"] == "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_L"
    assert rec["resolved_my_size"] == "L"


def test_reference_adapter_uses_offer_map_when_article_identity_is_unusable(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "store-b.xlsx",
        [
            {
                "№ заказа": "5001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "8990",
                "Склад передачи КД": "30000002_PP1",
                "Артикул": "103217238_324090514",
                "Название товара в Kaspi Магазине": "Комплект Antec RASH-921 Рашгард 5 в 1 черный 2XL",
            }
        ],
    )

    db_path = tmp_path / "app.db"
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('STOREB', 'CL_OC_MEN_LINE52_BLACK_2XL_103217220',
                'Комплект Antec RASH-921 Рашгард 5 в 1 черный 2XL',
                'CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK_2XL', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg)
        VALUES ('CL_OC_MEN_LINE52_BLACK', 47, 0.95)
        """
    )
    conn.commit()
    conn.close()

    report = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=db_path,
        explicit_store_map={"30000002_PP1": "STOREB"},
    )
    assert report["status"] == "available"
    rec = report["lines"].to_dict("records")[0]
    assert rec["resolved_sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert rec["resolved_sku_id"] == "CL_OC_MEN_LINE52_BLACK_2XL"


def test_reference_adapter_uses_article_numeric_token_fallback(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    _write_archive(
        archive_dir / "store-b.xlsx",
        [
            {
                "№ заказа": "6001",
                "Дата изменения статуса": "25.02.2026",
                "Статус": "Выдан",
                "Количество": "1",
                "Сумма": "8990",
                "Склад передачи КД": "30000002_PP1",
                "Артикул": "116515378_240177069",
                "Название товара в Kaspi Магазине": "Спортивный костюм PRO COMBAT 528742263 черный 2XL",
            }
        ],
    )

    db_path = tmp_path / "app.db"
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES ('STOREB', 'CL_OC_MEN_LINE52_BLACK_L_116515378',
                'Спортивный костюм PRO COMBAT 528742263 черный M',
                'CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK_L', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg)
        VALUES ('CL_OC_MEN_LINE52_BLACK', 47, 0.95)
        """
    )
    conn.commit()
    conn.close()

    report = build_reference_from_archive_dir(
        archive_dir=archive_dir,
        as_of=date(2026, 2, 26),
        include_as_of_day=False,
        db_path=db_path,
        explicit_store_map={"30000002_PP1": "STOREB"},
    )
    assert report["status"] == "available"
    rec = report["lines"].to_dict("records")[0]
    assert rec["resolved_sku_key"] == "CL_OC_MEN_LINE52_BLACK"
