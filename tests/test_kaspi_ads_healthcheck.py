from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scripts.kaspi_ads_healthcheck import run_healthcheck


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE hourly_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_at TEXT NOT NULL,
            snapshot_hour INTEGER NOT NULL,
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE hourly_reconciliation (
            date TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            metric TEXT NOT NULL,
            hourly_total REAL NOT NULL,
            daily_total REAL NOT NULL,
            pct_diff REAL NOT NULL,
            within_tolerance INTEGER NOT NULL,
            tolerance_pct REAL NOT NULL,
            computed_at TEXT NOT NULL
        )
        """
    )


def _insert_snapshot(conn: sqlite3.Connection, *, merchant_id: str, snapshot_at: datetime) -> None:
    conn.execute(
        """
        INSERT INTO hourly_snapshot (snapshot_at, snapshot_hour, date, merchant_id, campaign_id, sku_key)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_at.isoformat(),
            snapshot_at.hour,
            snapshot_at.date().isoformat(),
            merchant_id,
            "C-1",
            "SKU-1",
        ),
    )


def _insert_recon_rows(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    now: datetime,
    hours_ago_start: int,
    count: int,
    pct_diff: float,
    within_tolerance: int,
) -> None:
    rows = []
    for idx in range(count):
        ts = now - timedelta(hours=hours_ago_start + idx)
        rows.append(
            (
                ts.date().isoformat(),
                merchant_id,
                "C-1",
                "SKU-1",
                "clicks",
                10.0,
                10.0,
                pct_diff,
                within_tolerance,
                5.0,
                ts.isoformat(),
            )
        )
    conn.executemany(
        """
        INSERT INTO hourly_reconciliation (
            date, merchant_id, campaign_id, sku_key, metric,
            hourly_total, daily_total, pct_diff, within_tolerance, tolerance_pct, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_healthcheck_fails_on_stale_store(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)
    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(conn, merchant_id="759051", snapshot_at=now - timedelta(minutes=30))
        _insert_snapshot(conn, merchant_id="761413", snapshot_at=now - timedelta(hours=4))
        _insert_recon_rows(conn, merchant_id="759051", now=now, hours_ago_start=1, count=5, pct_diff=2.0, within_tolerance=1)

        result = run_healthcheck(
            conn,
            store_targets=[
                {"store_code": "ACMEWEAR", "merchant_id": "759051"},
                {"store_code": "UNIVERSAL", "merchant_id": "761413"},
            ],
            now_local=now,
            max_stale_hours=2.0,
        )

        assert result["ok"] is False
        assert result["exit_code"] == 1
        assert any("UNIVERSAL" in msg for msg in result["failures"])


def test_healthcheck_fails_on_reconciliation_regression(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)
    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(conn, merchant_id="759051", snapshot_at=now - timedelta(minutes=15))
        _insert_snapshot(conn, merchant_id="761413", snapshot_at=now - timedelta(minutes=10))
        # Previous window: good
        _insert_recon_rows(conn, merchant_id="759051", now=now, hours_ago_start=25, count=10, pct_diff=1.0, within_tolerance=1)
        # Recent window: significantly worse
        _insert_recon_rows(conn, merchant_id="759051", now=now, hours_ago_start=1, count=10, pct_diff=35.0, within_tolerance=0)

        result = run_healthcheck(
            conn,
            store_targets=[
                {"store_code": "ACMEWEAR", "merchant_id": "759051"},
                {"store_code": "UNIVERSAL", "merchant_id": "761413"},
            ],
            now_local=now,
            max_stale_hours=2.0,
            recon_window_hours=24,
            max_recon_fail_rate=0.8,
            max_recon_avg_pct_diff=40.0,
            max_recon_fail_rate_regression=0.2,
            max_recon_avg_pct_diff_regression=10.0,
        )

        assert result["ok"] is False
        assert result["exit_code"] == 1
        assert any("regression" in msg.lower() for msg in result["failures"])


def test_healthcheck_passes_for_fresh_and_stable_data(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)
    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(conn, merchant_id="759051", snapshot_at=now - timedelta(minutes=20))
        _insert_snapshot(conn, merchant_id="761413", snapshot_at=now - timedelta(minutes=15))
        _insert_recon_rows(conn, merchant_id="759051", now=now, hours_ago_start=25, count=10, pct_diff=4.0, within_tolerance=1)
        _insert_recon_rows(conn, merchant_id="759051", now=now, hours_ago_start=1, count=10, pct_diff=4.2, within_tolerance=1)

        result = run_healthcheck(
            conn,
            store_targets=[
                {"store_code": "ACMEWEAR", "merchant_id": "759051"},
                {"store_code": "UNIVERSAL", "merchant_id": "761413"},
            ],
            now_local=now,
            max_stale_hours=2.0,
            recon_window_hours=24,
            max_recon_fail_rate=0.5,
            max_recon_avg_pct_diff=10.0,
            max_recon_fail_rate_regression=0.2,
            max_recon_avg_pct_diff_regression=2.0,
        )

        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert result["failures"] == []
