from __future__ import annotations

import sqlite3
from pathlib import Path
from textwrap import dedent

from core.ads.canonical_truth import (
    load_daily_sku_ads,
    load_daily_store_ads,
    load_monthly_store_ads,
    load_readiness_metadata,
)


def _init_canonical_db(path: Path) -> None:
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
            status TEXT NOT NULL,
            notes_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE ads_campaign_product_daily (
            date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT,
            sku_key TEXT NOT NULL DEFAULT '',
            cost_kzt REAL NOT NULL DEFAULT 0,
            impressions INTEGER,
            clicks INTEGER,
            source_run_id TEXT,
            coverage_status TEXT NOT NULL DEFAULT 'UNKNOWN',
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (date, store_code, campaign_id, sku_key)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs
        (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
        VALUES ('run-1', '2026-01-31T01:00:00Z', '2026-01-31T01:05:00Z', '30137883', 'ACMEWEAR', '2026-01-01', '2026-01-31', 3, 'SUCCESS')
        """
    )
    conn.executemany(
        """
        INSERT INTO ads_campaign_product_daily
        (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-01-05", "ACMEWEAR", "C1", "Covered", "SKU_A", 100.0, 10, 1, "run-1", "COVERED"),
            ("2026-01-06", "ACMEWEAR", "C1", "No spend", "SKU_B", 0.0, 0, 0, "run-1", "NO_SPEND_VERIFIED"),
            ("2026-01-07", "ACMEWEAR", "C2", "Blocked", "SKU_C", 50.0, 5, 1, "run-1", "UNKNOWN"),
        ],
    )
    conn.commit()
    conn.close()


def test_canonical_daily_sku_projection_maps_covered_and_no_spend(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_canonical_db(db)

    rows = load_daily_sku_ads(db_path=db, start="2026-01-01", end="2026-01-31")

    assert list(rows["store_code"].unique()) == ["ACMEWEAR"]
    by_sku = {row["sku_key"]: row for row in rows.to_dict("records")}
    assert by_sku["SKU_A"]["mapped"] == 1
    assert by_sku["SKU_A"]["ads_kzt"] == 100.0
    assert by_sku["SKU_B"]["mapped"] == 1
    assert by_sku["SKU_B"]["ads_kzt"] == 0.0
    assert by_sku["SKU_C"]["mapped"] == 0


def test_canonical_store_totals_and_readiness_metadata(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_canonical_db(db)

    daily = load_daily_store_ads(db_path=db, start="2026-01-01", end="2026-01-31")
    monthly = load_monthly_store_ads(db_path=db, start="2026-01-01", end="2026-01-31")
    readiness = load_readiness_metadata(db_path=db, start="2026-01-01", end="2026-01-31")

    assert daily["total_cost_kzt"].sum() == 150.0
    assert monthly.iloc[0]["total_cost_kzt"] == 150.0
    assert monthly.iloc[0]["mapped_rows"] == 2
    assert monthly.iloc[0]["unmapped_rows"] == 1
    assert readiness["canonical_available"] is True
    assert readiness["campaign_rows"] == 3
    assert readiness["refresh_rows"] == 1
    assert readiness["campaign_max_date"] == "2026-01-07"
    assert readiness["refresh_max_date_end"] == "2026-01-31"


def test_effective_cost_multiplier_is_applied_in_canonical_reader(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    policy = tmp_path / "policy.yaml"
    _init_canonical_db(db)
    policy.write_text(
        dedent(
            """
            default_multiplier: 1.2
            date_overrides:
              - start_date: "2026-01-07"
                end_date: "2026-01-07"
                multiplier: 2.0
            """
        ).strip(),
        encoding="utf-8",
    )

    daily = load_daily_store_ads(
        db_path=db,
        start="2026-01-01",
        end="2026-01-31",
        effective_cost_mode=True,
        effective_policy_path=policy,
    )

    costs = {row["ads_date"]: row["total_cost_kzt"] for row in daily.to_dict("records")}
    assert costs["2026-01-05"] == 120.0
    assert costs["2026-01-06"] == 0.0
    assert costs["2026-01-07"] == 100.0
