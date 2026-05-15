from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.validate_cashflow_actual_model_separation import evaluate_actual_model_separation
from scripts.validate_order_cashflow_coverage import evaluate_order_cashflow_coverage


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE order_status_event (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            order_id TEXT,
            stage_code TEXT,
            event_ts TEXT,
            source TEXT,
            idempotency_key TEXT
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
        CREATE TABLE fact_cashflow_daily (
            date TEXT PRIMARY KEY,
            cash_open REAL,
            cash_close REAL,
            receivables_open REAL,
            receivables_close REAL,
            cash_flow_kzt REAL,
            receivables_flow_kzt
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT
        );
        """
    )
    return conn


def _seed_completed_entry(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O1', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-o1-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('E1', 'O1', 'ACMEWEAR', 'OFFER1', 1, 10000, 10000)
        """
    )


def test_order_cashflow_coverage_reports_missing_and_accepts_entry_cash_in(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_completed_entry(conn)
    conn.commit()
    conn.close()

    missing = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert missing["cash_in_missing_count"] == 1
    assert missing["modeled_receivables_count"] == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', NULL, NULL, 'ORDER_ENTRY', 'E1', 'ORDER_MODELLED', 'cash-e1')
        """
    )
    conn.commit()
    conn.close()

    covered = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert covered["cash_in_missing_count"] == 0
    assert covered["duplicate_cash_in_count"] == 0
    assert covered["balance_anchor_fake_cash_in_count"] == 0


def test_order_cashflow_coverage_rejects_balance_anchor_fake_cash_in(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_completed_entry(conn)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', 'BALANCE_ANCHOR', 'anchor-1', 'BALANCE_ANCHOR', 'fake-anchor')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert report["cash_in_missing_count"] == 1
    assert report["balance_anchor_fake_cash_in_count"] == 1


def test_entry_cash_in_takes_precedence_over_legacy_order_cash_overlap(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_completed_entry(conn)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER_ENTRY', 'E1',
                  'ORDER_MODELLED', 'entry-cash')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'O1',
                  'ORDER_MODELLED', 'legacy-order-cash')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', 'SKU_OTHER', 'SKU_OTHER_M', 'ORDER', 'O1',
                  'ORDER_MODELLED', 'legacy-order-cash-other-sku')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert report["cash_in_missing_count"] == 0
    assert report["duplicate_cash_in_count"] == 0


def test_unknown_store_lifecycle_shadow_is_ignored_when_real_store_stage_exists(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_completed_entry(conn)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('UNKNOWN', 'O1', 'COMPLETED', '2026-05-03T10:00:00+05:00',
                  'fixture', 'ose-o1-unknown-shadow')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                  'ACMEWEAR', NULL, NULL, 'ORDER_ENTRY', 'E1',
                  'ORDER_MODELLED', 'cash-e1')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert report["cash_in_missing_count"] == 0
    assert report["missing_line_evidence_count"] == 0


def test_generic_recovered_sku_identity_can_use_single_line_order_cash(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_GENERIC_SKU', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-generic-sku')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('E_GENERIC', 'O_GENERIC_SKU', 'ACMEWEAR', 'OFFER_GENERIC', 1, 17990, 17990)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (
            store_code, kaspi_article, sku_key, sku_id
        ) VALUES ('ACMEWEAR', 'OFFER_GENERIC', 'CL', 'CL_XL')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 14056.43,
                  'ACMEWEAR', 'CL_OC_MEN_LINE51_WHITE', 'CL_OC_MEN_LINE51_WHITE_XL',
                  'ORDER', 'O_GENERIC_SKU', 'ORDER_MODELLED', 'cash-generic')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert report["cash_in_missing_count"] == 0


def test_order_header_cash_exception_does_not_hide_missing_cash(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            delivery_cost_for_seller REAL,
            sku_key TEXT,
            sku_id TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_HEADER', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-o-header-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, quantity, unit_price_kzt, delivery_cost_for_seller,
            sku_key, sku_id
        ) VALUES ('O_HEADER', 'ACMEWEAR', 1, 15990, 1507, NULL, NULL)
        """
    )
    conn.commit()
    conn.close()

    missing_cash = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert missing_cash["cash_in_missing_count"] == 1
    assert missing_cash["missing_line_evidence_count"] == 0
    assert missing_cash["deterministic_exception_count"] == 1

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 12000,
                  'ACMEWEAR', 'ORDER', 'O_HEADER', 'ORDER_MODELLED', 'cash-header')
        """
    )
    conn.commit()
    conn.close()

    covered = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-03")
    assert covered["status"] == "PASS"
    assert covered["cash_in_missing_count"] == 0
    assert covered["deterministic_exception_count"] == 1


def test_recovered_blank_entries_can_use_order_level_cash_without_sku_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('UNIVERSAL', 'O_RECOV', 'COMPLETED',
                  '2026-04-20T10:00:00+05:00', 'fixture', 'ose-o-recov')
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES (?, 'O_RECOV', 'UNIVERSAL', ?, 1, 1500, 1500)
        """,
        [
            ("RECOV-CURRENT_CRM-a", "OFFER-A"),
            ("RECOV-CURRENT_CRM-b", "OFFER-B"),
        ],
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-04-20', 'CASH_IN', 'KASPI_PAY_UNIVERSAL', 3000,
                  'UNIVERSAL', 'ORDER', 'O_RECOV', 'ORDER_MODELLED',
                  'cash-o-recov')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_order_cashflow_coverage(db_path, as_of="2026-05-04")

    assert report["candidate_line_count"] == 2
    assert report["cash_in_missing_count"] == 0
    assert report["missing_line_evidence_count"] == 0


def test_actual_model_separation_allows_legacy_diagnostics_but_blocks_paid_truth_leaks(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_daily (
            date, cash_open, cash_close, receivables_open, receivables_close,
            cash_flow_kzt, receivables_flow_kzt
        ) VALUES ('2026-05-02', 0, 10000, 0, 0, 10000, 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'SALE_ACCRUED', 'RECEIVABLES', 10000,
                  'ORDER', 'O1', 'ORDER_MODELLED', 'legacy-recv')
        """
    )
    conn.commit()
    conn.close()

    report = evaluate_actual_model_separation(db_path, anchor_date="2026-05-03")
    assert report["modeled_receivables_count"] == 0
    assert report["legacy_modeled_receivables_diagnostic_count"] == 1
    assert report["paid_truth_receivables_daily_count"] == 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'PAYOUT_EXPECTED', 'RECEIVABLES', 5000,
                  'ORDER', 'O2', 'STATEMENT_ACTUAL', 'actual-recv-leak')
        """
    )
    conn.commit()
    conn.close()

    leaked = evaluate_actual_model_separation(db_path, anchor_date="2026-05-03")
    assert leaked["modeled_receivables_count"] == 1
