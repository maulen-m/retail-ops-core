import os
import sqlite3
from pathlib import Path

from scripts.sync_ads_sidecar import sync_ads_sidecar, run_sync_ads_sidecar


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
        INSERT INTO dim_sku (sku_key) VALUES ('CL_OC_MEN_LINE52_BLACK');
        INSERT INTO dim_sku (sku_key) VALUES ('CL_OC_MEN_LINE51_WHITE');
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
            assisted_products TEXT,
            cost REAL
        );
        INSERT INTO campaign_product_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, json_merchant_sku, assisted_products, cost)
        VALUES
        ('2026-02-07', 'm1', 'ACMEWEAR', 'c1', 'Suit', '19796919b', 'OF_SUIT-61_BLK_XL_50', '', 1000.0),
        ('2026-02-07', 'm1', 'ACMEWEAR', 'c1', 'Suit', 'UNKNOWN_KEY', '', '', 500.0);
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


def test_sync_ads_sidecar_model_hint_line52_maps(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    conn = sqlite3.connect(ads_db)
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
        INSERT INTO campaign_product_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, json_merchant_sku, assisted_products, cost)
        VALUES ('2026-02-07', 'm1', 'ACMEWEAR', 'c1', 'Line52 campaign', 'UNKNOWN', 'LINE52_BLACK_2XL_102529963', '', 777.0);
        """
    )
    conn.commit()
    conn.close()

    summary = sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since="2026-02-07",
        until="2026-02-07",
        apply=True,
    )
    assert summary["rows_mapped"] == 1
    conn = sqlite3.connect(app_db)
    row = conn.execute(
        """
        SELECT sku_key, mapped
        FROM ads_spend_sidecar_daily_sku
        WHERE date='2026-02-07'
        """
    ).fetchone()
    conn.close()
    assert row == ("CL_OC_MEN_LINE52_BLACK", 1)


def test_sync_ads_sidecar_adds_zero_cost_coverage_rows_from_assisted_products(tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    ads_db = tmp_path / "ads.db"
    _init_app_db(app_db)
    conn = sqlite3.connect(ads_db)
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
        INSERT INTO campaign_product_daily_current
        (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, json_merchant_sku, assisted_products, cost)
        VALUES (
            '2026-02-08',
            'm1',
            'ACMEWEAR',
            'c1',
            'Acmewear_16k',
            '19102598b',
            'CL_OC_MEN_LINE51_WHITE_XL_134547490',
            'CL_OC_MEN_LINE52_BLACK_120939888_56_(3XL)',
            14175.24
        );
        """
    )
    conn.commit()
    conn.close()

    summary = sync_ads_sidecar(
        app_db=app_db,
        ads_db=ads_db,
        since="2026-02-08",
        until="2026-02-08",
        apply=True,
    )
    assert summary["rows_mapped"] == 1
    assert summary["coverage_hint_rows"] == 1

    conn = sqlite3.connect(app_db)
    rows = conn.execute(
        """
        SELECT sku_key, ads_cost_kzt, mapped, merchant_sku_key
        FROM ads_spend_sidecar_daily_sku
        WHERE date='2026-02-08'
        ORDER BY ads_cost_kzt DESC, sku_key
        """
    ).fetchall()
    conn.close()
    assert rows == [
        ("CL_OC_MEN_LINE51_WHITE", 14175.24, 1, "CL_OC_MEN_LINE51_WHITE_XL_134547490"),
        ("CL_OC_MEN_LINE52_BLACK", 0.0, 1, "CL_OC_MEN_LINE52_BLACK_120939888_56_(3XL)"),
    ]


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
