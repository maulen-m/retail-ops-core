from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from scripts.sync_ads_sidecar import run_sync_ads_sidecar


def _init_app_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_sku (sku_key TEXT PRIMARY KEY);
        CREATE TABLE dim_sku_size (sku_id TEXT PRIMARY KEY, sku_key TEXT NOT NULL, my_size TEXT);
        """
    )
    conn.commit()
    conn.close()


def _init_ads_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE campaign_product_daily_current (
            date TEXT,
            merchant_id TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            json_merchant_sku TEXT,
            assisted_products TEXT,
            cost REAL
        );
        """
    )
    conn.commit()
    conn.close()


def test_run_sync_ads_sidecar_fails_closed_when_source_missing(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    missing_ads = tmp_path / "missing_ads.db"
    _init_app_db(app_db)

    rc = run_sync_ads_sidecar(
        app_db=app_db,
        ads_db=missing_ads,
        since="2026-02-01",
        until="2026-02-07",
        apply=False,
    )
    assert rc == 1


def test_run_sync_ads_sidecar_fails_closed_when_source_stale(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    _init_ads_db(ads_db)

    old_epoch = time.time() - (80 * 3600)
    os.utime(ads_db, (old_epoch, old_epoch))

    rc = run_sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since="2026-02-01",
        until="2026-02-07",
        apply=False,
    )
    assert rc == 1
