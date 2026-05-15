from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from core.sales.truth_views import ensure_sales_truth_views
from scripts.apply_storeb_product_identity_quarantine_production_safe import (
    PRODUCTION_ENV_GATE,
    ProductionQuarantineApplyError,
    apply_storeb_product_identity_quarantine_production_safe,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_quarantine_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                kaspi_offer_name TEXT,
                store_code TEXT,
                quantity REAL,
                net_rev REAL,
                cogs REAL,
                profit REAL,
                status TEXT,
                return_flag INTEGER
            );
            CREATE TABLE fact_sales (
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                store_code TEXT,
                quantity REAL,
                line_net_rev REAL,
                cogs_line REAL,
                profit_line REAL
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                base_cost_cny REAL,
                weight_kg REAL,
                cogs_kzt REAL
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT,
                event_type TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                store_code TEXT,
                qty_change INTEGER,
                reference_id TEXT,
                reference_type TEXT,
                idempotency_key TEXT
            );
            CREATE TABLE fact_cashflow_events (
                event_date TEXT,
                event_type TEXT,
                account TEXT,
                amount_kzt REAL,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                ref_type TEXT,
                ref_id TEXT,
                source TEXT,
                event_hash TEXT
            );
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL
            );
            """
        )
        conn.execute("INSERT INTO dim_sku VALUES ('SKU_HDR', 30, 0.4, 0)")
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, net_rev, cogs, profit, status, return_flag
            ) VALUES ('Q1', '2026-04-20', 'SKU_HDR', 'SKU_HDR_46', 'L',
                      'Header fallback', 'STOREB', 1, 9000, NULL, NULL,
                      'DELIVERED', 0)
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, source, event_hash
            ) VALUES
              ('2026-04-20', 'CASH_IN', 'KASPI_PAY_STOREB', 9000, 'STOREB',
               'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'cash-Q1'),
              ('2026-04-20', 'INVENTORY_MOVE', 'INVENTORY_ON_HAND_COST', -3000, 'STOREB',
               'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'inv-Q1')
            """
        )
        ensure_sales_truth_views(conn)


def _write_candidates(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "store_code",
                "order_id",
                "order_date",
                "sale_id",
                "reason_code",
                "api_entry_ids",
                "api_offer_codes",
                "api_product_ids",
                "publication_exclusion_required",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "store_code": "STOREB",
                "order_id": "Q1",
                "order_date": "2026-04-20",
                "sale_id": "1",
                "reason_code": "MISSING_APPROVED_CANONICAL_PRODUCT_IDENTITY",
                "api_entry_ids": "entry-unknown",
                "api_offer_codes": "OFFER_UNKNOWN",
                "api_product_ids": "PRODUCT_UNKNOWN",
                "publication_exclusion_required": "True",
            }
        )


def test_prod_safe_wrapper_requires_apply_env_backup_and_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    candidates = tmp_path / "candidates.csv"
    _make_quarantine_db(db_path)
    _write_candidates(candidates)
    original_sha = _sha256(db_path)

    summary = apply_storeb_product_identity_quarantine_production_safe(
        db_path=db_path,
        candidates_path=candidates,
        output_root=tmp_path / "dry",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_candidate_rows=1,
        expected_product_cashflow_delete_rows=1,
        expected_stock_ledger_delete_rows=0,
        apply=False,
    )
    assert summary["apply"]["applied"] is False
    assert summary["backup_path"] is None
    assert _sha256(db_path) == original_sha

    with pytest.raises(ProductionQuarantineApplyError, match=f"{PRODUCTION_ENV_GATE}=1"):
        apply_storeb_product_identity_quarantine_production_safe(
            db_path=db_path,
            candidates_path=candidates,
            output_root=tmp_path / "blocked_env",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=0,
            apply=True,
        )

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionQuarantineApplyError, match="pre-write SHA mismatch"):
        apply_storeb_product_identity_quarantine_production_safe(
            db_path=db_path,
            candidates_path=candidates,
            output_root=tmp_path / "blocked_sha",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256="0" * 64,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=0,
            apply=True,
        )
    assert _sha256(db_path) == original_sha


def test_prod_safe_wrapper_applies_via_staging_and_writes_rollback_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    candidates = tmp_path / "candidates.csv"
    _make_quarantine_db(db_path)
    _write_candidates(candidates)
    original_sha = _sha256(db_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    summary = apply_storeb_product_identity_quarantine_production_safe(
        db_path=db_path,
        candidates_path=candidates,
        output_root=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_candidate_rows=1,
        expected_product_cashflow_delete_rows=1,
        expected_stock_ledger_delete_rows=0,
        apply=True,
    )

    assert summary["apply"]["applied"] is True
    assert summary["materializer_summary"]["apply"]["inserted_quarantine_rows"] == 1
    assert summary["materializer_summary"]["apply"]["deleted_product_cashflow_rows"] == 1
    assert summary["materializer_summary"]["apply"]["deleted_stock_ledger_rows"] == 0
    assert summary["cash_in_preservation"]["before_count"] == 1
    assert summary["cash_in_preservation"]["after_count"] == 1
    assert summary["integrity_check"]["before"] == "ok"
    assert summary["integrity_check"]["after"] == "ok"
    assert Path(summary["backup_path"]).exists()
    assert "cp " in summary["rollback"]["restore_command"]
    assert Path(summary["summary_json"]).exists()

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert persisted["rollback"]["backup_path"] == summary["backup_path"]
    with sqlite3.connect(db_path) as conn:
        cash_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='Q1' AND event_type='CASH_IN'"
        ).fetchone()[0]
        product_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='Q1' AND event_type='INVENTORY_MOVE'"
        ).fetchone()[0]
    assert cash_rows == 1
    assert product_rows == 0


def test_prod_safe_wrapper_rejects_delta_mismatch_before_replacing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    candidates = tmp_path / "candidates.csv"
    _make_quarantine_db(db_path)
    _write_candidates(candidates)
    original_sha = _sha256(db_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionQuarantineApplyError, match="deleted_product_cashflow_rows mismatch"):
        apply_storeb_product_identity_quarantine_production_safe(
            db_path=db_path,
            candidates_path=candidates,
            output_root=tmp_path / "mismatch",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=2,
            expected_stock_ledger_delete_rows=0,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
