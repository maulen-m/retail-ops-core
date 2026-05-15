from __future__ import annotations

import sqlite3
from pathlib import Path
from textwrap import dedent

from scripts.generate_business_insides import compute_sales_metrics


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
    conn.execute("INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2000, 28, 0.9)")
    conn.execute("INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('SKU_A_M', 'SKU_A', 'M')")
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
    conn.commit()
    conn.close()


def test_effective_cost_mode_fails_closed_when_policy_missing(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    ads_source = tmp_path / "ads.db"
    _init_db(db_path)
    ads_source.write_text("stub", encoding="utf-8")

    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))
    monkeypatch.setenv("AB_ADS_EFFECTIVE_COST_MODE", "1")
    monkeypatch.setenv("AB_ADS_EFFECTIVE_COST_POLICY_PATH", str(tmp_path / "missing_policy.yaml"))

    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")
    assert metrics["ads"]["status"] == "unavailable", metrics["ads"]
    assert metrics["ads"]["reason"] == "policy_missing"
    assert metrics["avg_7d_profit_after_ads_kzt"] is None


def test_effective_cost_policy_multiplier_applies_when_present(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    ads_source = tmp_path / "ads.db"
    policy = tmp_path / "policy.yaml"
    _init_db(db_path)
    ads_source.write_text("stub", encoding="utf-8")
    policy.write_text(
        dedent(
            """
            default_multiplier: 1.2
            date_overrides: []
            """
        ).strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))
    monkeypatch.setenv("AB_ADS_EFFECTIVE_COST_MODE", "1")
    monkeypatch.setenv("AB_ADS_EFFECTIVE_COST_POLICY_PATH", str(policy))
    monkeypatch.setenv("AB_ADS_DB_MAX_AGE_HOURS", "240")

    metrics = compute_sales_metrics(db_path=db_path, as_of="2026-02-08")
    assert metrics["ads"]["status"] == "available", metrics["ads"]
    # 1000 cost * 1.2 / 7-day window
    assert metrics["avg_7d_ads_spend_kzt"] == 171.43
