from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from scripts.build_offer_stock_mapper import build_offer_stock_mapper


def _setup_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            kaspi_offer_name TEXT,
            order_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT,
            quantity INTEGER NOT NULL
        )
        """
    )

    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, ?)", ("SKU_A", 1))
    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, ?)", ("SKU_B", 1))
    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, ?)", ("SKU_C", 1))

    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?, ?, ?, ?)",
        ("SKU_A_S", "SKU_A", "S", 1),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?, ?, ?, ?)",
        ("SKU_B_M", "SKU_B", "M", 1),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?, ?, ?, ?)",
        ("SKU_B_L", "SKU_B", "L", 1),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?, ?, ?, ?)",
        ("SKU_C_XL", "SKU_C", "XL", 1),
    )

    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("UNIVERSAL", "SKU_A_S_1001", "Offer A", "SKU_A", "SKU_A_S", 1, "2026-02-18T00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("UNIVERSAL", "SKU_B_M_2002", "Offer B", "SKU_B", None, 1, "2026-02-18T00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("STOREB", "C_ONLY_3003", "Offer C", None, None, 1, "2026-02-18T00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map
            (store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, active_flag, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("STOREB", "B_NO_SIZE_4004", "Offer D", "SKU_B", None, 1, "2026-02-18T00:00:00"),
    )

    today = date.today().isoformat()
    conn.execute(
        """
        INSERT INTO fact_sales
            (store_code, kaspi_offer_name, order_date, sku_id, sku_key, my_size, quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("STOREB", "Offer C", today, "SKU_C_XL", "SKU_C", "XL", 5),
    )
    conn.execute(
        """
        INSERT INTO fact_sales
            (store_code, kaspi_offer_name, order_date, sku_id, sku_key, my_size, quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("STOREB", "Offer C", today, "SKU_B_M", "SKU_B", "M", 1),
    )
    conn.commit()
    conn.close()


def _write_store_config(path: Path) -> None:
    path.write_text(
        "stores:\n"
        "  UNIVERSAL:\n"
        "    merchant_uid: \"30000001\"\n"
        "  STOREB:\n"
        "    merchant_uid: \"30000002\"\n",
        encoding="utf-8",
    )


def test_build_offer_stock_mapper_resolves_expected_methods(tmp_path: Path):
    db_path = tmp_path / "app.db"
    cfg_path = tmp_path / "kaspi_stores.yaml"
    _setup_db(db_path)
    _write_store_config(cfg_path)

    summary = build_offer_stock_mapper(
        db_path=db_path,
        stores=["UNIVERSAL", "STOREB"],
        config_path=cfg_path,
        table_name="fact_offer_stock_mapper_current",
        window_days=90,
        dry_run=False,
    )

    assert summary["rows_total"] == 4
    assert summary["unresolved_rows"] == 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT store_code, kaspi_article, merchant_uid, sku_id, mapping_method, mapping_confidence, is_ambiguous
        FROM fact_offer_stock_mapper_current
        ORDER BY store_code, kaspi_article
        """
    ).fetchall()
    conn.close()

    by_key = {(row["store_code"], row["kaspi_article"]): row for row in rows}

    row_a = by_key[("UNIVERSAL", "SKU_A_S_1001")]
    assert row_a["merchant_uid"] == "30000001"
    assert row_a["sku_id"] == "SKU_A_S"
    assert row_a["mapping_method"] == "article_map_sku_id"
    assert row_a["mapping_confidence"] == "HIGH"

    row_b = by_key[("UNIVERSAL", "SKU_B_M_2002")]
    assert row_b["sku_id"] == "SKU_B_M"
    assert row_b["mapping_method"] == "article_map_article_size"
    assert row_b["mapping_confidence"] == "HIGH"

    row_c = by_key[("STOREB", "C_ONLY_3003")]
    assert row_c["sku_id"] == "SKU_C_XL"
    assert row_c["mapping_method"] == "recent_sales_offer_mode"
    assert row_c["mapping_confidence"] in {"HIGH", "MEDIUM"}

    row_d = by_key[("STOREB", "B_NO_SIZE_4004")]
    assert row_d["sku_id"] is None
    assert row_d["mapping_method"] == "unresolved"
    assert row_d["is_ambiguous"] == 1
