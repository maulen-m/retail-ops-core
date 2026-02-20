from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.validate_offer_stock_sync import validate_offer_stock_sync


def _setup_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_offer_stock_mapper_current (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            store_code TEXT NOT NULL,
            merchant_uid TEXT,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            mapping_method TEXT NOT NULL,
            mapping_confidence TEXT NOT NULL,
            is_ambiguous INTEGER NOT NULL DEFAULT 0,
            source_updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_offer_stock_mapper_current (
            generated_at, store_code, merchant_uid, kaspi_article, kaspi_offer_name,
            sku_id, sku_key, my_size, mapping_method, mapping_confidence, is_ambiguous, source_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-02-18T13:00:00+00:00",
            "UNIVERSAL",
            "30000001",
            "SKU_A_S_1001",
            "Offer A",
            "SKU_A_S",
            "SKU_A",
            "S",
            "article_map_sku_id",
            "HIGH",
            0,
            "2026-02-18T12:55:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO fact_offer_stock_mapper_current (
            generated_at, store_code, merchant_uid, kaspi_article, kaspi_offer_name,
            sku_id, sku_key, my_size, mapping_method, mapping_confidence, is_ambiguous, source_updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-02-18T13:00:00+00:00",
            "UNIVERSAL",
            "30000001",
            "SKU_B_L_2002",
            "Offer B",
            None,
            "SKU_B",
            None,
            "unresolved",
            "LOW",
            1,
            "2026-02-18T12:55:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("2026-02-18", "SKU_A_S", "SKU_A", "S", 5, 0),
    )
    conn.commit()
    conn.close()


def test_validate_offer_stock_sync_fails_when_unresolved_exceeds_threshold(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)

    report = validate_offer_stock_sync(
        db_path=db_path,
        stores=["UNIVERSAL"],
        table_name="fact_offer_stock_mapper_current",
        max_unresolved=0,
        min_confident_rate=0.95,
        require_snapshot_coverage=True,
    )

    assert report["ok"] is False
    assert any("unresolved_rows=1" in err for err in report["errors"])


def test_validate_offer_stock_sync_passes_with_relaxed_thresholds(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)

    report = validate_offer_stock_sync(
        db_path=db_path,
        stores=["UNIVERSAL"],
        table_name="fact_offer_stock_mapper_current",
        max_unresolved=1,
        min_confident_rate=0.50,
        require_snapshot_coverage=True,
    )

    assert report["ok"] is True
    metric = report["metrics_by_store"]["UNIVERSAL"]
    assert metric["total_rows"] == 2
    assert metric["confident_rows"] == 1
    assert metric["missing_snapshot_rows"] == 0
