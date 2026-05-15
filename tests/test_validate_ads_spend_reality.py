from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.validate_ads_spend_reality import (
    AdsSpendRealityError,
    validate_ads_spend_reality,
)


def _write_stores_yaml(path: Path) -> None:
    payload = {
        "stores": {
            "ACMEWEAR": {"merchant_uid": "30137883"},
        }
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _create_canonical_ads_tables(conn: sqlite3.Connection) -> None:
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


def _seed_db(db_path: Path, *, ads_cost: float | None, mapped: int = 1) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                net_rev_kzt REAL
            )
            """
        )
        _create_canonical_ads_tables(conn)
        conn.execute(
            "INSERT INTO view_sales_line_truth VALUES ('1','2026-01-05','ACMEWEAR','SKU_A',1000.0)"
        )
        if ads_cost is not None:
            conn.execute(
                """
                INSERT INTO ads_source_refresh_runs
                (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
                VALUES ('run-1', '2026-01-31T01:00:00Z', '2026-01-31T01:05:00Z', '30137883', 'ACMEWEAR', '2026-01-01', '2026-01-31', 1, 'SUCCESS')
                """
            )
            conn.execute(
                """
                INSERT INTO ads_campaign_product_daily
                (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
                VALUES ('2026-01-05', 'ACMEWEAR', 'C1', 'Campaign', 'SKU_A', ?, 10, 1, 'run-1', ?)
                """,
                (ads_cost, "COVERED" if mapped else "UNKNOWN"),
            )
        conn.commit()
    finally:
        conn.close()


def _write_gap_quarantine_yaml(path: Path) -> None:
    payload = {
        "version": 1,
        "quarantines": [
            {
                "order_id": "1",
                "sale_date": "2026-01-05",
                "store_code": "ACMEWEAR",
                "sku_key": "SKU_A",
                "reason": "missing_source_evidence",
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_validate_ads_spend_reality_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=100.0)
    payload = validate_ads_spend_reality(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        max_ads_to_net_rev_ratio=0.8,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
    assert "_ads_spend_reality_offer_input" in str(
        payload["source_offer_coverage_report_json"]
    )


def test_validate_ads_spend_reality_fails_ratio_out_of_band(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=900.0)
    with pytest.raises(AdsSpendRealityError):
        validate_ads_spend_reality(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            stores_config=stores,
            max_ads_to_net_rev_ratio=0.8,
            output_dir=tmp_path / "out",
        )


def test_validate_ads_spend_reality_strict_fail_missing_ads(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=0.0)
    with pytest.raises(AdsSpendRealityError):
        validate_ads_spend_reality(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            stores_config=stores,
            max_ads_to_net_rev_ratio=0.8,
            output_dir=tmp_path / "out",
        )


def test_validate_ads_spend_reality_passes_through_gap_quarantine(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    quarantine = tmp_path / "ads_source_gap_quarantine.yaml"
    _write_stores_yaml(stores)
    _write_gap_quarantine_yaml(quarantine)
    _seed_db(db, ads_cost=0.0)
    payload = validate_ads_spend_reality(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        max_ads_to_net_rev_ratio=0.8,
        gap_quarantine_config=quarantine,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
