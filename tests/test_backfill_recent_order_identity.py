from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts.backfill_recent_order_identity import backfill_recent_order_identity
from scripts.identity_stabilization_common import StatusError


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                kaspi_offer_name TEXT,
                size_source TEXT,
                size_confidence TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                product_id TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_reference_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "store_code": "UNIVERSAL",
                "sku_id_ksp": "SKU_A",
                "kaspi_offer_name": "Offer A",
                "effective_sku_key": "SKU_A",
                "effective_size": "XL",
                "mapping_status": "matched",
                "identity_status": "matched",
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def _write_crm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "OrderID": "1",
                "STORE_NAME": "30000001_PP1",
                "SKU_key": "CRM_SKU",
                "SKU_ID": "CRM_SKU",
                "MY_SIZE": "L",
                "KASPI_OFFER_NAME": "Offer A",
            }
        ]
    ).to_excel(path, sheet_name="SALES_KSP_CRM_1", index=False)


def test_backfill_recent_order_identity_dry_run_produces_diff(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "UNIVERSAL", "", "", "", "Offer A", "", "", "2026-03-04 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    reference_csv = tmp_path / "reference.csv"
    crm_path = tmp_path / "crm.xlsx"
    _write_reference_csv(reference_csv)
    _write_crm(crm_path)

    report = backfill_recent_order_identity(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=15,
        stores=("UNIVERSAL",),
        reference_csv=reference_csv,
        crm_workbook=crm_path,
        output_root=tmp_path / "out",
        strict=True,
        apply=False,
        backup_root=tmp_path / "backups",
    )
    assert report["status"] == "PASS"
    assert report["updated_rows"] == 1
    assert (tmp_path / "out" / "2026-03-04" / "backfill_recent_order_identity_diff_fact_orders_kaspi.csv").exists()


def test_backfill_recent_order_identity_apply_requires_env_gate(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "UNIVERSAL", "", "", "", "Offer A", "", "", "2026-03-04 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    reference_csv = tmp_path / "reference.csv"
    crm_path = tmp_path / "crm.xlsx"
    _write_reference_csv(reference_csv)
    _write_crm(crm_path)

    with pytest.raises(StatusError, match="IDENTITY_COVERAGE_FAIL"):
        backfill_recent_order_identity(
            db_path=db,
            as_of=date(2026, 3, 4),
            lookback_days=15,
            stores=("UNIVERSAL",),
            reference_csv=reference_csv,
            crm_workbook=crm_path,
            output_root=tmp_path / "out",
            strict=False,
            apply=True,
            backup_root=tmp_path / "backups",
        )


def test_backfill_recent_order_identity_uses_unique_product_mapping(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        # Historical mapped order creates deterministic product_id -> sku_key mapping.
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("hist-1", "UNIVERSAL", "SKU_FROM_PRODUCT", "SKU_FROM_PRODUCT", "XL", "Hist Offer", "seed", "1.0", "2026-02-25 10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, product_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("e-hist-1", "hist-1", "UNIVERSAL", "P-123", "2026-02-25 10:00:00"),
        )
        # Recent unresolved order with same product_id.
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2", "UNIVERSAL", "", "", "", "", "", "", "2026-03-04 10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi
            (entry_id, order_id, store_code, product_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("e-1", "2", "UNIVERSAL", "P-123", "2026-03-04 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    reference_csv = tmp_path / "reference.csv"
    crm_path = tmp_path / "crm.xlsx"
    _write_reference_csv(reference_csv)
    _write_crm(crm_path)

    report = backfill_recent_order_identity(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=15,
        stores=("UNIVERSAL",),
        reference_csv=reference_csv,
        crm_workbook=crm_path,
        output_root=tmp_path / "out",
        strict=True,
        apply=False,
        backup_root=tmp_path / "backups",
    )
    assert report["status"] == "PASS"
    assert report["updated_rows"] == 1
    diff = pd.read_csv(tmp_path / "out" / "2026-03-04" / "backfill_recent_order_identity_diff_fact_orders_kaspi.csv", dtype=str, keep_default_na=False)
    row = diff.loc[diff["order_id"] == "2"].iloc[0]
    assert row["after_sku_key"] == "SKU_FROM_PRODUCT"
    assert row["after_my_size"] == "XL"
    assert row["source"] == "ORDER_ENTRY_PRODUCT_ID_UNIQUE"


def test_backfill_recent_order_identity_derives_size_from_offer_text(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "UNIVERSAL", "SKU_A", "SKU_A", "", "Комплект тренировочный черный 2XL", "", "", "2026-03-04 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    # Candidate from CRM has sku_key but no size; parser should fill my_size from offer text.
    reference_csv = tmp_path / "reference.csv"
    crm_path = tmp_path / "crm.xlsx"
    _write_reference_csv(reference_csv)
    crm_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "OrderID": "1",
                "STORE_NAME": "30000001_PP1",
                "SKU_key": "SKU_A",
                "SKU_ID": "SKU_A",
                "MY_SIZE": "",
                "KASPI_OFFER_NAME": "Комплект тренировочный черный 2XL",
            }
        ]
    ).to_excel(crm_path, sheet_name="SALES_KSP_CRM_1", index=False)

    report = backfill_recent_order_identity(
        db_path=db,
        as_of=date(2026, 3, 4),
        lookback_days=15,
        stores=("UNIVERSAL",),
        reference_csv=reference_csv,
        crm_workbook=crm_path,
        output_root=tmp_path / "out",
        strict=True,
        apply=False,
        backup_root=tmp_path / "backups",
    )
    assert report["status"] == "PASS"
    diff = pd.read_csv(tmp_path / "out" / "2026-03-04" / "backfill_recent_order_identity_diff_fact_orders_kaspi.csv", dtype=str, keep_default_na=False)
    row = diff.loc[diff["order_id"] == "1"].iloc[0]
    assert row["after_my_size"] == "2XL"
    assert "my_size" in row["changed_fields"].split(",")


def test_backfill_recent_order_identity_does_not_guess_ambiguous_numeric_sizes(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name, size_source, size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "UNIVERSAL", "SKU_A", "SKU_A", "", "Комплект Antec Рашгард 5 в 1 черный 50, 52", "", "", "2026-03-04 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    reference_csv = tmp_path / "reference.csv"
    crm_path = tmp_path / "crm.xlsx"
    _write_reference_csv(reference_csv)
    crm_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "OrderID": "1",
                "STORE_NAME": "30000001_PP1",
                "SKU_key": "SKU_A",
                "SKU_ID": "SKU_A",
                "MY_SIZE": "",
                "KASPI_OFFER_NAME": "Комплект Antec Рашгард 5 в 1 черный 50, 52",
            }
        ]
    ).to_excel(crm_path, sheet_name="SALES_KSP_CRM_1", index=False)

    with pytest.raises(StatusError, match="IDENTITY_COVERAGE_FAIL"):
        backfill_recent_order_identity(
            db_path=db,
            as_of=date(2026, 3, 4),
            lookback_days=15,
            stores=("UNIVERSAL",),
            reference_csv=reference_csv,
            crm_workbook=crm_path,
            output_root=tmp_path / "out",
            strict=True,
            apply=False,
            backup_root=tmp_path / "backups",
        )
