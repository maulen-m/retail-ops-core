from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

from scripts.migrate_032_drop_mutable_sales_unique_constraints import run


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL,
                source_entry_id TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT,
                UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
            );
            CREATE UNIQUE INDEX ux_sales_fact_v2_source_entry_id
              ON sales_fact_v2(source_entry_id) WHERE source_entry_id IS NOT NULL;
            CREATE UNIQUE INDEX ux_sales_fact_v2_order_store_article_fallback
              ON sales_fact_v2(order_id, store_code, kaspi_article)
              WHERE source_entry_id IS NULL AND kaspi_article IS NOT NULL;
            CREATE UNIQUE INDEX ux_sales_fact_v2_order_store_line_identity
              ON sales_fact_v2(order_id, store_code, line_identity_key)
              WHERE line_identity_key IS NOT NULL;

            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                source_entry_id TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT,
                UNIQUE(order_id, kaspi_offer_name, sku_id, store_code)
            );
            CREATE UNIQUE INDEX ux_fact_sales_source_entry_id
              ON fact_sales(source_entry_id) WHERE source_entry_id IS NOT NULL;
            CREATE UNIQUE INDEX ux_fact_sales_order_store_article_fallback
              ON fact_sales(order_id, store_code, kaspi_article)
              WHERE source_entry_id IS NULL AND kaspi_article IS NOT NULL;
            CREATE UNIQUE INDEX ux_fact_sales_order_store_line_identity
              ON fact_sales(order_id, store_code, line_identity_key)
              WHERE line_identity_key IS NOT NULL;
            """
        )
        conn.execute(
            "INSERT INTO sales_fact_v2 "
            "(order_id,sku_id,store_code,kaspi_offer_name,source_entry_id,kaspi_article,line_identity_key) "
            "VALUES ('O1','SKU-M','S','Display','E1','A1','ENTRY:E1')"
        )
        conn.execute(
            "INSERT INTO fact_sales "
            "(order_id,kaspi_offer_name,sku_id,store_code,source_entry_id,kaspi_article,line_identity_key) "
            "VALUES ('O1','Display','SKU-M','S','E1','A1','ENTRY:E1')"
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_preserves_rows_and_allows_distinct_entries_with_same_mutable_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db = tmp_path / "app.db"
    _create_db(db)
    pre = _sha256(db)
    dry = run(
        db_path=db,
        apply=False,
        expected_pre_sha256=None,
        backup_dir=None,
    )
    assert dry["migration_required_tables"] == ["sales_fact_v2", "fact_sales"]

    monkeypatch.setenv("ENABLE_SCHEMA_WRITE", "1")
    monkeypatch.setenv("ENABLE_SALES_PUBLIC_LINE_SCHEMA_REBUILD", "1")
    report = run(
        db_path=db,
        apply=True,
        expected_pre_sha256=pre,
        backup_dir=tmp_path / "backups",
    )
    assert report["mode"] == "applied"
    assert report["integrity_check"] == "ok"

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO sales_fact_v2 "
            "(order_id,sku_id,store_code,kaspi_offer_name,source_entry_id,kaspi_article,line_identity_key) "
            "VALUES ('O1','SKU-M','S','Display','E2','A1','ENTRY:E2')"
        )
        conn.execute(
            "INSERT INTO fact_sales "
            "(order_id,kaspi_offer_name,sku_id,store_code,source_entry_id,kaspi_article,line_identity_key) "
            "VALUES ('O1','Display','SKU-M','S','E2','A1','ENTRY:E2')"
        )
        assert conn.execute("SELECT COUNT(*) FROM sales_fact_v2").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0] == 2
    finally:
        conn.close()

    noop = run(
        db_path=db,
        apply=False,
        expected_pre_sha256=None,
        backup_dir=None,
    )
    assert noop["mode"] == "already_migrated_noop"
