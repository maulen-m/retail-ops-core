import sqlite3
from pathlib import Path

from openpyxl import Workbook

import scripts.rebuild_kaspi_identity_map_from_crm as rebuild_mod
from core.db import get_db
from scripts.rebuild_kaspi_identity_map_from_crm import (
    build_core_majority_map,
    choose_best_identity,
    rebuild_identity_map,
)


def test_choose_best_identity_forces_line61():
    rows = [
        {
            "kaspi_article": "OF_SUIT-61_BLK_XL_48",
            "sku_key": "CL_OC_MEN_LINE51_WHITE",
            "kaspi_name_core": "Wrong",
            "weight": 1,
        }
    ]
    chosen = choose_best_identity("OF_SUIT-61_BLK_XL_48", rows)
    assert chosen["sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert chosen["kaspi_name_core"] == "6в1_Черный_+Сумка"


def test_choose_best_identity_prefers_majority_sku_key():
    rows = [
        {"kaspi_article": "ART-1", "sku_key": "A", "kaspi_name_core": "CoreA", "weight": 3},
        {"kaspi_article": "ART-1", "sku_key": "A", "kaspi_name_core": "CoreA", "weight": 1},
        {"kaspi_article": "ART-1", "sku_key": "B", "kaspi_name_core": "CoreB", "weight": 1},
    ]
    chosen = choose_best_identity("ART-1", rows)
    assert chosen["sku_key"] == "A"
    assert chosen["kaspi_name_core"] == "CoreA"


def test_build_core_majority_map_prefers_dominant_sku_per_store_core():
    rows = [
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE52_BLACK"},
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE52_BLACK"},
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE51_WHITE"},
    ]
    out = build_core_majority_map(rows)
    assert out[("ACMEWEAR", "Принт_5в1_черный")] == "CL_OC_MEN_LINE52_BLACK"


def test_rebuild_identity_map_persists_offer_name_from_crm_history(
    tmp_path: Path,
    monkeypatch,
):
    workbook = tmp_path / "crm.xlsx"
    db_path = tmp_path / "app.db"

    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Артикул", "Название товара в Kaspi Магазине", "SKU_key", "Kaspi_name_core", "STORE_NAME"])
    ws.append(
        [
            "OF_SUIT-61_BLK_2XL",
            "Комплект ACMEWEAR OF_SUIT-61_BLK_2XL",
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
            "6в1_Черный_+Сумка",
            "AcmeWear",
        ]
    )
    wb.save(workbook)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE dim_store (store_code TEXT PRIMARY KEY);
        CREATE TABLE dim_sku (sku_key TEXT PRIMARY KEY);
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            sku_key TEXT,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO dim_store(store_code) VALUES ('ACMEWEAR');
        INSERT INTO dim_sku(sku_key) VALUES ('CL_NEW-CLO2_MEN_SUIT-61_BLACK');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(rebuild_mod, "get_db", lambda db_path_override=None: get_db(db_path))
    monkeypatch.setenv("ENABLE_KASPI_WORKBOOK_MAP_SYNC", "1")

    stats = rebuild_identity_map(
        workbook=workbook,
        sheet="SALES_KSP_CRM_1",
        dry_run=False,
        db_path=db_path,
        as_of=rebuild_mod.date(2026, 4, 16),
        output_root=tmp_path / "reports",
        backup_root=tmp_path / "backups",
    )

    assert stats["inserted"] == 1
    assert stats["status"] == "APPLIED"
    assert Path(stats["backup_path"]).exists()
    assert Path(stats["report_json"]).exists()
    assert Path(stats["report_md"]).exists()
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT store_code, kaspi_article, kaspi_offer_name, kaspi_name_core, sku_key, source
        FROM dim_kaspi_article_map
        """
    ).fetchone()
    conn.close()

    assert row == (
        "ACMEWEAR",
        "OF_SUIT-61_BLK_2XL",
        "Комплект ACMEWEAR OF_SUIT-61_BLK_2XL",
        "6в1_Черный_+Сумка",
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
        "crm_historical_patch",
    )


def test_rebuild_identity_map_apply_requires_env_gate(tmp_path: Path):
    workbook = tmp_path / "crm.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Артикул", "SKU_key"])
    ws.append(["ART-1", "SKU-1"])
    wb.save(workbook)

    with rebuild_mod.get_db(tmp_path / "app.db") as conn:
        conn.executescript(
            """
            CREATE TABLE dim_store (store_code TEXT PRIMARY KEY);
            CREATE TABLE dim_sku (sku_key TEXT PRIMARY KEY);
            CREATE TABLE dim_kaspi_article_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                kaspi_article TEXT NOT NULL,
                kaspi_offer_name TEXT,
                kaspi_name_core TEXT,
                sku_key TEXT,
                source TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO dim_sku(sku_key) VALUES ('SKU-1');
            """
        )

    import os

    os.environ.pop("ENABLE_KASPI_WORKBOOK_MAP_SYNC", None)

    try:
        rebuild_identity_map(workbook=workbook, sheet="SALES_KSP_CRM_1", dry_run=False, db_path=tmp_path / "app.db")
    except RuntimeError as exc:
        assert "ENABLE_KASPI_WORKBOOK_MAP_SYNC=1" in str(exc)
    else:
        raise AssertionError("expected env-gate RuntimeError")
