import sqlite3
from pathlib import Path

import yaml

from scripts.generate_business_insides import generate_business_insides


def _write_bank_yaml(path: Path) -> None:
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


def _seed_db_with_custom_views(db_path: Path) -> None:
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
            'ORD-1' AS order_id,
            '2026-02-08' AS sale_date,
            'ACMEWEAR' AS store_code,
            'SKU_A' AS sku_key,
            'SKU_A_M' AS sku_id,
            'M' AS my_size,
            2.0 AS units,
            10000.0 AS net_rev_kzt,
            5000.0 AS cogs_kzt,
            5000.0 AS profit_kzt,
            'line_cogs' AS cogs_source,
            'sales_fact_v2' AS source_table;
        CREATE VIEW view_sales_daily_truth AS
        SELECT
            '2026-02-08' AS sale_date,
            'ACMEWEAR' AS store_code,
            'SKU_A' AS sku_key,
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
        VALUES ('SKU_A', 'A', 'BLACK', 'CL', 0, 0, 1500)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock)
        VALUES ('2026-02-07', 'SKU_A', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO po_part
        (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt)
        VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 10000, 1000, 1, 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()


def test_business_insides_daily_rows_follow_published_daily_truth(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank_accounts.yaml"
    _seed_db_with_custom_views(db_path)
    _write_bank_yaml(bank)

    # Keep injected custom views to assert consumer binding.
    monkeypatch.setattr("scripts.generate_business_insides.ensure_sales_truth_views", lambda conn: None)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )

    by_day = {row["date"]: row for row in result["last_7_days"]}
    assert by_day["2026-02-08"]["net_rev_kzt"] == 7000.0
    assert by_day["2026-02-08"]["cogs_kzt"] == 3000.0
    assert by_day["2026-02-08"]["profit_kzt"] == 4000.0
