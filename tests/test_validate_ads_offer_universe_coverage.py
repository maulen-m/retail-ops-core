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
            "INSERT INTO view_sales_line_truth (order_id, sale_date, store_code, sku_key, net_rev_kzt) VALUES ('1','2026-01-05','ACMEWEAR','SKU_A',1000)"
        )
        conn.execute(
            "INSERT INTO view_sales_line_truth (order_id, sale_date, store_code, sku_key, net_rev_kzt) VALUES ('2','2026-01-05','UNIVERSAL','SKU_U',1500)"
        )
        if with_ads:
            conn.execute(
                "INSERT INTO ads_spend_sidecar_daily_sku (date, store_code, sku_key, mapped, ads_cost_kzt) VALUES ('2026-01-05','30137883','SKU_A',?,100)",
                (1 if mapped else 0,),
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
