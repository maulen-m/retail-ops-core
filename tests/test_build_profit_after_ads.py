from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from scripts.build_profit_after_ads import build_profit_after_ads


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
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-02-08', 'ACMEWEAR', 900, 100, 1000, 1, 1, 50.0)
        """
    )
    conn.commit()
    conn.close()


def test_build_profit_after_ads_marks_unavailable_when_ads_source_stale(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    source = tmp_path / "ads.db"
    _init_db(db_path)
    source.write_text("stub", encoding="utf-8")
    stale_epoch = time.time() - (80 * 3600)
    os.utime(source, (stale_epoch, stale_epoch))

    monkeypatch.setenv("AB_ADS_DB_PATH", str(source))
    monkeypatch.setenv("AB_ADS_DB_MAX_AGE_HOURS", "36")

    report = build_profit_after_ads(db_path=db_path, as_of="2026-02-08", days=7)
    assert report["ads_status"] == "unavailable"
    assert report["avg_7d_ads_spend_kzt"] is None
    assert report["daily"][-1]["ads_spend_kzt"] is None
