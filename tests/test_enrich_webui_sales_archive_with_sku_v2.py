from __future__ import annotations

import csv
from pathlib import Path
import sqlite3

import pandas as pd

from scripts.enrich_webui_sales_archive_with_sku_v2 import (
    MAPPING_APPEND_COLUMNS,
    enrich_webui_sales_archive_with_sku_v2,
)


RAW_COLUMNS = [
    "pack_id",
    "store_code",
    "source_file",
    "source_file_sha256",
    "source_file_format",
    "source_row_number",
    "order_id",
    "created_at",
    "status_change_at",
    "status_raw",
    "status_internal",
    "quantity",
    "net_rev_kzt",
    "warehouse_code",
    "article",
    "kaspi_offer_name",
    "seller_system_name",
    "category",
    "pickup_or_delivery_address",
    "cancel_reason",
    "payment_mode",
    "delivery_mode",
    "courier_service",
    "planned_courier_at",
    "delivery_fee_buyer_kzt",
    "delivery_fee_seller_kzt",
    "transaction_signature_required",
    "status_change_required",
    "status_change_missing",
    "row_fingerprint",
    "window_since",
    "window_until",
]


def _write_csv(path: Path, rows: list[dict[str, str]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _make_raw_row(
    *,
    order_id: str,
    store_code: str,
    article: str,
    kaspi_offer_name: str,
    seller_system_name: str | None = None,
    warehouse_code: str | None = None,
) -> dict[str, str]:
    row = {column: "" for column in RAW_COLUMNS}
    row.update(
        {
            "pack_id": "pack-1",
            "store_code": store_code,
            "source_file": f"store_{store_code}/ArchiveOrders_{store_code}.xlsx",
            "source_file_sha256": "deadbeef",
            "source_file_format": "xlsx",
            "source_row_number": "2",
            "order_id": order_id,
            "created_at": "2026-03-19",
            "status_change_at": "2026-03-20",
            "status_raw": "Выдан",
            "status_internal": "DELIVERED",
            "quantity": "1.0",
            "net_rev_kzt": "10000.0",
            "warehouse_code": warehouse_code or "30000001_PP1",
            "article": article,
            "kaspi_offer_name": kaspi_offer_name,
            "seller_system_name": seller_system_name or kaspi_offer_name,
            "category": "Одежда",
            "delivery_mode": "DELIVERY_PICKUP",
            "row_fingerprint": f"fp-{order_id}",
            "window_since": "2026-03-01",
            "window_until": "2026-03-20",
        }
    )
    return row


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
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
    conn.commit()
    conn.close()


def _insert_dim_sku(path: Path, *sku_keys: str) -> None:
    conn = sqlite3.connect(path)
    for sku_key in sku_keys:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES (?, ?, ?)",
            (sku_key, 1.0, 1.0),
        )
    conn.commit()
    conn.close()


def _insert_article_map(
    path: Path,
    *,
    store_code: str,
    kaspi_article: str,
    kaspi_offer_name: str,
    sku_key: str,
    sku_id: str,
    active_flag: int = 1,
) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag),
    )
    conn.commit()
    conn.close()


def _write_historical_mapped_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "№ заказа",
        "Название товара в Kaspi Магазине",
        "Название в системе продавца",
        "Артикул",
        "Склад передачи КД",
        "mapped_sku_key",
        "mapped_size",
        "mapping_source_store_code",
    ]
    _write_csv(path, rows, fieldnames=fieldnames)


def test_enrich_webui_sales_archive_with_sku_v2_appends_mapping_columns_and_preserves_row_order(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
    output_csv = tmp_path / "ArchiveOrders_WEBUI_MERGED_ALL_STORES_v2.csv"
    db_path = tmp_path / "app.db"
    mapped_root = tmp_path / "mapped_data"

    rows = [
        _make_raw_row(
            order_id="1001",
            store_code="UNIVERSAL",
            article="CL_OC_MEN_LINE52_BLACK_XL_123456789",
            kaspi_offer_name="Комплект Line52 черный XL",
        ),
        _make_raw_row(
            order_id="1002",
            store_code="STOREB",
            article="103217238_324090514",
            kaspi_offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный 2XL",
            warehouse_code="30000002_PP1",
        ),
    ]
    _write_csv(source_csv, rows, fieldnames=RAW_COLUMNS)

    _init_db(db_path)
    _insert_dim_sku(db_path, "CL_OC_MEN_LINE52_BLACK")
    _insert_article_map(
        db_path,
        store_code="STOREB",
        kaspi_article="CL_OC_MEN_LINE52_BLACK_2XL_103217220",
        kaspi_offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный 2XL",
        sku_key="CL_OC_MEN_LINE52_BLACK",
        sku_id="CL_OC_MEN_LINE52_BLACK_2XL",
    )

    report = enrich_webui_sales_archive_with_sku_v2(
        source_csv=source_csv,
        output_csv=output_csv,
        db_path=db_path,
        historical_mapped_root=mapped_root,
    )

    assert report["rows_total"] == 2
    assert report["resolved_rows"] == 2

    frame = pd.read_csv(output_csv, dtype=str, keep_default_na=False)
    assert frame.columns.tolist() == RAW_COLUMNS + list(MAPPING_APPEND_COLUMNS)
    assert frame["order_id"].tolist() == ["1001", "1002"]
    assert frame["mapped_sku_key"].tolist() == [
        "CL_OC_MEN_LINE52_BLACK",
        "CL_OC_MEN_LINE52_BLACK",
    ]
    assert frame["mapping_method"].tolist() == ["parser", "db_offer"]


def test_enrich_webui_sales_archive_with_sku_v2_uses_historical_article_exact_fallback(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_v2.csv"
    db_path = tmp_path / "app.db"
    mapped_root = tmp_path / "mapped_data"

    _write_csv(
        source_csv,
        [
            _make_raw_row(
                order_id="2001",
                store_code="11KZ",
                article="122232437_802810737",
                kaspi_offer_name="Спортивный костюм Sports 87479745016 черный 3XL",
                warehouse_code="30290083_PP1",
            )
        ],
        fieldnames=RAW_COLUMNS,
    )

    _init_db(db_path)
    _insert_dim_sku(db_path, "CL_OC_MEN_LINE52_BLACK")
    _write_historical_mapped_csv(
        mapped_root / "hist.csv",
        [
            {
                "№ заказа": "9001",
                "Название товара в Kaspi Магазине": "",
                "Название в системе продавца": "Спортивный костюм Sports 87479745016 черный 3XL",
                "Артикул": "122232437_802810737",
                "Склад передачи КД": "30290083_PP1",
                "mapped_sku_key": "CL_OC_MEN_LINE52_BLACK",
                "mapped_size": "3XL",
                "mapping_source_store_code": "11KZ",
            }
        ],
    )

    enrich_webui_sales_archive_with_sku_v2(
        source_csv=source_csv,
        output_csv=output_csv,
        db_path=db_path,
        historical_mapped_root=mapped_root,
    )
    row = _read_rows(output_csv)[0]
    assert row["mapped_sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert row["mapped_size"] == "3XL"
    assert row["mapping_method"] == "hist_article_exact"
    assert row["mapping_source_store_code"] == "11KZ"


def test_enrich_webui_sales_archive_with_sku_v2_uses_historical_seller_name_fallback(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_v2.csv"
    db_path = tmp_path / "app.db"
    mapped_root = tmp_path / "mapped_data"

    _write_csv(
        source_csv,
        [
                _make_raw_row(
                    order_id="3001",
                    store_code="ACMEWEAR",
                    article="999999_111111111",
                    kaspi_offer_name="",
                    seller_system_name="Теплый комплект cashmere white 2XL",
                    warehouse_code="30137883_PP1",
                )
            ],
            fieldnames=RAW_COLUMNS,
    )
    _init_db(db_path)
    _insert_dim_sku(db_path, "CL_OC_MEN_LINE51_WHITE")
    _write_historical_mapped_csv(
        mapped_root / "hist.csv",
            [
                {
                    "№ заказа": "9002",
                    "Название товара в Kaspi Магазине": "",
                    "Название в системе продавца": "Теплый комплект cashmere white 2XL",
                    "Артикул": "LEGACY_LINE",
                    "Склад передачи КД": "30137883_PP1",
                    "mapped_sku_key": "CL_OC_MEN_LINE51_WHITE",
                "mapped_size": "2XL",
                "mapping_source_store_code": "ACMEWEAR",
            }
        ],
    )

    enrich_webui_sales_archive_with_sku_v2(
        source_csv=source_csv,
        output_csv=output_csv,
        db_path=db_path,
        historical_mapped_root=mapped_root,
    )
    row = _read_rows(output_csv)[0]
    assert row["mapped_sku_key"] == "CL_OC_MEN_LINE51_WHITE"
    assert row["mapped_size"] == "2XL"
    assert row["mapping_method"] == "hist_seller_exact"


def test_enrich_webui_sales_archive_with_sku_v2_marks_outliers_unresolved_without_inventing_sku(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_v2.csv"
    db_path = tmp_path / "app.db"
    mapped_root = tmp_path / "mapped_data"

    _write_csv(
        source_csv,
        [
            _make_raw_row(
                order_id="698394285",
                store_code="11KZ",
                article="122704812_773932398",
                kaspi_offer_name='Декорация для праздника Декор для Хэллоуина "Скелет Натуральный", 165 см 1 шт',
                seller_system_name='Декорация для праздника Декор для Хэллоуина "Скелет Натуральный", 165 см 1 шт',
                warehouse_code="30290083_PP1",
            )
        ],
        fieldnames=RAW_COLUMNS,
    )
    _init_db(db_path)

    report = enrich_webui_sales_archive_with_sku_v2(
        source_csv=source_csv,
        output_csv=output_csv,
        db_path=db_path,
        historical_mapped_root=mapped_root,
    )

    assert report["resolved_rows"] == 0
    assert report["unresolved_rows"] == 1
    row = _read_rows(output_csv)[0]
    assert row["mapped_sku_key"] == ""
    assert row["mapped_size"] == ""
    assert row["mapping_status"] == "unresolved"
    assert row["mapping_method"] == "unresolved"
    assert row["mapping_source_store_code"] == ""


def test_enrich_webui_sales_archive_with_sku_v2_prefers_parser_over_conflicting_history(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "raw.csv"
    output_csv = tmp_path / "raw_v2.csv"
    db_path = tmp_path / "app.db"
    mapped_root = tmp_path / "mapped_data"

    _write_csv(
        source_csv,
        [
            _make_raw_row(
                order_id="4001",
                store_code="UNIVERSAL",
                article="CL_NEW-CLO_MEN_LEG_BLACK_XL_123456789",
                kaspi_offer_name="Леггинсы черные XL",
            )
        ],
        fieldnames=RAW_COLUMNS,
    )
    _init_db(db_path)
    _insert_dim_sku(db_path, "CL_NEW-CLO_MEN_LEG_BLACK", "CL_OC_MEN_LINE52_BLACK")
    _write_historical_mapped_csv(
        mapped_root / "hist.csv",
        [
            {
                "№ заказа": "9003",
                "Название товара в Kaspi Магазине": "Леггинсы черные XL",
                "Название в системе продавца": "Леггинсы черные XL",
                "Артикул": "CL_NEW-CLO_MEN_LEG_BLACK_XL_123456789",
                "Склад передачи КД": "30000001_PP1",
                "mapped_sku_key": "CL_OC_MEN_LINE52_BLACK",
                "mapped_size": "L",
                "mapping_source_store_code": "UNIVERSAL",
            }
        ],
    )

    enrich_webui_sales_archive_with_sku_v2(
        source_csv=source_csv,
        output_csv=output_csv,
        db_path=db_path,
        historical_mapped_root=mapped_root,
    )
    row = _read_rows(output_csv)[0]
    assert row["mapped_sku_key"] == "CL_NEW-CLO_MEN_LEG_BLACK"
    assert row["mapped_size"] == "XL"
    assert row["mapping_method"] == "parser"
