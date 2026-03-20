import sqlite3
from pathlib import Path

import yaml

from scripts.generate_business_insides import compute_sales_metrics


def _write_bank(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "as_of": "2026-02-08 10:00:00 GMT+5",
                "stores": {"ACMEWEAR": {"accounts": {"kaspi_gold": {"balance_kzt": 1_000_000}}}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _seed_views_only(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT,
            color TEXT,
            product_type TEXT,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock REAL
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            status TEXT,
            base_cost_kzt REAL,
            est_delivery_kzt REAL,
            is_paid_base INTEGER,
            is_paid_dlv INTEGER,
            to_pay_base_kzt REAL,
            to_pay_dlv_kzt REAL
        );
        CREATE VIEW view_sales_line_truth AS
        SELECT
            'ORD-X' AS order_id,
            '2026-02-08' AS sale_date,
            'ACMEWEAR' AS store_code,
            'SKU_X' AS sku_key,
            'SKU_X_M' AS sku_id,
            'M' AS my_size,
            2.0 AS units,
            9000.0 AS net_rev_kzt,
            4000.0 AS cogs_kzt,
            5000.0 AS profit_kzt,
            'formula_full' AS cogs_source,
            'sales_fact_v2' AS source_table;
        CREATE VIEW view_sales_daily_truth AS
        SELECT
            '2026-02-08' AS sale_date,
            'ACMEWEAR' AS store_code,
            'SKU_X' AS sku_key,
            2.0 AS units,
            7000.0 AS revenue_kzt,
            3000.0 AS cogs_kzt,
            4000.0 AS profit_kzt,
            1 AS line_count;
        """
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
        VALUES ('SKU_X', 'X', 'BLACK', 'CL', 10, 1, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock)
        VALUES ('2026-02-07', 'SKU_X', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO po_part
        (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt)
        VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 1000, 100, 1, 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()


def test_compute_sales_metrics_reads_published_truth_views(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_views_only(db_path)
    _write_bank(tmp_path / "bank_accounts.yaml")

    monkeypatch.setattr("scripts.generate_business_insides.ensure_sales_truth_views", lambda conn: None)
    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")

    day = next(row for row in metrics["last_7_days"] if row["date"] == "2026-02-08")
    assert day["units_shipped"] == 2.0
    assert day["net_rev_kzt"] == 9000.0
    assert day["cogs_kzt"] == 3000.0
    assert day["profit_kzt"] == 4000.0
