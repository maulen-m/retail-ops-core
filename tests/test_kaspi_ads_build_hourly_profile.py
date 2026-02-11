from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.kaspi_ads_build_hourly_profile import (
    build_hourly_profile_and_reconciliation,
    ensure_profile_schema,
)
from scripts.kaspi_ads_hourly_snapshot import ensure_schema as ensure_hourly_schema


def _seed_hourly_delta(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO hourly_delta (
            date, hour_start, hour_end, merchant_id, campaign_id, sku_key,
            bid_cpc, views_delta, clicks_delta, cost_delta, gmv_delta,
            orders_delta, favorites_delta, carts_delta, delta_method, is_reset_anomaly, snapshot_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "2026-02-10", 9, 10, "759051", "2380614", "19796919b",
                70.0, 120, 12, 600.0, 2200.0,
                2, 0, 0, "sequential", 0, "2026-02-10T10:05:00+05:00",
            ),
            (
                "2026-02-10", 10, 11, "759051", "2380614", "19796919b",
                70.0, 80, 8, 400.0, 1800.0,
                1, 0, 0, "sequential", 0, "2026-02-10T11:05:00+05:00",
            ),
        ],
    )


def _seed_daily(conn: sqlite3.Connection, *, clicks: int = 20) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_product_daily_current (
            date TEXT,
            merchant_id TEXT,
            campaign_id TEXT,
            sku_key TEXT,
            views INTEGER,
            clicks INTEGER,
            cost REAL,
            gmv REAL,
            orders_total INTEGER,
            PRIMARY KEY (date, merchant_id, campaign_id, sku_key)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO campaign_product_daily_current
        (date, merchant_id, campaign_id, sku_key, views, clicks, cost, gmv, orders_total)
        VALUES ('2026-02-10', '759051', '2380614', '19796919b', 200, ?, 1000.0, 4000.0, 3)
        """,
        (clicks,),
    )


def test_build_hourly_profile_and_reconciliation_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_hourly_schema(conn)
        ensure_profile_schema(conn)
        _seed_hourly_delta(conn)
        _seed_daily(conn, clicks=20)

        result = build_hourly_profile_and_reconciliation(conn, tolerance_pct=5.0)

        assert result["profile_rows"] == 2
        assert result["reconciliation_failures"] == 0

        profile_rows = conn.execute(
            "SELECT hour, pct_daily_clicks, classification FROM hourly_activity_profile ORDER BY hour"
        ).fetchall()
        assert len(profile_rows) == 2
        assert profile_rows[0][1] == 60.0
        assert profile_rows[1][1] == 40.0

        recon_failures = conn.execute(
            "SELECT COUNT(*) FROM hourly_reconciliation WHERE within_tolerance = 0"
        ).fetchone()[0]
        assert recon_failures == 0


def test_build_hourly_profile_and_reconciliation_detects_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_hourly_schema(conn)
        ensure_profile_schema(conn)
        _seed_hourly_delta(conn)
        _seed_daily(conn, clicks=30)

        result = build_hourly_profile_and_reconciliation(conn, tolerance_pct=5.0)

        assert result["reconciliation_failures"] > 0
        bad_click_row = conn.execute(
            """
            SELECT within_tolerance, pct_diff
            FROM hourly_reconciliation
            WHERE metric = 'clicks'
              AND date = '2026-02-10'
              AND campaign_id = '2380614'
              AND sku_key = '19796919b'
            """
        ).fetchone()
        assert bad_click_row is not None
        assert bad_click_row[0] == 0
        assert bad_click_row[1] > 5.0
