from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from core.utils.kaspi_name_core_resolver import load_active_kaspi_name_core_maps, resolve_kaspi_name_core
from scripts.ingest_acmewear_child_bundle_ab_mapping import (
    APPLY_ENV,
    IngestError,
    run_ingest,
    validate_mapping_coverage,
)


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE dim_store (
                store_code TEXT PRIMARY KEY
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                color TEXT,
                product_type TEXT NOT NULL,
                base_cost_cny REAL NOT NULL DEFAULT 0,
                weight_kg REAL NOT NULL DEFAULT 0,
                category TEXT,
                gender TEXT,
                active_flag INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                size_order INTEGER,
                active_flag INTEGER DEFAULT 1
            );
            CREATE TABLE dim_kaspi_article_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                merchant_id TEXT,
                kaspi_article TEXT NOT NULL,
                kaspi_offer_name TEXT,
                kaspi_name_core TEXT,
                sku_key TEXT,
                sku_id TEXT,
                model TEXT,
                brand TEXT,
                source TEXT,
                active_flag INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(store_code, kaspi_article)
            );
            INSERT INTO dim_store(store_code) VALUES ('ACMEWEAR');
            INSERT INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg, category, gender, active_flag
            ) VALUES (
                'SUIT-31-TS', 'SUIT-31-TS', 'BLACK', 'CL', 0, 0, 'BUNDLE', 'MEN', 1
            );
            INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order, active_flag)
            VALUES ('SUIT-31-TS_3XL', 'SUIT-31-TS', '3XL', 6, 1);
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, kaspi_name_core,
                sku_key, sku_id, model, brand, source, active_flag
            ) VALUES (
                'ACMEWEAR', 'SUIT-31-TS-ST-3XL-54', 'SUIT-31-TS-ST-3XL-54',
                'SUIT-31-TS-ST', 'SUIT-31-TS', 'SUIT-31-TS_3XL',
                'SUIT-31-TS', 'ACMEWEAR', 'OLD_STAGE2', 1
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_mapping_csv(path: Path) -> None:
    headers = [
        "store",
        "store_code",
        "card_group",
        "bundle_code",
        "parent_family",
        "parent_sku_key",
        "ab_sku_key_proposed",
        "merchant_article",
        "internal_size",
        "platform_token",
        "current_sale_state_after_20260503_stock_update",
        "kaspi_name_core_required",
        "kaspi_name_core_source",
        "generic_fallback_to_avoid",
    ]
    rows = [
        {
            "store": "ACMEWEAR",
            "store_code": "30137883",
            "card_group": "LINE61|SUIT-31-TS|ST",
            "bundle_code": "SUIT-31-TS",
            "parent_family": "LINE61",
            "parent_sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
            "ab_sku_key_proposed": "CL_NEW-CLO2_MEN_SUIT-31_TS_BLACK",
            "merchant_article": "SUIT-31-TS-ST-3XL-54",
            "internal_size": "3XL",
            "platform_token": "3XL-54",
            "current_sale_state_after_20260503_stock_update": "active_sale_pp1_500",
            "kaspi_name_core_required": "3в1_Черный_Футболка_+Сумка",
            "kaspi_name_core_source": "owner_explicit",
            "generic_fallback_to_avoid": "Спортивный_костюм_ACMEWEAR",
        },
        {
            "store": "ACMEWEAR",
            "store_code": "30137883",
            "card_group": "LINE51|LINE-31-LS|ST",
            "bundle_code": "LINE-31-LS",
            "parent_family": "LINE51",
            "parent_sku_key": "CL_OC_MEN_LINE51_WHITE",
            "ab_sku_key_proposed": "CL_NEW-CLO_MEN_LINE-31_LS_WHITE",
            "merchant_article": "LINE-31-LS-ST-4XL-58",
            "internal_size": "4XL",
            "platform_token": "4XL-58",
            "current_sale_state_after_20260503_stock_update": "archive_out_of_stock_platform_56_58_60",
            "kaspi_name_core_required": "3в1_БЕЛИ_Лонгслив_+Сумка",
            "kaspi_name_core_source": "owner_explicit",
            "generic_fallback_to_avoid": "Спортивный_костюм_ACMEWEAR",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_ingest_requires_apply_gate_before_db_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    csv_path = tmp_path / "mapping.csv"
    _seed_db(db_path)
    _write_mapping_csv(csv_path)
    monkeypatch.delenv(APPLY_ENV, raising=False)

    with pytest.raises(IngestError, match=APPLY_ENV):
        run_ingest(
            db_path=db_path,
            mapping_csv=csv_path,
            backup_root=tmp_path / "backups",
            output_root=tmp_path / "reports",
            apply=True,
            expected_rows=2,
        )


def test_ingest_updates_child_bundle_core_and_resolver_uses_required_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    csv_path = tmp_path / "mapping.csv"
    _seed_db(db_path)
    _write_mapping_csv(csv_path)

    dry_report = run_ingest(
        db_path=db_path,
        mapping_csv=csv_path,
        backup_root=tmp_path / "backups",
        output_root=tmp_path / "reports",
        apply=False,
        expected_rows=2,
    )
    assert dry_report["status"] == "DRY_RUN"
    assert dry_report["changes"]["to_update"] == 1
    assert dry_report["changes"]["to_insert"] == 1

    monkeypatch.setenv(APPLY_ENV, "1")
    report = run_ingest(
        db_path=db_path,
        mapping_csv=csv_path,
        backup_root=tmp_path / "backups",
        output_root=tmp_path / "reports",
        apply=True,
        expected_rows=2,
    )

    assert report["status"] == "APPLIED"
    assert Path(report["backup_path"]).exists()
    assert report["after"]["coverage"]["expected_rows"] == 2
    assert report["after"]["coverage"]["resolved_rows"] == 2
    assert report["after"]["coverage"]["generic_fallback_rows"] == 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT kaspi_name_core, sku_key, sku_id, active_flag
            FROM dim_kaspi_article_map
            WHERE store_code='ACMEWEAR' AND kaspi_article='SUIT-31-TS-ST-3XL-54'
            """
        ).fetchone()
        assert dict(row) == {
            "kaspi_name_core": "3в1_Черный_Футболка_+Сумка",
            "sku_key": "SUIT-31-TS",
            "sku_id": "SUIT-31-TS_3XL",
            "active_flag": 1,
        }

        archived = conn.execute(
            """
            SELECT kaspi_name_core, sku_key, sku_id, active_flag
            FROM dim_kaspi_article_map
            WHERE store_code='ACMEWEAR' AND kaspi_article='LINE-31-LS-ST-4XL-58'
            """
        ).fetchone()
        assert dict(archived) == {
            "kaspi_name_core": "3в1_БЕЛИ_Лонгслив_+Сумка",
            "sku_key": "LINE-31-LS",
            "sku_id": "LINE-31-LS_4XL",
            "active_flag": 1,
        }

        maps = load_active_kaspi_name_core_maps(conn, sku_keys={"SUIT-31-TS"})
        resolution = resolve_kaspi_name_core(
            store_code="ACMEWEAR",
            kaspi_offer_name="Спортивный костюм ACMEWEAR SUIT-31-TS-ST-3XL-54 черный 3XL",
            sku_key="SUIT-31-TS",
            maps=maps,
        )
    finally:
        conn.close()

    assert resolution.core == "3в1_Черный_Футболка_+Сумка"
    assert resolution.source == "sku_key"
    assert resolution.safe


def test_validate_mapping_coverage_blocks_unresolved_child_bundle_core(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    csv_path = tmp_path / "mapping.csv"
    _seed_db(db_path)
    _write_mapping_csv(csv_path)

    coverage = validate_mapping_coverage(
        db_path=db_path,
        mapping_csv=csv_path,
        expected_rows=2,
    )

    assert coverage["ok"] is False
    assert coverage["expected_rows"] == 2
    assert coverage["resolved_rows"] == 0
    assert coverage["missing_rows"] == 1
    assert coverage["mismatched_core_rows"] == 1
    assert coverage["technical_core_rows"] == 1
