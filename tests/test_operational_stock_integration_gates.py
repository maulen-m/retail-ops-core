from __future__ import annotations

import sqlite3
from pathlib import Path

from core.ops.operational_stock_integration_gates import (
    evaluate_operational_stock_integration_gates,
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
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
            quantity INTEGER,
            status TEXT,
            return_flag INTEGER
        );
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
        CREATE TABLE return_qc_event (
            qc_event_id TEXT PRIMARY KEY,
            store_code TEXT,
            order_id TEXT,
            order_entry_id TEXT,
            sku_id TEXT,
            quantity INTEGER,
            qc_status TEXT,
            accepted_active_qty INTEGER,
            quarantine_qty INTEGER,
            rejected_qty INTEGER,
            writeoff_qty INTEGER,
            source TEXT,
            idempotency_key TEXT
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
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            status TEXT,
            units_total INTEGER,
            units_received INTEGER
        );
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            status TEXT,
            total_units INTEGER,
            is_paid_base INTEGER,
            is_paid_dlv INTEGER
        );
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            order_qty INTEGER,
            received_qty INTEGER,
            status TEXT
        );
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            current_stock INTEGER,
            inbound_stock INTEGER
        );
        CREATE TABLE ads_source_refresh_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            store_code TEXT,
            date_start TEXT,
            date_end TEXT,
            status TEXT
        );
        CREATE TABLE ads_campaign_product_daily (
            date TEXT,
            store_code TEXT,
            campaign_id TEXT,
            sku_key TEXT,
            cost_kzt REAL,
            source_run_id TEXT,
            coverage_status TEXT
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
            inventory_cost_open REAL,
            inventory_cost_close REAL,
            capital_close REAL,
            cash_flow_kzt REAL,
            receivables_flow_kzt REAL,
            inventory_cost_flow_kzt REAL,
            inventory_on_hand_close REAL,
            inventory_inbound_close REAL,
            inventory_on_delivery_close REAL
        );
        """
    )
    return conn


def _seed_green_baseline(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('O1', '2026-05-02', 'SKU_A', 'SKU_A_M', 'M', 'Offer A',
                  'ACMEWEAR', 1, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O1', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-O1-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('E1', 'O1', 'ACMEWEAR', 'OFFER_A', 1, 10000, 10000)
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, store_code, date_start, date_end, status
        ) VALUES ('ADS1', '2026-05-02T00:00:00+05:00', '2026-05-02T01:00:00+05:00',
                  'ACMEWEAR', '2026-05-02', '2026-05-02', 'SUCCESS')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily (
            date, store_code, campaign_id, sku_key, cost_kzt, source_run_id, coverage_status
        ) VALUES ('2026-05-02', 'ACMEWEAR', 'CAMP1', 'SKU_A', 750, 'ADS1', 'COVERED')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000, 'ACMEWEAR',
                  'SKU_A', 'SKU_A_M', 'ORDER', 'O1', 'ORDER_MODELLED', 'cash-O1')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_daily (
            date, cash_open, cash_close, receivables_open, receivables_close,
            inventory_cost_open, inventory_cost_close, capital_close, cash_flow_kzt,
            receivables_flow_kzt, inventory_cost_flow_kzt, inventory_on_hand_close,
            inventory_inbound_close, inventory_on_delivery_close
        ) VALUES ('2026-05-02', 0, 10000, 0, 0, 0, 0, 10000, 10000, 0, 0, 0, 0, 0)
        """
    )


def _codes(db_path: Path) -> set[str]:
    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    return {finding.code for finding in report.findings}


def _seed_storeb_quarantine_candidate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('Q1', '2026-05-02', 'SKU_HDR', 'SKU_HDR_46', 'L',
                  'Header fallback offer', 'STOREB', 1, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('STOREB', 'Q1', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-Q1-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_STOREB', 12000, 'STOREB',
                  'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'cash-Q1')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, store_code, date_start, date_end, status
        ) VALUES ('ADS_STOREB_Q', '2026-05-02T00:00:00+05:00',
                  '2026-05-02T01:00:00+05:00', 'STOREB', '2026-05-02',
                  '2026-05-02', 'SUCCESS')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily (
            date, store_code, campaign_id, sku_key, cost_kzt, source_run_id, coverage_status
        ) VALUES ('2026-05-02', 'STOREB', 'CAMP_Q', 'SKU_HDR', 0,
                  'ADS_STOREB_Q', 'NO_SPEND_VERIFIED')
        """
    )


def _create_quarantine_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE fact_order_entry_product_identity_quarantine (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sale_id INTEGER,
            order_date TEXT,
            reason_code TEXT NOT NULL,
            api_entry_ids TEXT NOT NULL,
            api_offer_codes TEXT NOT NULL,
            api_product_ids TEXT,
            api_entry_count INTEGER NOT NULL DEFAULT 0,
            api_entries_with_complete_sku_id_size INTEGER NOT NULL DEFAULT 0,
            publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
            product_stock_excluded INTEGER NOT NULL DEFAULT 0,
            product_cogs_excluded INTEGER NOT NULL DEFAULT 0,
            product_profit_excluded INTEGER NOT NULL DEFAULT 0,
            sku_publication_excluded INTEGER NOT NULL DEFAULT 0,
            publication_exclusion_proof_json TEXT,
            active_flag INTEGER NOT NULL DEFAULT 1,
            evidence_source TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (store_code, order_id)
        )
        """
    )


def _create_header_only_quarantine_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE fact_order_entry_header_only_source_gap_quarantine (
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            sale_id INTEGER,
            order_date TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            header_sku_key TEXT,
            header_sku_id TEXT,
            header_my_size TEXT,
            header_kaspi_offer_name TEXT,
            header_quantity REAL,
            header_source_file TEXT NOT NULL,
            source_hierarchy_checked_json TEXT NOT NULL,
            publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
            product_stock_excluded INTEGER NOT NULL DEFAULT 1,
            product_cogs_excluded INTEGER NOT NULL DEFAULT 1,
            product_profit_excluded INTEGER NOT NULL DEFAULT 1,
            sku_publication_excluded INTEGER NOT NULL DEFAULT 1,
            publication_exclusion_proof_json TEXT NOT NULL,
            owner_or_codecaptain_review_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
            active_flag INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (store_code, order_id)
        )
        """
    )


def _insert_quarantine_row(conn: sqlite3.Connection, *, proof: bool, complete_entries: int = 0) -> None:
    conn.execute(
        """
        INSERT INTO fact_order_entry_product_identity_quarantine (
            store_code, order_id, sale_id, order_date, reason_code, api_entry_ids,
            api_offer_codes, api_product_ids, api_entry_count,
            api_entries_with_complete_sku_id_size, publication_exclusion_required,
            product_stock_excluded, product_cogs_excluded, product_profit_excluded,
            sku_publication_excluded, publication_exclusion_proof_json, active_flag,
            evidence_source, created_by, created_at
        ) VALUES (
            'STOREB', 'Q1', 9001, '2026-05-02',
            'MISSING_APPROVED_CANONICAL_PRODUCT_IDENTITY',
            'entry-known;entry-unknown', 'OFFER_KNOWN;OFFER_UNKNOWN',
            'PRODUCT_KNOWN;PRODUCT_UNKNOWN', 2, ?, 1,
            ?, ?, ?, ?,
            ?, 1, 'agent39_fixture', 'agent43_test', '2026-05-05T00:00:00+00:00'
        )
        """,
        (
            complete_entries,
            1 if proof else 0,
            1 if proof else 0,
            1 if proof else 0,
            1 if proof else 0,
            (
                '{"stock_ledger_reference_count":0,'
                '"product_cashflow_reference_count":0,'
                '"published_sales_truth_line_count":0}'
                if proof
                else None
            ),
        ),
    )


def _insert_header_only_quarantine_row(conn: sqlite3.Connection, *, proof: bool) -> None:
    conn.execute(
        """
        INSERT INTO fact_order_entry_header_only_source_gap_quarantine (
            store_code, order_id, sale_id, order_date, reason_code,
            header_sku_key, header_sku_id, header_my_size, header_kaspi_offer_name,
            header_quantity, header_source_file, source_hierarchy_checked_json,
            publication_exclusion_required, product_stock_excluded, product_cogs_excluded,
            product_profit_excluded, sku_publication_excluded,
            publication_exclusion_proof_json, owner_or_codecaptain_review_status,
            active_flag, created_by, created_at
        ) VALUES (
            'STOREB', 'Q1', 9001, '2026-05-02',
            'HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE',
            'SKU_HDR', 'SKU_HDR_46', 'L', 'Header fallback offer', 1,
            'KASPI_API_HEADER_FALLBACK_REBUILD',
            ?,
            1, ?, ?, ?, ?,
            ?, 'REVIEW_REQUIRED', 1, 'agent696_test',
            '2026-05-04T23:59:59+05:00'
        )
        """,
        (
            (
                '{"approved_hierarchy_checked":true,'
                '"real_item_entry_evidence_exists":false,'
                '"crm_header_evidence_only":true}'
                if proof
                else ""
            ),
            1 if proof else 0,
            1 if proof else 0,
            1 if proof else 0,
            1 if proof else 0,
            (
                '{"stock_ledger_reference_count":0,'
                '"product_cashflow_reference_count":0,'
                '"published_sales_truth_line_count":0,'
                '"fact_order_entries_count":0}'
                if proof
                else ""
            ),
        ),
    )


def test_sales_order_dedup_fixture_blocks_duplicate_sales_projection(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('O1', '2026-05-02', 'SKU_A', 'SKU_A_M', 'M', 'Offer A',
                  'ACMEWEAR', 1, 'DELIVERED', 0)
        """
    )
    conn.commit()

    assert "SALES_ORDER_DUPLICATE" in _codes(db_path)


def test_return_qc_active_stock_fixture_blocks_restock_without_qc(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_RET', 'RETURNED', '2026-05-03T10:00:00+05:00',
                  'fixture', 'ose-O_RET-returned')
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-05-03', 'RETURN', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR',
                  1, 'O_RET', 'ORDER_RETURN', 'return-O_RET')
        """
    )
    conn.commit()

    assert "RETURN_ACTIVE_WITHOUT_QC" in _codes(db_path)


def test_return_qc_acceptance_allows_active_restock_quantity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_RET_QC', 'RETURNED', '2026-05-03T10:00:00+05:00',
                  'fixture', 'ose-O_RET_QC-returned')
        """
    )
    conn.execute(
        """
        INSERT INTO return_qc_event (
            qc_event_id, store_code, order_id, order_entry_id, sku_id, quantity,
            qc_status, accepted_active_qty, quarantine_qty, rejected_qty, writeoff_qty,
            source, idempotency_key
        ) VALUES ('QC_RET', 'ACMEWEAR', 'O_RET_QC', NULL, 'SKU_A_M', 1,
                  'ACCEPTED', 1, 0, 0, 0, 'fixture', 'qc-ret')
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-05-03', 'RETURN', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL',
                  1, 'O_RET_QC', 'ORDER_RETURN', 'return-O_RET_QC')
        """
    )
    conn.commit()

    assert "RETURN_ACTIVE_WITHOUT_QC" not in _codes(db_path)


def test_header_only_fact_order_does_not_clear_product_level_publication(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            quantity REAL,
            unit_price_kzt REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('O_HEADER_ONLY', '2026-05-02', 'SKU_HDR', 'SKU_HDR_M', 'M',
                  'Header-only offer', 'STOREB', 1, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('STOREB', 'O_HEADER_ONLY', 'COMPLETED',
                  '2026-05-02T10:00:00+05:00', 'fixture', 'ose-header-only')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, internal_status, kaspi_status, kaspi_status_detail,
            quantity, unit_price_kzt
        ) VALUES ('O_HEADER_ONLY', 'STOREB', 'COMPLETED', 'ARCHIVE', 'COMPLETED',
                  1, 12000)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_STOREB', 12000, 'STOREB',
                  'SKU_HDR', 'SKU_HDR_M', 'ORDER', 'O_HEADER_ONLY',
                  'ORDER_MODELLED', 'cash-header-only')
        """
    )
    conn.commit()

    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    entry_findings = [
        finding
        for finding in report.findings
        if finding.code == "ORDER_ENTRY_MISSING"
        and finding.evidence.get("order_id") == "O_HEADER_ONLY"
    ]

    assert entry_findings


def test_unquarantined_missing_order_entry_remains_blocking(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    conn.commit()

    assert "ORDER_ENTRY_MISSING" in _codes(db_path)


def test_quarantined_missing_entry_without_publication_proof_remains_blocking(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_quarantine_table(conn)
    _insert_quarantine_row(conn, proof=False)
    conn.commit()

    assert "ORDER_ENTRY_MISSING" in _codes(db_path)


def test_quarantined_missing_entry_with_exclusion_proof_is_not_unhandled_order_entry_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_quarantine_table(conn)
    _insert_quarantine_row(conn, proof=True)
    conn.commit()

    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    q1_missing = [
        finding
        for finding in report.findings
        if finding.code == "ORDER_ENTRY_MISSING"
        and finding.evidence.get("order_id") == "Q1"
    ]

    assert q1_missing == []
    assert report.status == "GREEN"


def test_header_only_source_gap_quarantine_warns_without_unhandled_order_entry_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_header_only_quarantine_table(conn)
    _insert_header_only_quarantine_row(conn, proof=True)
    conn.commit()

    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    q1_missing = [
        finding
        for finding in report.findings
        if finding.code == "ORDER_ENTRY_MISSING"
        and finding.evidence.get("order_id") == "Q1"
    ]
    q1_warns = [
        finding
        for finding in report.findings
        if finding.code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED"
        and finding.evidence.get("order_id") == "Q1"
    ]

    assert q1_missing == []
    assert len(q1_warns) == 1
    assert q1_warns[0].severity == "WARN"
    assert report.status == "GREEN"


def test_header_only_source_gap_quarantine_missing_proof_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_header_only_quarantine_table(conn)
    _insert_header_only_quarantine_row(conn, proof=False)
    conn.commit()

    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    q1_missing = [
        finding
        for finding in report.findings
        if finding.code == "ORDER_ENTRY_MISSING"
        and finding.evidence.get("order_id") == "Q1"
    ]

    assert len(q1_missing) == 1
    assert q1_missing[0].evidence["header_only_quarantine_present"] is True


def test_mixed_known_unknown_quarantined_order_blocks_partial_entry_leak(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_quarantine_table(conn)
    _insert_quarantine_row(conn, proof=True, complete_entries=1)
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('entry-known', 'Q1', 'STOREB', 'OFFER_KNOWN', 1, 12000, 12000)
        """
    )
    conn.commit()

    assert "ORDER_ENTRY_QUARANTINE_PARTIAL_ENTRY_LEAK" in _codes(db_path)


def test_quarantined_order_blocks_product_stock_cogs_and_profit_publication_leakage(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_quarantine_table(conn)
    _insert_quarantine_row(conn, proof=True)
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-05-02', 'SALE', 'SKU_HDR', 'SKU_HDR_46', 'L', 'UNIVERSAL',
                  -1, 'Q1', 'SALE', 'stock-leak-Q1')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'COGS_RECOGNIZED', 'COGS', -3000, 'STOREB',
                  'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'cogs-Q1')
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT 'Q1' AS order_id, '2026-05-02' AS sale_date, 'STOREB' AS store_code,
               'SKU_HDR' AS sku_key, 'SKU_HDR_46' AS sku_id, 1.0 AS units,
               3000.0 AS cogs_kzt, 9000.0 AS profit_kzt
        """
    )
    conn.commit()

    codes = _codes(db_path)

    assert "ORDER_ENTRY_QUARANTINE_PRODUCT_STOCK_LEAK" in codes
    assert "ORDER_ENTRY_QUARANTINE_PRODUCT_COGS_LEAK" in codes
    assert "ORDER_ENTRY_QUARANTINE_PRODUCT_PROFIT_LEAK" in codes


def test_header_only_source_gap_quarantine_blocks_product_stock_cogs_profit_and_entry_leaks(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    _seed_storeb_quarantine_candidate(conn)
    _create_header_only_quarantine_table(conn)
    _insert_header_only_quarantine_row(conn, proof=True)
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('entry-header-leak', 'Q1', 'STOREB', 'OFFER_HDR', 1, 12000, 12000)
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-05-02', 'SALE', 'SKU_HDR', 'SKU_HDR_46', 'L', 'UNIVERSAL',
                  -1, 'Q1', 'SALE', 'stock-leak-Q1')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'COGS_RECOGNIZED', 'COGS', -3000, 'STOREB',
                  'SKU_HDR', 'SKU_HDR_46', 'ORDER', 'Q1', 'ORDER_MODELLED', 'cogs-Q1')
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT 'Q1' AS order_id, '2026-05-02' AS sale_date, 'STOREB' AS store_code,
               'SKU_HDR' AS sku_key, 'SKU_HDR_46' AS sku_id, 1.0 AS units,
               3000.0 AS cogs_kzt, 9000.0 AS profit_kzt
        """
    )
    conn.commit()

    codes = _codes(db_path)

    assert "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_ENTRY_LEAK" in codes
    assert "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_STOCK_LEAK" in codes
    assert "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK" in codes
    assert "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_PROFIT_LEAK" in codes


def test_po_inbound_reconciliation_fixture_blocks_received_units_left_in_inbound(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute("INSERT INTO po_header VALUES ('PO-1', 'RECEIVED', 5, 5)")
    conn.execute("INSERT INTO po_part VALUES ('PO-1.1', 'PO-1', 'RECEIVED', 5, 1, 1)")
    conn.execute(
        """
        INSERT INTO po_line (
            po_id, po_part_id, sku_key, sku_id, my_size, order_qty, received_qty, status
        ) VALUES ('PO-1', 'PO-1.1', 'SKU_A', 'SKU_A_M', 'M', 5, 5, 'RECEIVED')
        """
    )
    po_line_id = conn.execute("SELECT po_line_id FROM po_line").fetchone()[0]
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-05-03', 'INBOUND', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL',
                  5, ?, 'PO_LINE', 'inbound-PO-1.1-SKU_A_M')
        """,
        (str(po_line_id),),
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (
            snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
        ) VALUES ('2026-05-03', 'SKU_A_M', 'SKU_A', 'M', 10, 5)
        """
    )
    conn.commit()

    assert "PO_INBOUND_DOUBLE_COUNT" in _codes(db_path)


def test_ads_coverage_fixture_blocks_storeb_missing_or_blocked_as_zero_spend(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('O_STOREB', '2026-05-02', 'SKU_MG', 'SKU_MG_M', 'M', 'Offer MG',
                  'STOREB', 1, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('STOREB', 'O_STOREB', 'COMPLETED', '2026-05-02T10:00:00+05:00',
                  'fixture', 'ose-O_STOREB-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
        ) VALUES ('E_STOREB', 'O_STOREB', 'STOREB', 'OFFER_MG', 1, 12000, 12000)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'KASPI_PAY_STOREB', 12000, 'STOREB',
                  'SKU_MG', 'SKU_MG_M', 'ORDER', 'O_STOREB', 'ORDER_MODELLED', 'cash-O_STOREB')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, store_code, date_start, date_end, status
        ) VALUES ('ADS_STOREB', '2026-05-02T00:00:00+05:00',
                  '2026-05-02T01:00:00+05:00', 'STOREB', '2026-05-02',
                  '2026-05-02', 'BLOCKED')
        """
    )
    conn.execute(
        """
        INSERT INTO ads_campaign_product_daily (
            date, store_code, campaign_id, sku_key, cost_kzt, source_run_id, coverage_status
        ) VALUES ('2026-05-02', 'STOREB', 'CAMP_MG', 'SKU_MG', 0,
                  'ADS_STOREB', 'STOREB_BLOCKED')
        """
    )
    conn.commit()

    codes = _codes(db_path)

    assert "ADS_REFRESH_BLOCKED" in codes
    assert "ADS_COVERAGE_BLOCKED" in codes


def test_ads_coverage_scope_skips_inactive_store_date_pairs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    rows = [
        ("O_UNI", "2026-03-01", "UNIVERSAL"),
        ("O_11KZ", "2026-03-01", "11KZ"),
        ("O_MELVIS", "2026-03-01", "MELVIS"),
        ("O_STOREB_PRE", "2026-03-07", "STOREB"),
        ("O_ACMEWEAR_PRE", "2024-12-31", "ACMEWEAR"),
    ]
    for order_id, order_date, store_code in rows:
        sku_key = f"SKU_{order_id}"
        sku_id = f"{sku_key}_M"
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, status, return_flag
            ) VALUES (?, ?, ?, ?, 'M', 'Inactive scope offer', ?, 1, 'DELIVERED', 0)
            """,
            (order_id, order_date, sku_key, sku_id, store_code),
        )
        conn.execute(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source, idempotency_key
            ) VALUES (?, ?, 'COMPLETED', ?, 'fixture', ?)
            """,
            (store_code, order_id, f"{order_date}T10:00:00+05:00", f"ose-{order_id}"),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
            ) VALUES (?, ?, ?, ?, 1, 10000, 10000)
            """,
            (f"E_{order_id}", order_id, store_code, f"OFFER_{order_id}"),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                ref_type, ref_id, source, event_hash
            ) VALUES (?, 'CASH_IN', ?, 10000, ?, ?, ?, 'ORDER', ?, 'ORDER_MODELLED', ?)
            """,
            (
                order_date,
                f"KASPI_PAY_{store_code}",
                store_code,
                sku_key,
                sku_id,
                order_id,
                f"cash-{order_id}",
            ),
        )
    conn.commit()

    report = evaluate_operational_stock_integration_gates(db_path, as_of="2026-05-03")
    inactive_sku_keys = {f"SKU_{row[0]}" for row in rows}
    scoped_ads_findings = [
        finding
        for finding in report.findings
        if finding.code.startswith("ADS_")
        and finding.evidence.get("sku_key") in inactive_sku_keys
    ]

    assert scoped_ads_findings == []


def test_d1_delivered_order_cashflow_fixture_requires_same_day_cash_in(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_D1', 'COMPLETED', '2026-05-02T11:00:00+05:00',
                  'fixture', 'ose-O_D1-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (
            event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
            ref_type, ref_id, source, event_hash
        ) VALUES ('2026-05-02', 'CASH_IN', 'RECEIVABLES', 12000, 'ACMEWEAR',
                  'SKU_A', 'SKU_A_M', 'ORDER', 'O_D1', 'ORDER_MODELLED', 'recv-O_D1')
        """
    )
    conn.commit()

    codes = _codes(db_path)

    assert "CASHFLOW_D1_CASH_IN_MISSING" in codes
    assert "CASHFLOW_D1_RECEIVABLES_MODELED" in codes


def test_d1_cashflow_gate_respects_operational_as_of_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
            store_code, quantity, status, return_flag
        ) VALUES ('O_FUTURE_D1', '2026-05-04', 'SKU_FUT', 'SKU_FUT_M', 'M',
                  'Future offer', 'ACMEWEAR', 1, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO order_status_event (
            store_code, order_id, stage_code, event_ts, source, idempotency_key
        ) VALUES ('ACMEWEAR', 'O_FUTURE_D1', 'COMPLETED',
                  '2026-05-04T11:00:00+05:00', 'fixture',
                  'ose-O_FUTURE_D1-completed')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt,
            total_price_kzt
        ) VALUES ('E_FUTURE_D1', 'O_FUTURE_D1', 'ACMEWEAR', 'OFFER_FUT',
                  1, 12000, 12000)
        """
    )
    conn.commit()

    codes = _codes(db_path)

    assert "CASHFLOW_D1_CASH_IN_MISSING" not in codes


def test_cashflow_roll_forward_invariant_fixture_blocks_opening_reset(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = _connect(db_path)
    _seed_green_baseline(conn)
    conn.execute(
        """
        INSERT INTO fact_cashflow_daily (
            date, cash_open, cash_close, receivables_open, receivables_close,
            inventory_cost_open, inventory_cost_close, capital_close, cash_flow_kzt,
            receivables_flow_kzt, inventory_cost_flow_kzt, inventory_on_hand_close,
            inventory_inbound_close, inventory_on_delivery_close
        ) VALUES ('2026-05-03', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """
    )
    conn.commit()

    assert "CASHFLOW_OPENING_RESET" in _codes(db_path)
