import sqlite3
from pathlib import Path

from scripts.build_kaspi_marketing_owner_workbook import build_owner_frames


def _seed_ads_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE campaign_product_daily_current (
                date TEXT,
                merchant_id TEXT,
                store_code TEXT,
                campaign_id TEXT,
                campaign_name TEXT,
                sku_key TEXT,
                product_name TEXT,
                json_merchant_sku TEXT,
                orders_total INTEGER,
                gmv REAL,
                cost REAL,
                views INTEGER,
                clicks INTEGER,
                favorites INTEGER,
                carts INTEGER,
                ingested_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE campaign_daily_current (
                date TEXT,
                merchant_id TEXT,
                store_code TEXT,
                campaign_id TEXT,
                campaign_name TEXT,
                views INTEGER,
                clicks INTEGER,
                favorites INTEGER,
                carts INTEGER,
                transactions INTEGER,
                gmv REAL,
                cost REAL,
                crr REAL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO campaign_product_daily_current
            (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, product_name, json_merchant_sku, orders_total, gmv, cost, views, clicks, favorites, carts, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                # historical mapped allowed model -> keep
                ("2025-01-02", "759051", "30137883", "2380614", "Acmewear_16k", "ads-a", "A", "CL_OC_MEN_LINE51_WHITE_XL_134547490", 2, 1200.0, 100.0, 10, 2, 1, 1, "2026-02-06T00:00:00+05:00"),
                # historical unmapped -> drop
                ("2025-01-02", "759051", "30137883", "2380614", "Acmewear_16k", "ads-b", "B", "", 1, 500.0, 50.0, 5, 1, 0, 0, "2026-02-06T00:00:00+05:00"),
                # historical mapped disallowed model -> drop
                ("2025-01-03", "759051", "30137883", "7000000", "Line52", "ads-c", "C", "CL_OC_MEN_LINE52_BLACK_XL_0001", 1, 700.0, 70.0, 7, 1, 0, 0, "2026-02-06T00:00:00+05:00"),
                # future unmapped -> keep
                ("2026-02-10", "759051", "30137883", "9999999", "Future", "ads-d", "D", "", 3, 900.0, 90.0, 9, 3, 1, 1, "2026-02-10T00:00:00+05:00"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO campaign_daily_current
            (date, merchant_id, store_code, campaign_id, campaign_name, views, clicks, favorites, carts, transactions, gmv, cost, crr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2025-01-02", "759051", "30137883", "2380614", "Acmewear_16k", 100, 20, 5, 4, 3, 1700.0, 150.0, 8.0),
                ("2026-02-10", "759051", "30137883", "9999999", "Future", 40, 9, 1, 1, 3, 900.0, 90.0, 10.0),
            ],
        )
        conn.commit()


def _seed_app_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE dim_sku (sku_key TEXT PRIMARY KEY, model TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE dim_sku_size (sku_id TEXT PRIMARY KEY, sku_key TEXT NOT NULL)"
        )
        conn.execute(
            """
            CREATE TABLE fact_sales (
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                store_code TEXT,
                line_net_rev REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, model) VALUES (?, ?)",
            [
                ("CL_OC_MEN_LINE51_WHITE", "LINE51"),
                ("CL_OC_MEN_LINE52_BLACK", "LINE52"),
            ],
        )
        conn.executemany(
            "INSERT INTO dim_sku_size (sku_id, sku_key) VALUES (?, ?)",
            [
                ("CL_OC_MEN_LINE51_WHITE_XL_134547490", "CL_OC_MEN_LINE51_WHITE"),
                ("CL_OC_MEN_LINE52_BLACK_XL_0001", "CL_OC_MEN_LINE52_BLACK"),
            ],
        )
        conn.executemany(
            "INSERT INTO fact_sales (order_id, order_date, sku_key, store_code, line_net_rev) VALUES (?, ?, ?, ?, ?)",
            [
                ("ord-1", "2025-01-02", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 1000.0),
                ("ord-2", "2025-01-02", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 300.0),
                ("ord-3", "2026-02-10", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 200.0),
            ],
        )
        conn.commit()


def test_build_owner_frames_applies_historical_filter_and_future_no_filter(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)

    campaign_df, product_df = build_owner_frames(
        ads_db=ads_db,
        app_db=app_db,
        history_start_date="2025-01-01",
        future_cutover_date="2026-02-01",
        strict_models={"line51", "line61", "suit-61"},
        store_code="ACMEWEAR",
    )

    # historical keeps only mapped + allowed model
    hist = product_df[product_df["date"].astype(str) == "2025-01-02"]
    assert len(hist) == 1
    assert hist.iloc[0]["mapping_status"] == "mapped"
    assert hist.iloc[0]["zone_type"] == "historical_strict"
    assert hist.iloc[0]["db_orders_count"] == 2
    assert hist.iloc[0]["db_sales_gmv_kzt"] == 1300.0

    # future keeps unmapped rows too
    fut = product_df[product_df["date"].astype(str) == "2026-02-10"]
    assert len(fut) == 1
    assert fut.iloc[0]["mapping_status"] == "unmapped"
    assert fut.iloc[0]["zone_type"] == "future_all"

    assert not campaign_df.empty
    assert {"db_orders_count", "db_sales_gmv_kzt", "delta_orders_db_minus_ads"}.issubset(campaign_df.columns)
