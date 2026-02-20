#!/usr/bin/env python3
"""
Migration 020: Kaspi article/offer mapping table.

Creates dim_kaspi_article_map to store per-store Kaspi article
(SKU_ID_KSP), offer name, and mapping to internal sku_key/sku_id.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("Migration 020: Kaspi article/offer mapping table")
    print("=" * 60)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_kaspi_article_map (
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
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_kaspi_article_map_sku_key ON dim_kaspi_article_map(sku_key)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_kaspi_article_map_offer ON dim_kaspi_article_map(kaspi_offer_name)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_kaspi_article_map_store ON dim_kaspi_article_map(store_code)"
    )

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("Migration 020 complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
