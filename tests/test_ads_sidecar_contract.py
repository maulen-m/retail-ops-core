from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from core.ads.sidecar_contract import resolve_ads_db_path, validate_ads_source


def test_resolve_ads_db_path_fails_closed_when_env_path_missing(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing_ads.db"
    monkeypatch.setenv("AB_ADS_DB_PATH", str(missing))

    with pytest.raises(RuntimeError):
        resolve_ads_db_path(require_exists=True)


def test_validate_ads_source_flags_stale_file(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    ads_db.write_text("stub", encoding="utf-8")
    old_epoch = time.time() - (72 * 3600)
    os.utime(ads_db, (old_epoch, old_epoch))

    report = validate_ads_source(ads_db, max_age_hours=36)
    assert report["ok"] is False
    assert report["reason"] == "stale"


def test_validate_ads_source_passes_for_fresh_file(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    ads_db.write_text("stub", encoding="utf-8")

    report = validate_ads_source(ads_db, max_age_hours=36)
    assert report["ok"] is True
    assert report["reason"] == "ok"


def test_validate_ads_source_accepts_fresh_refresh_run_metadata_when_db_mtime_is_stale(
    tmp_path: Path,
) -> None:
    ads_db = tmp_path / "ads.db"
    conn = sqlite3.connect(ads_db)
    conn.execute(
        """
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            campaign_days_total INTEGER NOT NULL DEFAULT 0,
            product_rows_total INTEGER NOT NULL DEFAULT 0,
            download_failure_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end,
            campaign_days_total, product_rows_total, download_failure_count, status, notes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run_1",
            "2026-03-08T19:59:00+00:00",
            "2026-03-08T20:00:00+00:00",
            "761413",
            "30000001",
            "2026-01-01",
            "2026-02-28",
            0,
            0,
            0,
            "SUCCESS",
            "[]",
        ),
    )
    conn.commit()
    conn.close()

    old_epoch = 1773003600.0 - (72 * 3600)
    os.utime(ads_db, (old_epoch, old_epoch))

    report = validate_ads_source(
        ads_db,
        max_age_hours=36,
        now_ts_override=1773003600.0,
    )
    assert report["ok"] is True
    assert report["reason"] == "ok_refresh_run"
    assert report["freshness_source"] == "ads_source_refresh_runs.finished_at"


def test_validate_ads_source_rejects_failed_refresh_run_metadata(
    tmp_path: Path,
) -> None:
    ads_db = tmp_path / "ads.db"
    conn = sqlite3.connect(ads_db)
    conn.execute(
        """
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            merchant_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            campaign_days_total INTEGER NOT NULL DEFAULT 0,
            product_rows_total INTEGER NOT NULL DEFAULT 0,
            download_failure_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end,
            campaign_days_total, product_rows_total, download_failure_count, status, notes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run_1",
            "2026-03-08T19:59:00+00:00",
            "2026-03-08T20:00:00+00:00",
            "761413",
            "30000001",
            "2026-01-01",
            "2026-02-28",
            0,
            0,
            0,
            "FAILED",
            "[]",
        ),
    )
    conn.commit()
    conn.close()

    old_epoch = time.time() - (72 * 3600)
    os.utime(ads_db, (old_epoch, old_epoch))

    report = validate_ads_source(
        ads_db,
        max_age_hours=36,
        now_ts_override=time.time(),
    )
    assert report["ok"] is False
    assert report["reason"] == "stale"
