import os
import sqlite3
from pathlib import Path

import pytest

from scripts.sync_ads_sidecar import run_sync_ads_sidecar, sync_ads_sidecar


def _init_app_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT
        );
        INSERT INTO dim_sku (sku_key) VALUES ('CL_NEW-CLO2_MEN_SUIT-61_BLACK');
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('OF_SUIT-61_BLK_XL', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'XL');
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
            cost REAL
        );
        INSERT INTO campaign_product_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, json_merchant_sku, cost)
        VALUES
        ('2026-02-07', 'm1', 'ACMEWEAR', 'c1', 'Suit', '19796919b', 'OF_SUIT-61_BLK_XL_50', 1000.0),
        ('2026-02-07', 'm1', 'ACMEWEAR', 'c1', 'Suit', 'UNKNOWN_KEY', '', 500.0);
        """
    )
    conn.commit()
    conn.close()


def test_sync_ads_sidecar_maps_and_tracks_unmapped_spend(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    _init_ads_db(ads_db)

    summary = sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since="2026-02-07",
        until="2026-02-07",
        apply=True,
    )
    assert summary["rows_total"] == 2
    assert summary["rows_mapped"] == 1
    assert summary["rows_unmapped"] == 1

    conn = sqlite3.connect(app_db)
    row = conn.execute(
        """
        SELECT mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapping_coverage_pct
        FROM ads_spend_sidecar_daily
        WHERE date='2026-02-07' AND store_code='ACMEWEAR'
        """
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 1000.0
    assert row[1] == 500.0
    assert row[2] == 1500.0
    assert row[3] == 50.0


def test_run_sync_ads_sidecar_apply_requires_enable_cashflow_write(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    _init_ads_db(ads_db)

    os.environ.pop("ENABLE_CASHFLOW_WRITE", None)
    rc = run_sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since="2026-02-07",
        until="2026-02-07",
        apply=True,
    )
    assert rc == 1


def test_run_sync_ads_sidecar_uses_env_ads_db_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    _init_ads_db(ads_db)

    monkeypatch.setenv("KASPI_MARKETING_DB_PATH", str(ads_db))
    rc = run_sync_ads_sidecar(
        app_db=app_db,
        ads_db=None,
        since="2026-02-07",
        until="2026-02-07",
        apply=False,
    )
    assert rc == 0


def test_run_sync_ads_sidecar_blocks_prod_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_db = tmp_path / "app.db"
    _init_app_db(app_db)
    prod_ads_path = Path(
        "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/"
        "Kaspi_marketing/db/kaspi_marketing.db"
    )

    monkeypatch.delenv("ALLOW_PROD_ADS_DB", raising=False)

    with pytest.raises(RuntimeError, match="Refusing to use production ads DB path"):
        run_sync_ads_sidecar(
            app_db=app_db,
            ads_db=prod_ads_path,
            since="2026-02-07",
            until="2026-02-07",
            apply=False,
        )
