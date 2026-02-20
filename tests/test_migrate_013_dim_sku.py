from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.migrate_013 import migrate, REQUIRED_COLUMNS


def _create_old_dim_sku(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            category TEXT,
            gender TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def test_migrate_013_adds_missing_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_old_dim_sku(db_path)

    migrate(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_sku)").fetchall()}
    for col in REQUIRED_COLUMNS:
        assert col in cols

    # Ensure insert with new columns works
    conn.execute(
        """
        INSERT INTO dim_sku (
            sku_key, model, color, product_type, base_cost_cny, weight_kg,
            cogs_kzt, avg_sell_price_kzt_used, avg_sell_price_source, price_missing_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("TEST_SKU", "MODEL", "BLACK", "CL", 10.0, 1.0, 100.0, 120.0, "DIM_SKU", 0),
    )
    conn.commit()
    conn.close()
