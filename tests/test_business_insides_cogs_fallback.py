import sqlite3
from pathlib import Path

from scripts.generate_business_insides import compute_sales_metrics


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            cogs REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        """
    )
    conn.commit()
    conn.close()


def test_cogs_formula_uses_full_landed_components(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', 'A', 'BLACK', 'CL', 100, 1.5, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 2, NULL, 10000, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()

    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")
    day = {r["date"]: r for r in metrics["last_7_days"]}["2026-02-08"]
    # unit COGS = 100*75 + 1.5*520*2.66 = 9574.8 -> line = 19149.6
    assert day["cogs_kzt"] == 19149.6
    assert day["profit_kzt"] == -9149.6
    assert metrics["fallback_rows"] == 0


def test_profit_uses_effective_cogs_not_raw_zero_cogs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_A', 'A', 'BLACK', 'CL', 35, 0.72, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES ('ORD-2', '2026-02-08', 'SKU_A', 'SKU_A_L', 3, 0, 12000, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()

    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")
    day = {r["date"]: r for r in metrics["last_7_days"]}["2026-02-08"]
    assert day["cogs_kzt"] > 0
    assert day["profit_kzt"] == round(day["net_rev_kzt"] - day["cogs_kzt"], 2)


def test_unresolved_rows_and_sku_count_are_reported(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-U-1", "2026-02-08", "SKU_X", "SKU_X_M", 1, None, 2000, "DELIVERED", 0),
            ("ORD-U-2", "2026-02-08", "SKU_X", "SKU_X_L", 2, 0, 3000, "DELIVERED", 0),
            ("ORD-U-3", "2026-02-08", "SKU_Y", "SKU_Y_S", 1, None, 1000, "DELIVERED", 0),
        ],
    )
    conn.commit()
    conn.close()

    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")
    assert metrics["unresolved_rows"] == 3
    assert metrics["unresolved_sku_count"] == 2
