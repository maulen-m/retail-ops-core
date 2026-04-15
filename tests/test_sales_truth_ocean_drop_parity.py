from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts.validate_sales_truth_ocean_drop_parity import (
    validate_sales_truth_ocean_drop_parity,
)


def _seed_db(path: Path, *, rev_ord_1: float = 1200.0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity REAL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            api_updated_at TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code, quantity, sell_price_kzt, delivery_fee,
         cogs, net_rev, profit, status, return_flag, return_date, source_file, api_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "ORD-1",
                "2026-02-25",
                "SKU_A",
                "SKU_A_L",
                "L",
                "Offer A",
                "ACMEWEAR",
                2,
                600,
                0,
                None,
                rev_ord_1,
                None,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
            (
                "ORD-2",
                "2026-02-25",
                "SKU_B",
                "SKU_B_M",
                "M",
                "Offer B",
                "UNIVERSAL",
                1,
                800,
                0,
                None,
                800,
                None,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _write_ocean_drop(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "№ заказа": "ORD-1",
                "Статус": "ЗАВЕРШЕН",
                "Количество": "2",
                "Сумма": "1200",
                "Склад передачи КД": "30137883_PP1",
                "Дата поступления заказа": "24.02.2026",
                "Дата изменения статуса": "25.02.2026",
                "Артикул": "SKU_A",
                "Название в системе продавца": "Offer A",
                "mapped_sku_key": "SKU_A",
                "mapped_size": "L",
            },
            {
                "№ заказа": "ORD-2",
                "Статус": "ВЫДАН",
                "Количество": "1",
                "Сумма": "800",
                "Склад передачи КД": "30000001_PP1",
                "Дата поступления заказа": "24.02.2026",
                "Дата изменения статуса": "25.02.2026",
                "Артикул": "SKU_B",
                "Название в системе продавца": "Offer B",
                "mapped_sku_key": "SKU_B",
                "mapped_size": "M",
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def test_sales_truth_ocean_drop_parity_passes_for_matching_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    ocean_drop = tmp_path / "ocean_drop.csv"
    output_root = tmp_path / "out"

    _seed_db(db, rev_ord_1=1200.0)
    _write_ocean_drop(ocean_drop)

    report = validate_sales_truth_ocean_drop_parity(
        db_path=db,
        as_of=date(2026, 2, 26),
        ocean_drop_path=ocean_drop,
        output_root=output_root,
        volatility_days=0,
        strict=True,
        crm_archive_lookup_path=None,
    )

    assert report["status"] == "PASS"
    out_dir = output_root / "2026-02-26"
    assert (out_dir / "parity_report.json").exists()
    assert (out_dir / "parity_report.md").exists()
    assert (out_dir / "diff_missing_order_ids.csv").exists()
    assert (out_dir / "diff_extra_order_ids.csv").exists()
    assert (out_dir / "diff_date_mismatches.csv").exists()


def test_sales_truth_ocean_drop_parity_fails_closed_on_nonvolatile_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    ocean_drop = tmp_path / "ocean_drop.csv"

    _seed_db(db, rev_ord_1=999.0)
    _write_ocean_drop(ocean_drop)

    with pytest.raises(RuntimeError, match="non-volatile"):
        validate_sales_truth_ocean_drop_parity(
            db_path=db,
            as_of=date(2026, 2, 26),
            ocean_drop_path=ocean_drop,
            output_root=tmp_path / "out",
            volatility_days=0,
            strict=True,
            crm_archive_lookup_path=None,
        )


def test_window_days_mode_detects_db_extra_days_without_reference_rows(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    ocean_drop = tmp_path / "ocean_drop.csv"

    _seed_db(db, rev_ord_1=1200.0)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code, quantity, sell_price_kzt,
         delivery_fee, cogs, net_rev, profit, status, return_flag, return_date, source_file, api_updated_at)
        VALUES ('ORD-EXTRA', '2026-02-26', 'SKU_X', 'SKU_X_M', 'M', 'Offer X', 'ACMEWEAR', 1, 500, 0, NULL, 500, NULL, 'DELIVERED', 0, NULL, 'seed', NULL)
        """
    )
    conn.commit()
    conn.close()
    _write_ocean_drop(ocean_drop)

    with pytest.raises(RuntimeError, match="non-volatile"):
        validate_sales_truth_ocean_drop_parity(
            db_path=db,
            as_of=date(2026, 2, 26),
            ocean_drop_path=ocean_drop,
            output_root=tmp_path / "out",
            volatility_days=0,
            strict=True,
            crm_archive_lookup_path=None,
            window_days=2,
        )


def test_window_days_mode_can_pass_no_overlap_when_enabled(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    ocean_drop = tmp_path / "ocean_drop.csv"
    output_root = tmp_path / "out"

    _seed_db(db, rev_ord_1=1200.0)
    _write_ocean_drop(ocean_drop)

    report = validate_sales_truth_ocean_drop_parity(
        db_path=db,
        as_of=date(2026, 3, 19),
        ocean_drop_path=ocean_drop,
        output_root=output_root,
        volatility_days=14,
        strict=True,
        crm_archive_lookup_path=None,
        window_days=14,
        allow_no_overlap=True,
    )

    assert report["status"] == "PASS_NO_OVERLAP"
    assert report["reference_window_overlap"] is False
    assert report["daily_rows"] == []
