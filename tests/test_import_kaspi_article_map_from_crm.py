from __future__ import annotations

from pathlib import Path
import sqlite3

from openpyxl import Workbook

from scripts.import_kaspi_article_map_from_crm import import_map


def _create_workbook(path: Path, rows: list[dict[str, object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "M02_SKU_CATALOG_NC"
    headers = [
        "Store_name",
        "SKU_ID",
        "SKU_ID_KSP",
        "Kaspi_name_core",
        "MY_SIZE",
        "Size_kaspi",
        "SKU_key",
        "Kaspi_offer_name",
        "Model",
        "Brand",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h) for h in headers])
    wb.save(path)


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE dim_store (
            store_code TEXT PRIMARY KEY
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT
        );
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL REFERENCES dim_store(store_code),
            merchant_id TEXT,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            sku_key TEXT REFERENCES dim_sku(sku_key),
            sku_id TEXT REFERENCES dim_sku_size(sku_id),
            model TEXT,
            brand TEXT,
            source TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(store_code, kaspi_article)
        );
        INSERT INTO dim_store(store_code) VALUES ('ACMEWEAR'), ('STOREB');
        INSERT INTO dim_sku(sku_key) VALUES ('CL_OC_MEN_LINE51_WHITE');
        INSERT INTO dim_sku_size(sku_id, sku_key, my_size) VALUES
            ('CL_OC_MEN_LINE51_WHITE_XL', 'CL_OC_MEN_LINE51_WHITE', 'XL');
        """
    )


def test_import_map_seeds_workbook_catalog_for_all_stores(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    conn = sqlite3.connect(db_path)
    _seed_schema(conn)
    conn.commit()
    conn.close()

    _create_workbook(
        workbook,
        [
            {
                "Store_name": "ACMEWEAR",
                "SKU_ID": "CL_OC_MEN_LINE51_WHITE_XL",
                "SKU_ID_KSP": "CL_OC_MEN_LINE51_WHITE_134547486_48_(XL)",
                "Kaspi_name_core": "Line51",
                "MY_SIZE": "XL",
                "Size_kaspi": "48",
                "SKU_key": "CL_OC_MEN_LINE51_WHITE",
                "Kaspi_offer_name": None,
                "Model": "Line51",
                "Brand": "AcmeWear",
            }
        ],
    )

    monkeypatch.setattr(
        "scripts.import_kaspi_article_map_from_crm._load_store_catalog",
        lambda: {
            "ACMEWEAR": {"merchant_id": "m-acmewear"},
            "STOREB": {"merchant_id": "m-storeb"},
        },
    )
    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")

    report = import_map(
        db_path=db_path,
        workbook=workbook,
        sheet="M02_SKU_CATALOG_NC",
        store_filter=None,
        apply_changes=True,
    )

    assert report["inserted"] == 2
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT store_code, merchant_id, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, sku_id, source
        FROM dim_kaspi_article_map
        ORDER BY store_code
        """
    ).fetchall()
    conn.close()

    assert rows == [
        (
            "STOREB",
            "m-storeb",
            "CL_OC_MEN_LINE51_WHITE_134547486_48_(XL)",
            None,
            "Line51",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_XL",
            "CRM:M02_SKU_CATALOG_NC",
        ),
        (
            "ACMEWEAR",
            "m-acmewear",
            "CL_OC_MEN_LINE51_WHITE_134547486_48_(XL)",
            None,
            "Line51",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_XL",
            "CRM:M02_SKU_CATALOG_NC",
        ),
    ]


def test_import_map_uses_sheet_sku_key_and_builds_missing_size_rows(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    conn = sqlite3.connect(db_path)
    _seed_schema(conn)
    conn.commit()
    conn.close()

    _create_workbook(
        workbook,
        [
            {
                "Store_name": None,
                "SKU_ID": "IGNORED_SHEET_SIZE_ID",
                "SKU_ID_KSP": "CL_OC_MEN_LINE51_WHITE_134547486_56_(4XL)",
                "Kaspi_name_core": "Line51",
                "MY_SIZE": "4XL",
                "Size_kaspi": "56",
                "SKU_key": "CL_OC_MEN_LINE51_WHITE",
                "Kaspi_offer_name": "Workbook Offer Name",
                "Model": "Line51",
                "Brand": "AcmeWear",
            }
        ],
    )

    monkeypatch.setattr(
        "scripts.import_kaspi_article_map_from_crm._load_store_catalog",
        lambda: {"ACMEWEAR": {"merchant_id": "m-acmewear"}},
    )
    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")

    report = import_map(
        db_path=db_path,
        workbook=workbook,
        sheet="M02_SKU_CATALOG_NC",
        store_filter=None,
        apply_changes=True,
    )

    assert report["inserted"] == 1
    assert report["missing_sku_key"] == 0
    assert report["missing_sku_id"] == 0

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT kaspi_article, kaspi_offer_name, sku_key, sku_id
        FROM dim_kaspi_article_map
        WHERE store_code='ACMEWEAR'
        """
    ).fetchone()
    size_row = conn.execute(
        "SELECT sku_id, sku_key, my_size FROM dim_sku_size WHERE sku_id='CL_OC_MEN_LINE51_WHITE_4XL'"
    ).fetchone()
    conn.close()

    assert row == (
        "CL_OC_MEN_LINE51_WHITE_134547486_56_(4XL)",
        "Workbook Offer Name",
        "CL_OC_MEN_LINE51_WHITE",
        "CL_OC_MEN_LINE51_WHITE_4XL",
    )
    assert size_row == ("CL_OC_MEN_LINE51_WHITE_4XL", "CL_OC_MEN_LINE51_WHITE", "4XL")


def test_import_map_ignores_placeholder_offer_values(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    conn = sqlite3.connect(db_path)
    _seed_schema(conn)
    conn.commit()
    conn.close()

    _create_workbook(
        workbook,
        [
            {
                "Store_name": "ACMEWEAR",
                "SKU_ID": "CL_OC_MEN_LINE51_WHITE_XL",
                "SKU_ID_KSP": "CL_OC_MEN_LINE51_WHITE_134547486_48_(XL)",
                "Kaspi_name_core": "Line51",
                "MY_SIZE": "XL",
                "Size_kaspi": "48",
                "SKU_key": "CL_OC_MEN_LINE51_WHITE",
                "Kaspi_offer_name": "YES",
                "Model": "Line51",
                "Brand": "AcmeWear",
            }
        ],
    )

    monkeypatch.setattr(
        "scripts.import_kaspi_article_map_from_crm._load_store_catalog",
        lambda: {"ACMEWEAR": {"merchant_id": "m-acmewear"}},
    )
    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")

    report = import_map(
        db_path=db_path,
        workbook=workbook,
        sheet="M02_SKU_CATALOG_NC",
        store_filter=None,
        apply_changes=True,
    )

    assert report["inserted"] == 1
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT kaspi_offer_name, kaspi_name_core
        FROM dim_kaspi_article_map
        WHERE store_code='ACMEWEAR'
        """
    ).fetchone()
    conn.close()

    assert row == (None, "Line51")
