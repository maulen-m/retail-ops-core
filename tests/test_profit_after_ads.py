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
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            merchant_id TEXT,
            store_code TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            product_rows_total INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE ads_campaign_product_daily (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT,
            sku_key TEXT NOT NULL DEFAULT '',
            cost_kzt REAL NOT NULL DEFAULT 0,
            impressions INTEGER,
            clicks INTEGER,
            source_run_id TEXT,
            coverage_status TEXT NOT NULL DEFAULT 'UNKNOWN',
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code, campaign_id, sku_key)
        );
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 0, 28, 0.9)"
    )
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
        INSERT INTO ads_source_refresh_runs
        (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
        VALUES ('run-1', '2026-02-08T01:00:00Z', '2026-02-08T01:05:00Z', '30137883', 'ACMEWEAR', '2026-02-01', '2026-02-08', 1, 'SUCCESS')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily
        (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
        VALUES ('2026-02-08', 'ACMEWEAR', 'C1', 'Campaign', 'SKU_A', 1000, 10, 1, 'run-1', 'COVERED')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily
        (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
        VALUES ('2026-02-08', 'ACMEWEAR', 'C2', 'Unmapped', 'SKU_UNKNOWN', 0, 0, 0, 'run-1', 'UNKNOWN')
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


def test_business_insides_reports_profit_after_ads_and_mapping_coverage(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    bank = tmp_path / "bank.yaml"
    ads_source = tmp_path / "ads_source.db"
    _init_db(db_path)
    _write_bank(bank)
    ads_source.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))
    monkeypatch.setenv("AB_ADS_DB_MAX_AGE_HOURS", "36")

    result = generate_business_insides(
        db_path=db_path,
        bank_accounts_path=bank,
        as_of="2026-02-08",
        output_dir=tmp_path / "business_insides",
        archive_orders_globs=[],
    )
    perf = result["performance"]
    assert perf["avg_7d_profit_kzt"] > perf["avg_7d_profit_after_ads_kzt"]
    assert perf["avg_7d_ads_spend_kzt"] > 0
    assert result["ads"]["mapping_coverage_pct"] == 50.0
