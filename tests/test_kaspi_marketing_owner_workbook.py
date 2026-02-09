import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_kaspi_marketing_owner_workbook import build_owner_frames, build_owner_workbook


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
                bid_cpc REAL,
                bid_cpc_source TEXT,
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
            (date, merchant_id, store_code, campaign_id, campaign_name, sku_key, product_name, json_merchant_sku, bid_cpc, bid_cpc_source, orders_total, gmv, cost, views, clicks, favorites, carts, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                # historical mapped allowed model -> keep
                ("2025-01-02", "759051", "30137883", "2380614", "Acmewear_16k", "ads-a", "A", "CL_OC_MEN_LINE51_WHITE_XL_134547490", 70.0, "api_current", 2, 1200.0, 100.0, 10, 2, 1, 1, "2026-02-06T00:00:00+05:00"),
                # historical unmapped -> drop
                ("2025-01-02", "759051", "30137883", "2380614", "Acmewear_16k", "ads-b", "B", "", 40.0, "api_current", 1, 500.0, 50.0, 5, 1, 0, 0, "2026-02-06T00:00:00+05:00"),
                # historical mapped disallowed model -> drop
                ("2025-01-03", "759051", "30137883", "7000000", "Line52", "ads-c", "C", "CL_OC_MEN_LINE52_BLACK_XL_0001", 55.0, "api_current", 1, 700.0, 70.0, 7, 1, 0, 0, "2026-02-06T00:00:00+05:00"),
                # future unmapped -> keep
                ("2026-02-10", "759051", "30137883", "9999999", "Future", "ads-d", "D", "", 60.0, "api_current", 3, 900.0, 90.0, 9, 3, 1, 1, "2026-02-10T00:00:00+05:00"),
                # line61 merchant sku payload that should map by heuristic
                ("2025-01-04", "759051", "30137883", "2545773", "ACMEWEAR_LINE61", "19796919b", "Suit", "OF_SUIT-61_BLK_XL_48", 70.0, "api_current", 1, 400.0, 40.0, 4, 1, 0, 0, "2026-02-06T00:00:00+05:00"),
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
                quantity INTEGER,
                sell_price_kzt REAL,
                line_net_rev REAL,
                cogs_line REAL,
                profit_line REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, model) VALUES (?, ?)",
            [
                ("CL_OC_MEN_LINE51_WHITE", "LINE51"),
                ("CL_OC_MEN_LINE52_BLACK", "LINE52"),
                ("CL_NEW-CLO2_MEN_SUIT-61_BLACK", "SUIT-61"),
            ],
        )
        conn.executemany(
            "INSERT INTO dim_sku_size (sku_id, sku_key) VALUES (?, ?)",
            [
                ("CL_OC_MEN_LINE51_WHITE_XL_134547490", "CL_OC_MEN_LINE51_WHITE"),
                ("CL_OC_MEN_LINE52_BLACK_XL_0001", "CL_OC_MEN_LINE52_BLACK"),
                ("CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL", "CL_NEW-CLO2_MEN_SUIT-61_BLACK"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_sales
            (order_id, order_date, sku_key, store_code, quantity, sell_price_kzt, line_net_rev, cogs_line, profit_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                # Gross is used for db_sales_gmv_kzt (1000 + 300 = 1300), not net (750 + 200 = 950)
                ("ord-1", "2025-01-02", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 2, 500.0, 750.0, 600.0, 250.0),
                ("ord-2", "2025-01-02", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 1, 300.0, 200.0, 100.0, 100.0),
                ("ord-3", "2026-02-10", "CL_OC_MEN_LINE51_WHITE", "ACMEWEAR", 1, 200.0, 150.0, 100.0, 50.0),
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
    hist_row = hist.iloc[0]
    assert hist_row["mapping_status"] == "mapped"
    assert hist_row["zone_type"] == "historical_strict"
    assert hist_row["db_orders_count"] == 2
    assert hist_row["db_sales_gmv_kzt"] == 1300.0
    assert hist_row["db_cogs"] == 700.0
    assert hist_row["delta_orders_db_minus_ads"] == 0
    assert hist_row["delta_gmv_db_minus_ads"] == 100.0
    assert hist_row["db_acos"] == pytest.approx((100.0 / 1300.0) * 100.0)
    assert hist_row["db_roas"] == pytest.approx(13.0)
    assert hist_row["db_asp_kzt"] == pytest.approx(650.0)
    assert hist_row["ads_cost_per_db_order"] == pytest.approx(50.0)
    assert hist_row["db_profit_est_kzt"] == pytest.approx(250.0)
    assert hist_row["db_Unit_profit_%"] == pytest.approx((250.0 / 1300.0) * 100.0)
    assert hist_row["bid_cpc_2"] == pytest.approx(70.0)

    # future keeps unmapped rows too
    fut = product_df[product_df["date"].astype(str) == "2026-02-10"]
    assert len(fut) == 1
    assert fut.iloc[0]["mapping_status"] == "unmapped"
    assert fut.iloc[0]["zone_type"] == "future_all"

    assert not campaign_df.empty
    assert {"db_orders_count", "db_sales_gmv_kzt", "delta_orders_db_minus_ads"}.issubset(campaign_df.columns)

    suit = product_df[product_df["campaign_name"] == "ACMEWEAR_LINE61"]
    assert len(suit) == 1
    assert suit.iloc[0]["mapping_status"] == "mapped"
    assert suit.iloc[0]["mapped_sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"

    expected_product_cols = [
        "date",
        "merchant_id",
        "store_code",
        "campaign_id",
        "campaign_name",
        "sku_key",
        "product_name",
        "product_status",
        "ingested_at",
        "mapped_sku_id",
        "mapped_sku_key",
        "mapped_model",
        "mapping_status",
        "filter_rule",
        "zone_type",
        "bid_cpc",
        "bid_cpc_source",
        "ad_score",
        "avg_cpc",
        "views",
        "clicks",
        "ctr",
        "favorites",
        "carts",
        "conversion_order",
        "orders_total",
        "orders_direct",
        "orders_assisted",
        "gmv",
        "cost",
        "acos_share",
        "delta_orders_db_minus_ads",
        "db_acos",
        "db_roas",
        "delta_gmv_db_minus_ads",
        "db_sales_gmv_kzt",
        "bid_cpc_2",
        "db_asp_kzt",
        "db_orders_count",
        "ads_cost_per_db_order",
        "db_cogs",
        "db_profit_est_kzt",
        "db_Unit_profit_%",
    ]
    assert product_df.columns.tolist() == expected_product_cols


def test_build_owner_workbook_persists_manual_bid_override(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    workbook = tmp_path / "owner.xlsx"
    csv_dir = tmp_path / "csv"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)

    summary1 = build_owner_workbook(
        ads_db=ads_db,
        app_db=app_db,
        workbook_path=workbook,
        csv_dir=csv_dir,
        history_start_date="2025-01-01",
        future_cutover_date="2026-02-01",
        strict_models={"line51", "line61", "suit-61"},
        store_code="ACMEWEAR",
    )
    assert summary1["product_rows"] >= 1

    sheet = pd.read_excel(workbook, sheet_name="campaign_product_daily")
    campaign_sheet = pd.read_excel(workbook, sheet_name="campaign_daily")
    campaign_id_str = sheet["campaign_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    target = (campaign_id_str == "2545773") & (sheet["date"].astype(str) == "2025-01-04")
    assert target.any()
    sheet.loc[target, "bid_cpc"] = 123.0
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        campaign_sheet.to_excel(writer, sheet_name="campaign_daily", index=False)
        sheet.to_excel(writer, sheet_name="campaign_product_daily", index=False)

    summary2 = build_owner_workbook(
        ads_db=ads_db,
        app_db=app_db,
        workbook_path=workbook,
        csv_dir=csv_dir,
        history_start_date="2025-01-01",
        future_cutover_date="2026-02-01",
        strict_models={"line51", "line61", "suit-61"},
        store_code="ACMEWEAR",
    )
    assert summary2["bid_override_upserts"] >= 1

    sheet2 = pd.read_excel(workbook, sheet_name="campaign_product_daily")
    campaign_id_str2 = sheet2["campaign_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    target2 = (campaign_id_str2 == "2545773") & (sheet2["date"].astype(str) == "2025-01-04")
    assert target2.any()
    row = sheet2[target2].iloc[0]
    assert float(row["bid_cpc"]) == 123.0
    assert float(row["bid_cpc_2"]) == 70.0
    assert row["bid_cpc_source"] == "manual_override"
