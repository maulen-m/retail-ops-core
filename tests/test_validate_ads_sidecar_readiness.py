from __future__ import annotations

import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import pytest

from scripts.validate_ads_sidecar_readiness import (
    AdsReadinessError,
    validate_ads_sidecar_readiness,
)


def _init_db(
    path: Path,
    *,
    mapped_rows: int,
    unmapped_rows: int,
    campaign_date: str = "2026-03-04",
    refresh_end: str = "2026-03-04",
    include_refresh: bool = True,
) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            merchant_id TEXT,
            store_code TEXT NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            product_rows_total INTEGER NOT NULL DEFAULT 0,
            status TEXT,
            notes_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE ads_campaign_product_daily (
            date TEXT,
            store_code TEXT,
            campaign_id TEXT,
            campaign_name TEXT,
            sku_key TEXT,
            cost_kzt REAL,
            impressions INTEGER,
            clicks INTEGER,
            source_run_id TEXT,
            coverage_status TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code, campaign_id, sku_key)
        );
        """
    )
    if include_refresh:
        conn.execute(
            """
            INSERT INTO ads_source_refresh_runs
            (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
            VALUES ('run-1', '2026-03-04T01:00:00Z', '2026-03-04T01:05:00Z', '30137883', 'UNIVERSAL', '2026-02-04', ?, ?, 'SUCCESS')
            """,
            (refresh_end, mapped_rows + unmapped_rows),
        )
    for idx in range(mapped_rows):
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily
            (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
            VALUES (?, 'UNIVERSAL', ?, 'Mapped', ?, 100.0, 10, 1, 'run-1', 'COVERED')
            """,
            (campaign_date, f"C-M-{idx}", f"SKU_M_{idx}"),
        )
    for idx in range(unmapped_rows):
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily
            (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
            VALUES (?, 'UNIVERSAL', ?, 'Unmapped', ?, 100.0, 10, 1, 'run-1', 'UNKNOWN')
            """,
            (campaign_date, f"C-U-{idx}", f"SKU_U_{idx}"),
        )
    conn.executescript(
        """
        CREATE TABLE ads_spend_sidecar_daily (
            date TEXT,
            store_code TEXT,
            mapped_cost_kzt REAL,
            unmapped_cost_kzt REAL,
            total_cost_kzt REAL,
            mapped_rows INTEGER,
            unmapped_rows INTEGER,
            mapping_coverage_pct REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-03-03', 'UNIVERSAL', 0, 10000, 10000, 0, 100, 0)
        """,
    )
    conn.commit()
    conn.close()


def test_validate_ads_sidecar_readiness_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, mapped_rows=9, unmapped_rows=1)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        min_mapping_coverage_pct=85.0,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["error_code"] is None
    assert report["ads_payload"]["mapping_coverage_pct"] >= 85.0


def test_validate_ads_sidecar_readiness_live_mode_warns_when_source_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, mapped_rows=9, unmapped_rows=1)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("stale", encoding="utf-8")
    stale_epoch = time.time() - (90 * 3600)
    os.utime(ads_source, (stale_epoch, stale_epoch))
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        max_age_hours=24.0,
        readiness_mode="live",
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["warnings"] == ["ADS_SOURCE_STALE"]


def test_validate_ads_sidecar_readiness_fails_on_low_mapping_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, mapped_rows=4, unmapped_rows=6)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        min_mapping_coverage_pct=85.0,
        strict=False,
    )
    assert report["status"] == "FAIL"
    assert report["error_code"] == "ADS_MAPPING_COVERAGE_FAIL"


def test_validate_ads_sidecar_readiness_fails_when_canonical_tables_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    with pytest.raises(AdsReadinessError):
        validate_ads_sidecar_readiness(
            db_path=db_path,
            as_of=date(2026, 3, 4),
            output_root=tmp_path / "out",
            strict=True,
        )


def test_validate_ads_sidecar_readiness_fails_on_stale_canonical_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, mapped_rows=9, unmapped_rows=1, campaign_date="2026-02-20")
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["error_code"] == "ADS_CANONICAL_STALE"


def test_validate_ads_sidecar_readiness_fails_on_missing_refresh_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, mapped_rows=9, unmapped_rows=1, include_refresh=False)
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["error_code"] == "ADS_REFRESH_COVERAGE_MISSING"
