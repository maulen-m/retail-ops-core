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


def _seed_sidecar_db(
    path: Path,
    *,
    mapped_rows: int,
    unmapped_rows: int,
    total_cost_kzt: float = 1000.0,
) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ads_spend_sidecar_daily (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            mapped_cost_kzt REAL NOT NULL DEFAULT 0,
            unmapped_cost_kzt REAL NOT NULL DEFAULT 0,
            total_cost_kzt REAL NOT NULL DEFAULT 0,
            mapped_rows INTEGER NOT NULL DEFAULT 0,
            unmapped_rows INTEGER NOT NULL DEFAULT 0,
            mapping_coverage_pct REAL NOT NULL DEFAULT 0
        );
        """
    )
    mapped_cost = total_cost_kzt if unmapped_rows == 0 else round(total_cost_kzt * 0.4, 2)
    unmapped_cost = round(total_cost_kzt - mapped_cost, 2)
    coverage = (
        round((mapped_rows / (mapped_rows + unmapped_rows)) * 100.0, 2)
        if (mapped_rows + unmapped_rows)
        else 0.0
    )
    conn.execute(
        """
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-03-03', 'ACMEWEAR', ?, ?, ?, ?, ?, ?)
        """,
        (mapped_cost, unmapped_cost, total_cost_kzt, mapped_rows, unmapped_rows, coverage),
    )
    conn.commit()
    conn.close()


def test_validate_ads_sidecar_readiness_live_mode_passes_with_stale_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_sidecar_db(db_path, mapped_rows=9, unmapped_rows=0)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("stale", encoding="utf-8")
    stale_epoch = time.time() - (90 * 3600)
    os.utime(ads_source, (stale_epoch, stale_epoch))
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        readiness_mode="live",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["readiness_mode"] == "live"
    assert report["ads_source_status"]["reason"] == "stale"
    assert report["ads_payload"]["status"] == "available"
    assert report["ads_payload"]["reason"] == "sidecar_runtime_ok"
    assert report["warnings"] == ["ADS_SOURCE_STALE"]


def test_validate_ads_sidecar_readiness_apply_mode_fails_with_stale_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_sidecar_db(db_path, mapped_rows=9, unmapped_rows=0)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("stale", encoding="utf-8")
    stale_epoch = time.time() - (90 * 3600)
    os.utime(ads_source, (stale_epoch, stale_epoch))
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    with pytest.raises(AdsReadinessError):
        validate_ads_sidecar_readiness(
            db_path=db_path,
            as_of=date(2026, 3, 4),
            output_root=tmp_path / "out",
            readiness_mode="apply",
            strict=True,
        )


def test_validate_ads_sidecar_readiness_live_mode_still_fails_on_low_mapping_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_sidecar_db(db_path, mapped_rows=4, unmapped_rows=6)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("stale", encoding="utf-8")
    stale_epoch = time.time() - (90 * 3600)
    os.utime(ads_source, (stale_epoch, stale_epoch))
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = validate_ads_sidecar_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        readiness_mode="live",
        min_mapping_coverage_pct=85.0,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["error_code"] == "ADS_MAPPING_COVERAGE_FAIL"
