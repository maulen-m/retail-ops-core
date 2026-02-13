from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from scripts.kaspi_ads_campaign_coverage_report import build_campaign_coverage_report


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


def _insert_snapshot(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    campaign_id: str,
    sku_key: str,
    snapshot_at: datetime,
) -> None:
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
            campaign_id,
            sku_key,
        ),
    )


def test_coverage_flags_missing_expected_campaigns(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)

    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(
            conn,
            merchant_id="761413",
            campaign_id="2566809",
            sku_key="SKU-A",
            snapshot_at=now - timedelta(minutes=20),
        )
        _insert_snapshot(
            conn,
            merchant_id="761413",
            campaign_id="2572822",
            sku_key="SKU-B",
            snapshot_at=now - timedelta(minutes=20),
        )

        report = build_campaign_coverage_report(
            conn,
            store_targets=[{"store_code": "UNIVERSAL", "merchant_id": "761413"}],
            expected_campaigns_by_store={"UNIVERSAL": {"2566809", "2572387", "2572822"}},
            now_local=now,
            lookback_hours=24,
            max_stale_hours=2.0,
        )

    store_report = report["stores"][0]
    assert store_report["store_code"] == "UNIVERSAL"
    assert store_report["rows_24h"] == 2
    assert set(store_report["campaign_ids_seen_24h"]) == {"2566809", "2572822"}
    assert store_report["missing_expected_campaign_ids"] == ["2572387"]


def test_coverage_marks_acmewear_rows_one_valid_when_expected_is_one(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)

    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(
            conn,
            merchant_id="759051",
            campaign_id="2380614",
            sku_key="19796919b",
            snapshot_at=now - timedelta(minutes=15),
        )

        report = build_campaign_coverage_report(
            conn,
            store_targets=[{"store_code": "ACMEWEAR", "merchant_id": "759051"}],
            expected_campaigns_by_store={"ACMEWEAR": {"2380614"}},
            now_local=now,
            lookback_hours=24,
            max_stale_hours=2.0,
        )

    store_report = report["stores"][0]
    assert store_report["rows_24h"] == 1
    assert store_report["acmewear_rows_one_status"] == "valid"
    assert "expected campaign count is 1" in store_report["acmewear_rows_one_note"].lower()


def test_coverage_marks_acmewear_rows_one_invalid_when_campaign_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    now = datetime(2026, 2, 14, 1, 30, 0)

    with sqlite3.connect(db_path) as conn:
        _seed_schema(conn)
        _insert_snapshot(
            conn,
            merchant_id="759051",
            campaign_id="2380614",
            sku_key="19796919b",
            snapshot_at=now - timedelta(minutes=15),
        )

        report = build_campaign_coverage_report(
            conn,
            store_targets=[{"store_code": "ACMEWEAR", "merchant_id": "759051"}],
            expected_campaigns_by_store={"ACMEWEAR": {"2380614", "2545773"}},
            now_local=now,
            lookback_hours=24,
            max_stale_hours=2.0,
        )

    store_report = report["stores"][0]
    assert store_report["rows_24h"] == 1
    assert store_report["acmewear_rows_one_status"] == "invalid"
    assert store_report["missing_expected_campaign_ids"] == ["2545773"]
    assert "missing expected campaigns" in store_report["acmewear_rows_one_note"].lower()
