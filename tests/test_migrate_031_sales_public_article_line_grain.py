from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts.migrate_031_sales_public_article_line_grain import (
    ARTICLE_INDEXES,
    ENTRY_INDEXES,
    LINE_INDEXES,
    migrate,
    validate_public_article_line_grain,
)


def _create_legacy_schema(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_id TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT
            );
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                kaspi_offer_name TEXT
            );
            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                kaspi_offer_name TEXT
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY,
                reference_id TEXT,
                store_code TEXT,
                sku_id TEXT,
                qty_change INTEGER
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_adds_columns_indexes_and_normalizes_proven_key(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_legacy_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO fact_orders_kaspi "
            "(id, order_id, store_code, sku_id, kaspi_article, line_identity_key) "
            "VALUES (1, 'O-1', 'universal', 'SKU-M', ' article-m ', 'old-key')"
        )

    assert validate_public_article_line_grain(db_path)
    migrate(db_path)
    assert validate_public_article_line_grain(db_path) == []

    with sqlite3.connect(db_path) as conn:
        for table in ("sales_fact_v2", "fact_sales", "stock_ledger"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert {"kaspi_article", "line_identity_key"}.issubset(columns)
        assert conn.execute(
            "SELECT line_identity_key FROM fact_orders_kaspi WHERE id=1"
        ).fetchone()[0] == "ARTICLE:ARTICLE-M"
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        assert set(ARTICLE_INDEXES.values()).issubset(indexes)
        assert set(ENTRY_INDEXES.values()).issubset(indexes)
        assert set(LINE_INDEXES.values()).issubset(indexes)
        assert "idx_stock_ledger_order_line_identity" in indexes
        assert "ux_stock_ledger_supersedes_ledger_id" in indexes
        identity_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(stock_ledger_source_identity)"
            ).fetchall()
        }
        assert {
            "ledger_id",
            "source_entry_id",
            "source_store_code",
            "kaspi_article",
            "line_identity_key",
            "repair_batch_id",
        }.issubset(identity_columns)


def test_unique_article_grain_ignores_size_but_allows_blank_legacy_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _create_legacy_schema(db_path)
    migrate(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sales_fact_v2 "
            "(sale_id, order_id, store_code, sku_id, kaspi_offer_name, "
            "kaspi_article, line_identity_key) "
            "VALUES (1, 'O-1', 'UNIVERSAL', 'SKU-M', 'Shared', "
            "'article-1', 'ARTICLE:ARTICLE-1')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sales_fact_v2 "
                "(sale_id, order_id, store_code, sku_id, kaspi_offer_name, "
                "kaspi_article, line_identity_key) "
                "VALUES (2, 'O-1', 'universal', 'SKU-L', 'Shared', "
                "' ARTICLE-1 ', 'ARTICLE:ARTICLE-1')"
            )
        conn.execute(
            "INSERT INTO sales_fact_v2 "
            "(sale_id, order_id, store_code, sku_id, kaspi_offer_name) "
            "VALUES (3, 'LEGACY', 'UNIVERSAL', 'SKU-M', 'Shared')"
        )
        conn.execute(
            "INSERT INTO sales_fact_v2 "
            "(sale_id, order_id, store_code, sku_id, kaspi_offer_name) "
            "VALUES (4, 'LEGACY', 'UNIVERSAL', 'SKU-L', 'Shared')"
        )


def test_migration_fails_before_index_on_existing_article_duplicate(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _create_legacy_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE sales_fact_v2 ADD COLUMN kaspi_article TEXT")
        conn.execute("ALTER TABLE sales_fact_v2 ADD COLUMN line_identity_key TEXT")
        conn.executemany(
            "INSERT INTO sales_fact_v2 "
            "(sale_id, order_id, store_code, sku_id, kaspi_offer_name, "
            "kaspi_article, line_identity_key) VALUES (?, 'O-1', ?, ?, 'Shared', ?, ?)",
            [
                (1, "UNIVERSAL", "SKU-M", "ARTICLE-1", "ARTICLE:ARTICLE-1"),
                (2, "universal", "SKU-L", " article-1 ", "ARTICLE:ARTICLE-1"),
            ],
        )

    with pytest.raises(RuntimeError, match="duplicate public-article lines"):
        migrate(db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sales_fact_v2"
        ).fetchone()[0] == 2
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='ux_sales_fact_v2_order_store_article_fallback'"
        ).fetchone() is None


def test_distinct_source_entries_may_share_article(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_legacy_schema(db_path)
    migrate(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO sales_fact_v2 "
            "(sale_id, order_id, store_code, sku_id, kaspi_offer_name, "
            "source_entry_id, kaspi_article, line_identity_key) "
            "VALUES (?, 'O-SHARED', 'UNIVERSAL', ?, 'Shared', ?, 'ARTICLE-1', ?)",
            [
                (1, "SKU-M", "ENTRY-1", "ENTRY:ENTRY-1"),
                (2, "SKU-L", "ENTRY-2", "ENTRY:ENTRY-2"),
            ],
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM sales_fact_v2 WHERE order_id='O-SHARED'"
        ).fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sales_fact_v2 "
                "(sale_id, order_id, store_code, sku_id, kaspi_offer_name, "
                "source_entry_id, kaspi_article, line_identity_key) "
                "VALUES (3, 'O-OTHER', 'UNIVERSAL', 'SKU-X', 'Other', "
                "'ENTRY-1', 'ARTICLE-X', 'ENTRY:ENTRY-1')"
            )
