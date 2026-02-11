from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.kaspi_ads_elasticity import analyze_elasticity


def _seed_ads_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE campaign_product_daily_current (
                date TEXT,
                merchant_id TEXT,
                campaign_id TEXT,
                sku_key TEXT,
                bid_cpc REAL,
                clicks INTEGER,
                orders_total INTEGER,
                gmv REAL,
                cost REAL,
                PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO campaign_product_daily_current
            (date, merchant_id, campaign_id, sku_key, bid_cpc, clicks, orders_total, gmv, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-08", "759051", "2380614", "SKU-A", 30.0, 100, 10, 10000.0, 1000.0),
                ("2026-02-09", "759051", "2380614", "SKU-A", 30.0, 110, 9, 9800.0, 980.0),
                ("2026-02-10", "759051", "2380614", "SKU-A", 60.0, 150, 12, 12000.0, 2500.0),
                ("2026-02-11", "759051", "2380614", "SKU-A", 60.0, 155, 11, 11800.0, 2450.0),
            ],
        )


def _seed_app_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE fact_sales (
                order_date TEXT,
                sku_key TEXT,
                quantity INTEGER,
                sell_price_kzt REAL,
                profit_line REAL,
                cogs_line REAL
            )
            """
        )
        # Margin ~= 30%
        conn.executemany(
            """
            INSERT INTO fact_sales
            (order_date, sku_key, quantity, sell_price_kzt, profit_line, cogs_line)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-02-08", "SKU-A", 1, 1000.0, 300.0, 700.0),
                ("2026-02-09", "SKU-A", 1, 1000.0, 300.0, 700.0),
            ],
        )


def test_analyze_elasticity_recommends_profit_best_bid(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    _seed_ads_db(ads_db)
    _seed_app_db(app_db)

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.25,
    )

    assert result["level_rows"] == 2
    assert result["transition_rows"] == 1
    assert result["recommendation_rows"] == 1

    rec = result["recommendations"][0]
    assert rec["recommended_bid_cpc"] == 30.0
    assert rec["expected_profit_est_kzt"] > 0


def test_analyze_elasticity_falls_back_to_default_margin(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    app_db = tmp_path / "app.db"
    out_dir = tmp_path / "out"
    _seed_ads_db(ads_db)
    # App DB without fact_sales table -> fallback margin
    with sqlite3.connect(app_db):
        pass

    result = analyze_elasticity(
        ads_db=ads_db,
        app_db=app_db,
        out_dir=out_dir,
        since="2026-02-01",
        until="2026-02-10",
        min_days=1,
        default_margin_pct=0.2,
    )

    assert result["level_rows"] == 2
    assert result["economics_rows"] == 0
    assert result["recommendation_rows"] == 1
