from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from core.sales.truth_views import ensure_sales_truth_views
from scripts.apply_header_only_source_gap_quarantine_production_safe import (
    PRODUCTION_ENV_GATE,
    ProductionHeaderOnlySourceGapQuarantineApplyError,
    apply_header_only_source_gap_quarantine_production_safe,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_header_only_db(path: Path) -> None:
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
                      'Header fallback', 'STOREB', 1, 9000, 3000, 6000,
                      'DELIVERED', 0)
            """
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, idempotency_key
            ) VALUES ('2026-04-20', 'SALE', 'SKU_HDR', 'SKU_HDR_46', 'L',
                      'UNIVERSAL', -1, 'Q1', 'SALE', 'stock-Q1')
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
              ('2026-04-20', 'COGS_RECOGNIZED', 'COGS', -3000, 'STOREB',
               'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'cogs-Q1')
            """
        )
        ensure_sales_truth_views(conn)


def _write_classification(path: Path) -> None:
    fieldnames = [
        "order_id",
        "store_code",
        "order_date",
        "sale_id",
        "sales_fact_sku_key",
        "sales_fact_sku_id",
        "sales_fact_my_size",
        "sales_fact_kaspi_offer_name",
        "sales_fact_quantity",
        "sales_fact_source_file",
        "real_api_item_entry_evidence_exists",
        "real_api_item_entry_evidence_source",
        "crm_header_evidence_present",
        "crm_header_evidence_only",
        "overlaps_agent69c_23",
        "recommended_action",
        "classification_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "order_id": "Q1",
                "store_code": "STOREB",
                "order_date": "2026-04-20",
                "sale_id": "1",
                "sales_fact_sku_key": "SKU_HDR",
                "sales_fact_sku_id": "SKU_HDR_46",
                "sales_fact_my_size": "L",
                "sales_fact_kaspi_offer_name": "Header fallback",
                "sales_fact_quantity": "1",
                "sales_fact_source_file": "KASPI_API_HEADER_FALLBACK_REBUILD",
                "real_api_item_entry_evidence_exists": "false",
                "real_api_item_entry_evidence_source": "NONE_IN_AGENT69B_APPROVED_SOURCE_HIERARCHY",
                "crm_header_evidence_present": "true",
                "crm_header_evidence_only": "true",
                "overlaps_agent69c_23": "false",
                "recommended_action": "HEADER_ONLY_BLOCKER",
                "classification_reason": "approved hierarchy found header evidence only",
            }
        )


def _prepared_inputs(tmp_path: Path) -> tuple[Path, Path, str]:
    db_path = tmp_path / "app.db"
    classification = tmp_path / "classification.tsv"
    _make_header_only_db(db_path)
    _write_classification(classification)
    return db_path, classification, _sha256(db_path)


def test_prod_safe_wrapper_dry_run_does_not_change_db(tmp_path: Path) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)

    summary = apply_header_only_source_gap_quarantine_production_safe(
        db_path=db_path,
        classification_path=classification,
        output_root=tmp_path / "dry",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_candidate_rows=1,
        expected_product_cashflow_delete_rows=1,
        expected_stock_ledger_delete_rows=1,
        expected_sales_fact_product_profit_null_rows=1,
        apply=False,
    )

    assert summary["apply"]["applied"] is False
    assert summary["production_db_modified"] is False
    assert summary["backup_path"] is None
    assert Path(summary["summary_json"]).exists()
    assert _sha256(db_path) == original_sha


def test_prod_safe_wrapper_apply_without_env_gate_fails_before_mutation(tmp_path: Path) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)

    with pytest.raises(ProductionHeaderOnlySourceGapQuarantineApplyError, match=f"{PRODUCTION_ENV_GATE}=1"):
        apply_header_only_source_gap_quarantine_production_safe(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "blocked_env",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=1,
            expected_sales_fact_product_profit_null_rows=1,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert not (tmp_path / "backups").exists()


def test_prod_safe_wrapper_wrong_pre_sha_fails_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionHeaderOnlySourceGapQuarantineApplyError, match="pre-write SHA mismatch"):
        apply_header_only_source_gap_quarantine_production_safe(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "blocked_sha",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256="0" * 64,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=1,
            expected_sales_fact_product_profit_null_rows=1,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert not (tmp_path / "backups").exists()


def test_prod_safe_wrapper_sidecars_block_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)
    Path(f"{db_path}-wal").write_text("sidecar", encoding="utf-8")

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(ProductionHeaderOnlySourceGapQuarantineApplyError, match="SQLite sidecars"):
        apply_header_only_source_gap_quarantine_production_safe(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "blocked_sidecar",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=1,
            expected_sales_fact_product_profit_null_rows=1,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert not (tmp_path / "backups").exists()


def test_prod_safe_wrapper_applies_via_backup_staging_and_writes_rollback_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    summary = apply_header_only_source_gap_quarantine_production_safe(
        db_path=db_path,
        classification_path=classification,
        output_root=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        expected_candidate_rows=1,
        expected_product_cashflow_delete_rows=1,
        expected_stock_ledger_delete_rows=1,
        expected_sales_fact_product_profit_null_rows=1,
        apply=True,
    )

    assert summary["apply"]["applied"] is True
    assert summary["apply"]["target_replaced"] is True
    assert summary["apply"]["staging_path"] is not None
    assert summary["backup_sha256"] == original_sha
    assert Path(summary["backup_path"]).exists()
    assert summary["integrity_check"]["backup"] == "ok"
    assert summary["integrity_check"]["staging_before_apply"] == "ok"
    assert summary["integrity_check"]["staging_after_apply"] == "ok"
    assert summary["integrity_check"]["after"] == "ok"
    assert summary["actual"] == {
        "candidate_rows": 1,
        "deleted_product_cashflow_rows": 1,
        "deleted_stock_ledger_rows": 1,
        "nulled_sales_fact_product_profit_rows": 1,
    }
    assert summary["cash_in_preservation"]["before_count"] == 1
    assert summary["cash_in_preservation"]["after_count"] == 1
    assert summary["cash_in_preservation"]["preserved"] is True
    assert summary["fact_order_entries_inserted"] == 0
    assert summary["header_fields_used_as_canonical_item_entry_truth"] is False
    assert "cp " in summary["rollback"]["restore_command"]

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert persisted["rollback"]["backup_path"] == summary["backup_path"]
    assert persisted["production_db_modified"] is False

    with sqlite3.connect(db_path) as conn:
        cash_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='Q1' AND event_type='CASH_IN'"
        ).fetchone()[0]
        product_cash_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='Q1' AND event_type='COGS_RECOGNIZED'"
        ).fetchone()[0]
        stock_rows = conn.execute("SELECT COUNT(*) FROM stock_ledger WHERE reference_id='Q1'").fetchone()[0]
        entries = conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi WHERE order_id='Q1'").fetchone()[0]
        cogs_profit = conn.execute(
            "SELECT cogs, profit FROM sales_fact_v2 WHERE order_id='Q1' AND store_code='STOREB'"
        ).fetchone()
        quarantine = conn.execute(
            """
            SELECT product_stock_excluded, product_cogs_excluded,
                   product_profit_excluded, sku_publication_excluded
            FROM fact_order_entry_header_only_source_gap_quarantine
            WHERE order_id='Q1' AND store_code='STOREB'
            """
        ).fetchone()

    assert cash_rows == 1
    assert product_cash_rows == 0
    assert stock_rows == 0
    assert entries == 0
    assert cogs_profit == (None, None)
    assert quarantine == (1, 1, 1, 1)


def test_prod_safe_wrapper_expected_delta_mismatch_fails_before_target_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, classification, original_sha = _prepared_inputs(tmp_path)

    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")
    with pytest.raises(
        ProductionHeaderOnlySourceGapQuarantineApplyError,
        match="nulled_sales_fact_product_profit_rows mismatch",
    ):
        apply_header_only_source_gap_quarantine_production_safe(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "mismatch",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_candidate_rows=1,
            expected_product_cashflow_delete_rows=1,
            expected_stock_ledger_delete_rows=1,
            expected_sales_fact_product_profit_null_rows=2,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert list((tmp_path / "backups").glob("*.db"))
