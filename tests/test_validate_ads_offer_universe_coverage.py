from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
import json
import pandas as pd

import scripts.validate_ads_offer_universe_coverage as ads_mod
from scripts.validate_ads_offer_universe_coverage import (
    AdsOfferCoverageError,
    validate_ads_offer_universe_coverage,
)


def _write_stores_yaml(path: Path) -> None:
    payload = {
        "stores": {
            "ACMEWEAR": {"merchant_uid": "30137883"},
            "UNIVERSAL": {"merchant_uid": "30000001"},
        }
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _write_ads_scope_yaml(path: Path) -> None:
    payload = {
        "version": 1,
        "default_active": False,
        "stores": {
            "ACMEWEAR": {"windows": [{"start": "2024-01-01", "active": True}]},
            "UNIVERSAL": {
                "windows": [
                    {"start": "2024-01-01", "end": "2026-02-21", "active": True},
                    {"start": "2026-02-22", "active": False},
                ]
            },
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_acmewear_active_scope_yaml(path: Path) -> None:
    payload = {
        "version": 1,
        "default_active": False,
        "stores": {
            "ACMEWEAR": {"windows": [{"start": "2024-01-01", "active": True}]},
            "UNIVERSAL": {"windows": [{"start": "2024-01-01", "active": False}]},
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_storeb_scope_yaml(path: Path, *, coverage_mode: str) -> None:
    payload = {
        "version": 1,
        "default_active": False,
        "stores": {
            "STOREB": {
                "windows": [
                    {
                        "start": "2026-03-08",
                        "active": True,
                        "coverage_mode": coverage_mode,
                    }
                ]
            },
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_ads_gap_quarantine_yaml(path: Path) -> None:
    payload = {
        "version": 1,
        "quarantines": [
            {
                "order_id": "HUS_ORDER",
                "sale_date": "2026-01-05",
                "store_code": "ACMEWEAR",
                "sku_key": "SKU_HUS",
                "reason": "missing_source_evidence",
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


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


def _insert_canonical_ads(
    conn: sqlite3.Connection,
    *,
    day: str = "2026-01-05",
    store_code: str = "ACMEWEAR",
    sku_key: str = "SKU_A",
    cost_kzt: float = 100.0,
    coverage_status: str = "COVERED",
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO ads_source_refresh_runs
        (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
        VALUES ('run-1', '2026-01-31T01:00:00Z', '2026-01-31T01:05:00Z', '30137883', ?, '2026-01-01', '2026-01-31', 1, 'SUCCESS')
        """,
        (store_code,),
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily
        (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
        VALUES (?, ?, 'C1', 'Campaign', ?, ?, 10, 1, 'run-1', ?)
        """,
        (day, store_code, sku_key, cost_kzt, coverage_status),
    )


def _seed_db(db_path: Path, *, with_ads: bool, mapped: bool = True) -> None:
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
            "INSERT INTO view_sales_line_truth (order_id, sale_date, store_code, sku_key, net_rev_kzt) VALUES ('1','2026-01-05','ACMEWEAR','SKU_A',1000)"
        )
        conn.execute(
            "INSERT INTO view_sales_line_truth (order_id, sale_date, store_code, sku_key, net_rev_kzt) VALUES ('2','2026-01-05','UNIVERSAL','SKU_U',1500)"
        )
        if with_ads:
            _insert_canonical_ads(
                conn,
                coverage_status="COVERED" if mapped else "UNKNOWN",
            )
        conn.commit()
    finally:
        conn.close()


def _seed_storeb_scope_db(
    db_path: Path,
    *,
    sales: list[tuple[str, str, str, str, float]],
    ads_rows: list[tuple[str, str, str, str, float, str]],
) -> None:
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
        conn.executemany(
            """
            INSERT INTO view_sales_line_truth
            (order_id, sale_date, store_code, sku_key, net_rev_kzt)
            VALUES (?, ?, ?, ?, ?)
            """,
            sales,
        )
        for day, campaign_id, sku_key, store_code, cost_kzt, coverage_status in ads_rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO ads_source_refresh_runs
                (run_id, started_at, finished_at, merchant_id, store_code, date_start, date_end, product_rows_total, status)
                VALUES (?, '2026-03-31T01:00:00Z', '2026-03-31T01:05:00Z', '30000001', ?, '2026-03-01', '2026-03-31', 1, 'SUCCESS')
                """,
                (f"run-{store_code}", store_code),
            )
            conn.execute(
                """
                INSERT INTO ads_campaign_product_daily
                (date, store_code, campaign_id, campaign_name, sku_key, cost_kzt, impressions, clicks, source_run_id, coverage_status)
                VALUES (?, ?, ?, 'Campaign', ?, ?, 10, 1, ?, ?)
                """,
                (day, store_code, campaign_id, sku_key, cost_kzt, f"run-{store_code}", coverage_status),
            )
        conn.commit()
    finally:
        conn.close()


def test_validate_ads_offer_universe_coverage_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _seed_db(db, with_ads=True)
    payload = validate_ads_offer_universe_coverage(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
    assert "ads_spend_reality_by_month_store_csv" in payload["outputs"]


def test_validate_ads_offer_universe_coverage_canonical_wins_over_legacy_sidecar(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _seed_db(db, with_ads=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            CREATE TABLE ads_spend_sidecar_daily_sku (
                date TEXT,
                store_code TEXT,
                sku_key TEXT,
                mapped INTEGER,
                ads_cost_kzt REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO ads_spend_sidecar_daily_sku VALUES ('2026-01-05','30137883','SKU_OTHER',1,999.0)"
        )
        conn.commit()
    finally:
        conn.close()

    payload = validate_ads_offer_universe_coverage(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=tmp_path / "out",
    )

    spend = pd.read_csv(payload["outputs"]["ads_spend_reality_by_month_store_csv"])
    assert payload["status"] == "PASS"
    assert spend.iloc[0]["ads_kzt"] == pytest.approx(100.0)


def test_validate_ads_offer_universe_coverage_strict_fail(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, with_ads=True, mapped=False)
    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            output_dir=tmp_path / "out",
        )


def test_all_sold_skus_mode_fails_when_sold_sku_lacks_ads_coverage(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_storeb_scope_yaml(ads_scope, coverage_mode="all_sold_skus")
    _seed_storeb_scope_db(
        db,
        sales=[
            ("1", "2026-03-10", "STOREB", "SKU_ADVERTISED", 1000.0),
            ("2", "2026-03-10", "STOREB", "SKU_NOT_ADVERTISED", 1500.0),
        ],
        ads_rows=[
            ("2026-03-10", "C1", "SKU_ADVERTISED", "STOREB", 100.0, "COVERED"),
        ],
    )

    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-03-01",
            end="2026-03-31",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            ads_scope_config=ads_scope,
            output_dir=tmp_path / "out",
        )


def test_advertised_products_only_mode_ignores_non_advertised_sold_skus(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_storeb_scope_yaml(ads_scope, coverage_mode="advertised_products_only")
    _seed_storeb_scope_db(
        db,
        sales=[
            ("1", "2026-03-10", "STOREB", "SKU_NOT_ADVERTISED", 1500.0),
        ],
        ads_rows=[
            ("2026-03-10", "C1", "SKU_ADVERTISED", "STOREB", 100.0, "COVERED"),
        ],
    )

    payload = validate_ads_offer_universe_coverage(
        start="2026-03-01",
        end="2026-03-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=tmp_path / "out",
    )

    assert payload["status"] == "PASS"
    assert payload["missing_sold_offers"] == 0


def test_positive_spend_advertised_product_with_unresolved_mapping_fails(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_storeb_scope_yaml(ads_scope, coverage_mode="advertised_products_only")
    _seed_storeb_scope_db(
        db,
        sales=[
            ("1", "2026-03-10", "STOREB", "SKU_NOT_ADVERTISED", 1500.0),
        ],
        ads_rows=[
            ("2026-03-10", "11391711b", "11391711b", "STOREB", 500.0, "BLOCKED_CONFLICT"),
        ],
    )

    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-03-01",
            end="2026-03-31",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            ads_scope_config=ads_scope,
            output_dir=tmp_path / "out",
        )
    report = json.loads((tmp_path / "out" / "ads_offer_universe_report.json").read_text())
    assert report["unmapped_positive_spend_ads"] == 1


def test_advertised_products_only_still_requires_monthly_spend_reality(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_storeb_scope_yaml(ads_scope, coverage_mode="advertised_products_only")
    _seed_storeb_scope_db(
        db,
        sales=[
            ("1", "2026-03-10", "STOREB", "SKU_NOT_ADVERTISED", 1500.0),
        ],
        ads_rows=[],
    )

    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-03-01",
            end="2026-03-31",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            ads_scope_config=ads_scope,
            output_dir=tmp_path / "out",
        )
    report = json.loads((tmp_path / "out" / "ads_offer_universe_report.json").read_text())
    assert report["failing_month_store_pairs"] == 0
    assert report["spend_reality_fail_pairs"] == 1


def test_non_ads_store_does_not_fail_spend_reality(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _seed_db(db, with_ads=True)
    payload = validate_ads_offer_universe_coverage(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_ads_offer_universe_coverage_webui_uses_effective_db_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ledger = tmp_path / "ledger"
    out_dir = tmp_path / "out"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    ledger.mkdir()
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _seed_db(db, with_ads=True)

    monkeypatch.setattr(
        ads_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 1},
        ),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ledger_root": str(ledger.resolve()),
                "period": {"start": "2026-01-01", "end": "2026-01-31"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 1,
            }
        ),
        encoding="utf-8",
    )

    payload = validate_ads_offer_universe_coverage(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        truth_source="webui_archive",
        ledger_root=ledger,
        as_of="2026-03-07",
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=out_dir,
    )
    assert payload["status"] == "PASS"
    assert payload["truth_errors"] == []


def test_validate_ads_offer_universe_coverage_ignores_inactive_store_after_stop_date(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_ads_scope_yaml(ads_scope)
    conn = sqlite3.connect(db)
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
            "INSERT INTO view_sales_line_truth VALUES ('1','2026-02-25','UNIVERSAL','SKU_U',1500.0)"
        )
        conn.commit()
    finally:
        conn.close()

    payload = validate_ads_offer_universe_coverage(
        start="2026-02-01",
        end="2026-02-29",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_ads_offer_universe_coverage_still_requires_historical_scope_before_stop_date(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    _write_stores_yaml(stores)
    _write_ads_scope_yaml(ads_scope)
    conn = sqlite3.connect(db)
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
            "INSERT INTO view_sales_line_truth VALUES ('1','2026-02-21','UNIVERSAL','SKU_U',1500.0)"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-02-01",
            end="2026-02-29",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            ads_scope_config=ads_scope,
            output_dir=tmp_path / "out",
        )


def test_validate_ads_offer_universe_coverage_applies_exact_gap_quarantine(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    quarantine = tmp_path / "ads_source_gap_quarantine.yaml"
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _write_ads_gap_quarantine_yaml(quarantine)

    conn = sqlite3.connect(db)
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
            "INSERT INTO view_sales_line_truth VALUES ('HUS_ORDER','2026-01-05','ACMEWEAR','SKU_HUS',1500.0)"
        )
        conn.commit()
    finally:
        conn.close()

    payload = validate_ads_offer_universe_coverage(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        min_coverage=1.0,
        max_ads_to_net_rev_ratio=0.8,
        db_path=db,
        stores_config=stores,
        ads_scope_config=ads_scope,
        gap_quarantine_config=quarantine,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
    assert payload["quarantined_sold_offers"] == 1


def test_validate_ads_offer_universe_coverage_does_not_quarantine_partial_match(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    ads_scope = tmp_path / "ads_active_scope.yaml"
    quarantine = tmp_path / "ads_source_gap_quarantine.yaml"
    _write_stores_yaml(stores)
    _write_acmewear_active_scope_yaml(ads_scope)
    _write_ads_gap_quarantine_yaml(quarantine)

    conn = sqlite3.connect(db)
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
            "INSERT INTO view_sales_line_truth VALUES ('HUS_ORDER','2026-01-06','ACMEWEAR','SKU_HUS',1500.0)"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(AdsOfferCoverageError):
        validate_ads_offer_universe_coverage(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            min_coverage=1.0,
            max_ads_to_net_rev_ratio=0.8,
            db_path=db,
            stores_config=stores,
            ads_scope_config=ads_scope,
            gap_quarantine_config=quarantine,
            output_dir=tmp_path / "out",
        )
