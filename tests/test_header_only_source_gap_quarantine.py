from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from core.sales.truth_views import ensure_sales_truth_views
from scripts.materialize_header_only_source_gap_quarantine import (
    HeaderOnlySourceGapQuarantineError,
    materialize_header_only_source_gap_quarantine,
)


def _make_header_only_db(path: Path) -> None:
    conn = sqlite3.connect(path)
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
    conn.commit()
    conn.close()


def _write_classification(path: Path, *, missing_proof: bool = False) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        row = {
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
        if missing_proof:
            row["real_api_item_entry_evidence_source"] = ""
        writer.writerow(row)


def test_header_only_quarantine_apply_excludes_publication_leaks_and_keeps_cash_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "temp.db"
    classification = tmp_path / "classification.tsv"
    _make_header_only_db(db_path)
    _write_classification(classification)

    dry = materialize_header_only_source_gap_quarantine(
        db_path=db_path,
        classification_path=classification,
        output_root=tmp_path / "dry",
        apply=False,
    )
    assert dry["apply"]["applied"] is False
    assert dry["candidate_rows"] == 1
    assert dry["leakage_before"]["stock_ledger_reference_count"] == 1
    assert dry["leakage_before"]["product_cashflow_reference_count"] == 1
    assert dry["leakage_before"]["published_sales_truth_line_count"] == 1

    with pytest.raises(
        HeaderOnlySourceGapQuarantineError,
        match="ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY=1",
    ):
        materialize_header_only_source_gap_quarantine(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "blocked",
            apply=True,
        )

    monkeypatch.setenv("ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY", "1")
    applied = materialize_header_only_source_gap_quarantine(
        db_path=db_path,
        classification_path=classification,
        output_root=tmp_path / "apply",
        apply=True,
    )

    assert applied["apply"]["inserted_quarantine_rows"] == 1
    assert applied["apply"]["deleted_stock_ledger_rows"] == 1
    assert applied["apply"]["deleted_product_cashflow_rows"] == 1
    assert applied["leakage_after"]["stock_ledger_reference_count"] == 0
    assert applied["leakage_after"]["product_cashflow_reference_count"] == 0
    assert applied["leakage_after"]["published_sales_truth_line_count"] == 0
    assert applied["leakage_after"]["fact_order_entries_count"] == 0

    with sqlite3.connect(db_path) as conn:
        cash_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='Q1' AND event_type='CASH_IN'"
        ).fetchone()[0]
        entry_rows = conn.execute(
            "SELECT COUNT(*) FROM fact_order_entries_kaspi WHERE order_id='Q1'"
        ).fetchone()[0]
        truth_rows = conn.execute(
            "SELECT COUNT(*) FROM view_sales_line_truth WHERE order_id='Q1'"
        ).fetchone()[0]
        quarantine_row = conn.execute(
            """
            SELECT product_stock_excluded, product_cogs_excluded,
                   product_profit_excluded, sku_publication_excluded
            FROM fact_order_entry_header_only_source_gap_quarantine
            WHERE order_id='Q1' AND store_code='STOREB'
            """
        ).fetchone()

    assert cash_rows == 1
    assert entry_rows == 0
    assert truth_rows == 0
    assert quarantine_row == (1, 1, 1, 1)


def test_header_only_quarantine_missing_source_hierarchy_proof_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "temp.db"
    classification = tmp_path / "classification.tsv"
    _make_header_only_db(db_path)
    _write_classification(classification, missing_proof=True)

    with pytest.raises(HeaderOnlySourceGapQuarantineError, match="missing source hierarchy proof"):
        materialize_header_only_source_gap_quarantine(
            db_path=db_path,
            classification_path=classification,
            output_root=tmp_path / "dry",
            apply=False,
        )
