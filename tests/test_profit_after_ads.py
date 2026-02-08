import sqlite3
from pathlib import Path

import yaml

from scripts.generate_business_insides import generate_business_insides


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
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
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT
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
        CREATE TABLE ads_spend_sidecar_daily (
            date TEXT,
            store_code TEXT,
            mapped_cost_kzt REAL,
            unmapped_cost_kzt REAL,
            total_cost_kzt REAL,
            mapped_rows INTEGER,
            unmapped_rows INTEGER,
            mapping_coverage_pct REAL
        );
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2000, 0, 0)")
    conn.execute("INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('SKU_A_M', 'SKU_A', 'M')")
    conn.execute("INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock) VALUES ('2026-02-07', 'SKU_A', 5)")
    conn.execute(
        "INSERT INTO po_part (po_part_id, po_id, status, base_cost_kzt, est_delivery_kzt, is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt) "
        "VALUES ('PO-1.1', 'PO-1', 'IN_TRANSIT', 1000, 100, 1, 1, 0, 0)"
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, quantity, cogs, net_rev, status, return_flag)
        VALUES ('O1', '2026-02-08', 'SKU_A', 'SKU_A_M', 1, 2000, 6000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-02-08', 'ACMEWEAR', 900, 100, 1000, 1, 1, 50.0)
        """
    )
    conn.commit()
    conn.close()


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


def test_business_insides_reports_profit_after_ads_and_mapping_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank.yaml"
    _init_db(db_path)
    _write_bank(bank)

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
    )
    perf = result["performance"]
    assert perf["avg_7d_profit_kzt"] > perf["avg_7d_profit_after_ads_kzt"]
    assert perf["avg_7d_ads_spend_kzt"] > 0
    assert result["ads"]["mapping_coverage_pct"] == 50.0
