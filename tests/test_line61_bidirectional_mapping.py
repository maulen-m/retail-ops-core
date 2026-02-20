import sqlite3
from pathlib import Path

from core.sales.truth_views import ensure_sales_truth_views, get_article_aliases_for_sku


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        );
        """
    )


def test_article_to_canonical_mapping_for_of_line61_variants(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed(conn)
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt) VALUES ('CL_NEW-CLO2_MEN_SUIT-61_BLACK', 100, 1.0, 0)"
    )
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, 1)
        """,
        [
            ("ACMEWEAR", "OF_SUIT-61_BLK_XL_50", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL"),
            ("ACMEWEAR", "OF_SUIT-61_BLK_4XL_56", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES (?, '2026-02-08', ?, ?, ?, 'ACMEWEAR', 1, 12000, 0, 0, 'DELIVERED', 0)
        """,
        [
            ("ORD-XL", "OF_SUIT-61_BLK_XL_50", "OF_SUIT-61_BLK_XL_50_XL", "XL"),
            ("ORD-4XL", "OF_SUIT-61_BLK_4XL_56", "OF_SUIT-61_BLK_4XL_56_4XL", "4XL"),
        ],
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    rows = conn.execute(
        "SELECT order_id, sku_key FROM view_sales_line_truth ORDER BY order_id"
    ).fetchall()
    conn.close()

    assert rows == [
        ("ORD-4XL", "CL_NEW-CLO2_MEN_SUIT-61_BLACK"),
        ("ORD-XL", "CL_NEW-CLO2_MEN_SUIT-61_BLACK"),
    ]


def test_canonical_to_article_presence_for_reverse_traceability(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed(conn)
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, 1)
        """,
        [
            ("ACMEWEAR", "OF_SUIT-61_BLK_XL_50", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL"),
            ("ACMEWEAR", "OF_SUIT-61_BLK_4XL_56", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "CL_NEW-CLO2_MEN_SUIT-61_BLACK_4XL"),
        ],
    )
    conn.commit()

    aliases = get_article_aliases_for_sku(
        conn,
        sku_key="CL_NEW-CLO2_MEN_SUIT-61_BLACK",
        store_code="ACMEWEAR",
    )
    conn.close()

    assert set(aliases) >= {"OF_SUIT-61_BLK_XL_50", "OF_SUIT-61_BLK_4XL_56"}
