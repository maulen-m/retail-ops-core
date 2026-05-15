from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import yaml

import scripts.build_north_star_owner_review as owner_review_mod
from scripts.build_north_star_owner_review import (
    NorthStarOwnerReviewError,
    build_north_star_owner_review,
)


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                units REAL,
                net_rev_kzt REAL,
                cogs_kzt REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE fact_cashflow_commitments (
                commit_date TEXT,
                commit_type TEXT,
                amount_kzt REAL
            )
            """
        )
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
            "INSERT INTO view_sales_line_truth VALUES ('1','2026-01-15','ACMEWEAR','SKU_A',1,1000,300)"
        )
        conn.execute(
            "INSERT INTO fact_cashflow_commitments VALUES ('2026-01-20','OPEX',200)"
        )
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
            VALUES ('2026-01-15', 'ACMEWEAR', 'C1', 'Campaign', 'SKU_A', 100.0, 10, 1, 'run-1', 'COVERED')
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_validation(validation_dir: Path, status: str) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "sales_truth_vs_crm_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
    ]:
        (validation_dir / name).write_text(json.dumps({"status": status}), encoding="utf-8")


def _write_webui_validation(validation_dir: Path, status: str) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "webui_truth_promotion_report.json",
        "webui_vs_db_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "order_status_audit_report.json",
    ]:
        (validation_dir / name).write_text(json.dumps({"status": status, "ok": status == "PASS"}), encoding="utf-8")


def _write_webui_fallback_validation(validation_dir: Path, *, workbook_status: str = "PASS") -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}),
        encoding="utf-8",
    )
    (validation_dir / "sales_against_workbook_report.json").write_text(
        json.dumps({"status": workbook_status, "ok": workbook_status == "PASS"}),
        encoding="utf-8",
    )
    for name in [
        "webui_vs_db_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "order_status_audit_report.json",
    ]:
        (validation_dir / name).write_text(json.dumps({"status": "PASS", "ok": True}), encoding="utf-8")


def _write_stores(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"stores": {"ACMEWEAR": {"merchant_uid": "30137883"}}}),
        encoding="utf-8",
    )


def _write_owner_flags(path: Path, decision_grade: bool) -> None:
    payload = {
        "monthly_totals": [
            {"sale_month": "2026-01", "decision_grade": decision_grade, "statusdate_coverage_pct": 100.0}
        ],
        "monthly_by_store": [
            {
                "sale_month": "2026-01",
                "store_code": "ACMEWEAR",
                "decision_grade": decision_grade,
                "statusdate_coverage_pct": 100.0,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_north_star_owner_review_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    validation = tmp_path / "validation"
    _write_validation(validation, "PASS")
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    owner = tmp_path / "owner.json"
    _write_owner_flags(owner, decision_grade=True)
    out = tmp_path / "out"
    payload = build_north_star_owner_review(
        as_of="2026-03-05",
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        truth_source="db",
        ledger_root=None,
        validation_dir=validation,
        owner_pnl_json=owner,
        output_dir=out,
    )
    assert payload["status"] == "PASS"
    monthly = pd.read_csv(out / "monthly_totals_review.csv")
    assert monthly.iloc[0]["profit_after_ads_kzt"] == pytest.approx(600.0)


def test_build_north_star_owner_review_strict_fail_when_gate_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    validation = tmp_path / "validation"
    _write_validation(validation, "FAIL")
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    owner = tmp_path / "owner.json"
    _write_owner_flags(owner, decision_grade=True)
    with pytest.raises(NorthStarOwnerReviewError):
        build_north_star_owner_review(
            as_of="2026-03-05",
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            stores_config=stores,
            truth_source="db",
            ledger_root=None,
            validation_dir=validation,
            owner_pnl_json=owner,
            output_dir=tmp_path / "out",
        )


def test_locked_month_never_exposes_numeric_profit(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    validation = tmp_path / "validation"
    _write_validation(validation, "PASS")
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    owner = tmp_path / "owner.json"
    _write_owner_flags(owner, decision_grade=False)
    out = tmp_path / "out"
    payload = build_north_star_owner_review(
        as_of="2026-03-05",
        start="2026-01-01",
        end="2026-01-31",
        strict=False,
        db_path=db,
        stores_config=stores,
        truth_source="db",
        ledger_root=None,
        validation_dir=validation,
        owner_pnl_json=owner,
        output_dir=out,
    )
    assert payload["status"] == "PASS"
    monthly = pd.read_csv(out / "monthly_totals_review.csv")
    assert pd.isna(monthly.iloc[0]["profit_after_ads_kzt"])


def test_build_north_star_owner_review_webui_uses_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    validation = tmp_path / "validation"
    _write_webui_validation(validation, "PASS")
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    owner = tmp_path / "owner.json"
    _write_owner_flags(owner, decision_grade=True)

    def fake_projection(**_kwargs):
        frame = pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-20",
                    "store_code": "ACMEWEAR",
                    "sku_key": "SKU_A",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                    "cogs_kzt": 300.0,
                    "db_match_status": "MATCHED",
                }
            ]
        )
        return frame, {"projected_rows": 1, "missing_in_db_orders": 0}

    monkeypatch.setattr(owner_review_mod, "build_webui_truth_projection", fake_projection)

    out = tmp_path / "out"
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    payload = build_north_star_owner_review(
        as_of="2026-03-06",
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        truth_source="webui_archive",
        ledger_root=ledger,
        validation_dir=validation,
        owner_pnl_json=owner,
        output_dir=out,
    )
    assert payload["status"] == "PASS"
    daily = pd.read_csv(out / "daily_profit_by_day_store.csv")
    assert daily.iloc[0]["sale_date"] == "2026-01-20"


def test_build_north_star_owner_review_webui_fallback_requires_workbook_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    validation = tmp_path / "validation"
    _write_webui_fallback_validation(validation, workbook_status="FAIL")
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    owner = tmp_path / "owner.json"
    _write_owner_flags(owner, decision_grade=True)

    def fake_projection(**_kwargs):
        frame = pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-20",
                    "store_code": "ACMEWEAR",
                    "sku_key": "SKU_A",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                    "cogs_kzt": 300.0,
                    "db_match_status": "MATCHED",
                }
            ]
        )
        return frame, {"projected_rows": 1, "missing_in_db_orders": 0}

    monkeypatch.setattr(owner_review_mod, "build_webui_truth_projection", fake_projection)
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    with pytest.raises(NorthStarOwnerReviewError):
        build_north_star_owner_review(
            as_of="2026-03-07",
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            stores_config=stores,
            truth_source="webui_archive",
            ledger_root=ledger,
            validation_dir=validation,
            owner_pnl_json=owner,
            output_dir=tmp_path / "out",
        )
