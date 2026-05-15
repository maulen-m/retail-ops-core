from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.materialize_stock_ledger_sales_from_sales_fact_v2 import run_materialization


def _create_stock_materializer_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT DEFAULT 'DELIVERED',
            return_flag INTEGER DEFAULT 0,
            return_date DATE,
            ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            source_file TEXT,
            api_updated_at DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date DATE NOT NULL,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            idempotency_key TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE return_qc_event (
            qc_event_id TEXT PRIMARY KEY,
            store_code TEXT,
            order_id TEXT,
            sku_id TEXT,
            quantity INTEGER,
            accepted_active_qty INTEGER,
            quarantine_qty INTEGER,
            rejected_qty INTEGER,
            writeoff_qty INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX ux_stock_ledger_idempotency_key
        ON stock_ledger(idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, status, return_flag, return_date, source_file
        ) VALUES
            ('SALE-1', '2026-04-20', 'SKU_A', 'SKU_A_M', 'M', 'Offer A', 'UNIVERSAL',
             2, 10000, 'DELIVERED', 0, NULL, 'KASPI_API_ENTRIES_REBUILD'),
            ('RET-1', '2026-04-21', 'SKU_A', 'SKU_A_M', 'M', 'Offer A', 'UNIVERSAL',
             1, 10000, 'RETURNED', 1, '2026-04-22', 'KASPI_API_ENTRIES_REBUILD')
        """
    )
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, running_balance, reference_id, reference_type, idempotency_key
        ) VALUES ('2026-04-19', 'ADJUSTMENT', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL',
                  5, 5, 'manual-1', 'ADJUSTMENT', 'manual:1')
        """
    )
    conn.commit()
    conn.close()


def test_stock_ledger_sales_materializer_is_dry_run_by_default_and_env_gated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _create_stock_materializer_db(db_path)

    dry = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "dry",
        apply=False,
    )
    assert dry["candidate_count"] == 2
    assert dry["insert_count"] == 2
    assert dry["active_return_units"] == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0] == 1

    with pytest.raises(RuntimeError, match="ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE=1"):
        run_materialization(
            db_path=db_path,
            start_date=date(2026, 4, 16),
            end_date=date(2026, 5, 4),
            output_root=tmp_path / "blocked",
            apply=True,
        )

    monkeypatch.setenv("ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE", "1")
    applied = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "apply",
        apply=True,
    )
    assert applied["rows_applied"] == 2

    second = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "apply_again",
        apply=True,
    )
    assert second["insert_count"] == 0
    assert second["rows_applied"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_type, qty_change, reference_id, reference_type
            FROM stock_ledger
            ORDER BY ledger_id
            """
        ).fetchall()

    assert rows == [
        ("ADJUSTMENT", 5, "manual-1", "ADJUSTMENT"),
        ("SALE", -2, "SALE-1", "SALE"),
        ("SALE", -1, "RET-1", "SALE"),
    ]


def test_stock_ledger_sales_materializer_only_activates_qc_accepted_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _create_stock_materializer_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO return_qc_event (
                qc_event_id, store_code, order_id, sku_id, quantity,
                accepted_active_qty, quarantine_qty, rejected_qty, writeoff_qty
            ) VALUES ('QC-RET-1', 'UNIVERSAL', 'RET-1', 'SKU_A_M', 1, 1, 0, 0, 0)
            """
        )
        conn.commit()

    monkeypatch.setenv("ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE", "1")
    applied = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "apply_qc",
        apply=True,
    )

    assert applied["rows_applied"] == 3
    assert applied["active_return_units"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT event_type, qty_change, notes
            FROM stock_ledger
            WHERE event_type='RETURN'
            """
        ).fetchone()

    assert row == (
        "RETURN",
        1,
        "sales_fact_v2 stock replay RETURN after QC accepted_active_qty",
    )


def test_stock_ledger_sales_materializer_skips_product_identity_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _create_stock_materializer_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE fact_order_entry_product_identity_quarantine (
                store_code TEXT NOT NULL,
                order_id TEXT NOT NULL,
                publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
                active_flag INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (store_code, order_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
                quantity, sell_price_kzt, status, return_flag, return_date, source_file
            ) VALUES ('Q-SALE', '2026-04-23', 'SKU_Q', 'SKU_Q_M', 'M', 'Header fallback',
                      'STOREB', 1, 12000, 'DELIVERED', 0, NULL,
                      'KASPI_API_HEADER_FALLBACK_REBUILD')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entry_product_identity_quarantine (
                store_code, order_id, publication_exclusion_required, active_flag
            ) VALUES ('STOREB', 'Q-SALE', 1, 1)
            """
        )
        conn.commit()

    monkeypatch.setenv("ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE", "1")
    applied = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "apply_quarantine",
        apply=True,
    )

    assert applied["candidate_count"] == 2
    assert applied["quarantined_order_count"] == 1
    with sqlite3.connect(db_path) as conn:
        leaked = conn.execute(
            "SELECT COUNT(*) FROM stock_ledger WHERE reference_id='Q-SALE'"
        ).fetchone()[0]

    assert leaked == 0


def test_stock_ledger_sales_materializer_skips_header_only_source_gap_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _create_stock_materializer_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE fact_order_entry_header_only_source_gap_quarantine (
                store_code TEXT NOT NULL,
                order_id TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
                product_stock_excluded INTEGER NOT NULL DEFAULT 1,
                active_flag INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (store_code, order_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
                quantity, sell_price_kzt, status, return_flag, return_date, source_file
            ) VALUES ('Q-HDR', '2026-04-24', 'SKU_HDR', 'SKU_HDR_M', 'M', 'Header fallback',
                      'STOREB', 1, 12000, 'DELIVERED', 0, NULL,
                      'KASPI_API_HEADER_FALLBACK_REBUILD')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entry_header_only_source_gap_quarantine (
                store_code, order_id, reason_code, publication_exclusion_required,
                product_stock_excluded, active_flag
            ) VALUES (
                'STOREB', 'Q-HDR', 'HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE',
                1, 1, 1
            )
            """
        )
        conn.commit()

    monkeypatch.setenv("ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE", "1")
    applied = run_materialization(
        db_path=db_path,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 5, 4),
        output_root=tmp_path / "apply_header_only_quarantine",
        apply=True,
    )

    assert applied["candidate_count"] == 2
    assert applied["header_only_source_gap_quarantined_order_count"] == 1
    with sqlite3.connect(db_path) as conn:
        leaked = conn.execute(
            "SELECT COUNT(*) FROM stock_ledger WHERE reference_id='Q-HDR'"
        ).fetchone()[0]

    assert leaked == 0
