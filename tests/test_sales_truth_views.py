import sqlite3
import threading
import time
from pathlib import Path

from core.sales.truth_views import ensure_sales_truth_views


def _seed_schema(conn: sqlite3.Connection) -> None:
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
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL,
            profit_line REAL
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


def test_view_sales_line_truth_prefers_sales_fact_v2_on_overlap(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', 40, 0.5, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 10000, 3000, 7000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 8000, 2000, 6000)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT net_rev_kzt, source_table
        FROM view_sales_line_truth
        WHERE order_id='ORD-1'
        """
    ).fetchone()
    conn.close()

    assert row[0] == 10000
    assert row[1] == "sales_fact_v2"


def test_view_sales_daily_truth_uses_fact_sales_when_missing_in_sales_fact_v2(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_B', 20, 0.2, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-2', '2026-02-08', 'SKU_B', 'SKU_B_L', 'L', 'ACMEWEAR', 3, 15000, 4500, 10500)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT units, revenue_kzt
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-08' AND sku_key='SKU_B'
        """
    ).fetchone()
    conn.close()

    assert row[0] == 3
    assert row[1] == 15000


def test_view_sales_truth_excludes_fact_sales_on_overlapping_dates(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-V2-1", "2026-02-05", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 1, 1000, 300, 700, "DELIVERED", 0),
            ("ORD-V2-2", "2026-02-06", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 2, 2200, 600, 1600, "DELIVERED", 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-FS-OVERLAP", "2026-02-05", "SKU_A", "SKU_A_L", "L", "ACMEWEAR", 10, 8000, 2500, 5500),
            ("ORD-FS-PRE", "2026-02-04", "SKU_A", "SKU_A_L", "L", "ACMEWEAR", 3, 2400, 900, 1500),
        ],
    )
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt) VALUES ('SKU_A', 30, 0.5, 0)")
    conn.commit()

    ensure_sales_truth_views(conn)

    daily = conn.execute(
        """
        SELECT sale_date, SUM(units) AS units, SUM(revenue_kzt) AS net_rev
        FROM view_sales_daily_truth
        GROUP BY sale_date
        ORDER BY sale_date
        """
    ).fetchall()
    conn.close()

    assert daily == [
        ("2026-02-04", 3.0, 2400.0),
        ("2026-02-05", 1.0, 1000.0),
        ("2026-02-06", 2.0, 2200.0),
    ]


def test_view_sales_truth_keeps_fact_sales_for_pre_v2_history_only(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-V2-1', '2026-02-10', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 1, 1500, 300, 1200, 'DELIVERED', 0)
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-FS-HIST", "2026-02-09", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 2, 1800, 600, 1200),
            ("ORD-FS-OVERLAP", "2026-02-10", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 7, 7000, 2100, 4900),
        ],
    )
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt) VALUES ('SKU_A', 25, 0.4, 0)")
    conn.commit()

    ensure_sales_truth_views(conn)
    rows = conn.execute(
        """
        SELECT order_id, sale_date, source_table, units, net_rev_kzt
        FROM view_sales_line_truth
        ORDER BY sale_date, order_id
        """
    ).fetchall()
    conn.close()

    assert rows == [
        ("ORD-FS-HIST", "2026-02-09", "fact_sales", 2.0, 1800.0),
        ("ORD-V2-1", "2026-02-10", "sales_fact_v2", 1.0, 1500.0),
    ]


def test_truth_view_maps_offer_article_to_canonical_line61(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES ('ACMEWEAR', 'OF_SUIT-61_BLK_XL_50', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('CL_NEW-CLO2_MEN_SUIT-61_BLACK', 100, 1.5, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-SUIT', '2026-02-08', 'OF_SUIT-61_BLK_XL_50', 'OF_SUIT-61_BLK_XL_50_XL', 'XL', 'ACMEWEAR', 2, 20000, 0, 0, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT sku_key, sku_id, source_sku_key, source_sku_id
        FROM view_sales_line_truth
        WHERE order_id='ORD-SUIT'
        """
    ).fetchone()
    conn.close()

    assert row == (
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL",
        "OF_SUIT-61_BLK_XL_50",
        "OF_SUIT-61_BLK_XL_50_XL",
    )


def test_truth_view_uses_inactive_article_map_when_no_active_row_exists(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, active_flag)
        VALUES ('ACMEWEAR', '108381956_872156561', 'CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('CL_OC_MEN_LINE52_BLACK', 47, 0.95, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-INACTIVE-MAP', '2026-02-08', '108381956_872156561', '108381956_872156561', '', 'ACMEWEAR', 1, 9900, 0, 0, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT sku_key, cogs_source, cogs_kzt
        FROM view_sales_line_truth
        WHERE order_id='ORD-INACTIVE-MAP'
        """
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "CL_OC_MEN_LINE52_BLACK"
    assert row[1] == "formula_full"
    assert row[2] is not None and row[2] > 0


def test_truth_view_cogs_uses_full_formula_not_partial_source_cogs(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_FORMULA', 100, 1.5, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-FML', '2026-02-08', 'SKU_FORMULA', 'SKU_FORMULA_L', 'L', 'ACMEWEAR', 2, 25000, 1, 24999, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT cogs_kzt, cogs_source, source_cogs_kzt
        FROM view_sales_line_truth
        WHERE order_id='ORD-FML'
        """
    ).fetchone()
    conn.close()

    # cogs_unit = 100*75 + 1.5*520*2.66 = 9574.8; line = 19149.6
    assert row[0] == 19149.6
    assert row[1] == "formula_full"
    assert row[2] == 1.0


def test_truth_view_unresolved_when_base_or_weight_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_BAD', 80, NULL, 2500)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-BAD', '2026-02-08', 'SKU_BAD', 'SKU_BAD_M', 'M', 'ACMEWEAR', 1, 10000, 0, 0, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT cogs_kzt, profit_kzt, cogs_source
        FROM view_sales_line_truth
        WHERE order_id='ORD-BAD'
        """
    ).fetchone()
    conn.close()

    assert row[0] is None
    assert row[1] is None
    assert row[2] == "unresolved"


def test_truth_view_preserves_source_columns_for_audit(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', 50, 1.0, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-AUD', '2026-02-08', 'SKU_A', 'SKU_A_XL', 'XL', 'ACMEWEAR', 1, 8000, 1234, 6766, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT source_sku_key, source_sku_id, source_units, source_net_rev_kzt, source_cogs_kzt, source_table
        FROM view_sales_line_truth
        WHERE order_id='ORD-AUD'
        """
    ).fetchone()
    conn.close()

    assert row == ("SKU_A", "SKU_A_XL", 1.0, 8000.0, 1234.0, "sales_fact_v2")


def test_view_sales_truth_keeps_internal_source_when_external_reference_exists(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        CREATE TABLE fact_sales_external_ref (
            line_id TEXT PRIMARY KEY,
            sale_date TEXT,
            store_code TEXT,
            order_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            net_rev_kzt REAL,
            status TEXT,
            return_flag INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-V2-OF", "2026-02-25", "SKU_A", "SKU_A", "L", "ACMEWEAR", 1, 1000, 0, 0, "DELIVERED", 0),
            ("ORD-V2-UNI", "2026-02-25", "SKU_B", "SKU_B", "L", "UNIVERSAL", 1, 2000, 0, 0, "DELIVERED", 0),
        ],
    )
    conn.execute(
        """
        INSERT INTO fact_sales_external_ref
        (line_id, sale_date, store_code, order_id, sku_key, sku_id, quantity, net_rev_kzt, status, return_flag)
        VALUES ('ref-1', '2026-02-25', 'ACMEWEAR', 'ORD-REF-OF', 'SKU_X', 'SKU_X', 3, 5000, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    truth_rows = conn.execute(
        """
        SELECT store_code, SUM(units) AS units, SUM(revenue_kzt) AS rev
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-25'
        GROUP BY store_code
        ORDER BY store_code
        """
    ).fetchall()
    reference_rows = conn.execute(
        """
        SELECT store_code, SUM(units) AS units, SUM(revenue_kzt) AS rev
        FROM view_sales_daily_reference
        WHERE sale_date='2026-02-25'
        GROUP BY store_code
        ORDER BY store_code
        """
    ).fetchall()
    conn.close()

    assert truth_rows == [("ACMEWEAR", 1.0, 1000.0), ("UNIVERSAL", 1.0, 2000.0)]
    assert reference_rows == [("ACMEWEAR", 3.0, 5000.0)]


def test_ensure_sales_truth_views_waits_for_transient_db_lock(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    locker = sqlite3.connect(db, check_same_thread=False)
    _seed_schema(locker)
    locker.execute(
        """
        INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_LOCK', 40, 0.5, 0)
        """
    )
    locker.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-LOCK', '2026-02-08', 'SKU_LOCK', 'SKU_LOCK_M', 'M', 'ACMEWEAR', 1, 1000, 300, 700, 'DELIVERED', 0)
        """
    )
    locker.commit()

    runner = sqlite3.connect(db, timeout=0.1)
    try:
        locker.execute("BEGIN EXCLUSIVE")

        def _release_lock() -> None:
            time.sleep(0.3)
            locker.rollback()

        release_thread = threading.Thread(target=_release_lock)
        release_thread.start()

        ensure_sales_truth_views(runner)
        row = runner.execute(
            """
            SELECT order_id, source_table
            FROM view_sales_line_truth
            WHERE order_id='ORD-LOCK'
            """
        ).fetchone()
        release_thread.join(timeout=2.0)
    finally:
        runner.close()
        locker.close()

    assert row == ("ORD-LOCK", "sales_fact_v2")
