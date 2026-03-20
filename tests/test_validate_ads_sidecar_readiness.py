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


def _init_db(path: Path, *, mapped_rows: int, unmapped_rows: int) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date DATE,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity INTEGER,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT
        );
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
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-03-03', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 1, 2000, 6000, 4000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2000, 20, 0.8)"
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('SKU_A_M', 'SKU_A', 'M')"
    )
    conn.execute(
        """
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-03-03', 'UNIVERSAL', 900, 100, 1000, ?, ?, 0)
        """,
        (mapped_rows, unmapped_rows),
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
