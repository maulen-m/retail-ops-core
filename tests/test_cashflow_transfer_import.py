import sqlite3
from datetime import date
from pathlib import Path

from scripts.import_transfer_ledger_cashflow import import_transfer_ledger


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE transfer_ledger (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                amount_kzt REAL NOT NULL,
                fx_rate_to_kzt REAL NOT NULL,
                fx_source TEXT NOT NULL DEFAULT 'MANUAL',
                reference_type TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                from_account TEXT,
                to_account TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
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
                notes TEXT,
                source TEXT,
                run_id TEXT,
                event_hash TEXT
            );
            """
        )
    finally:
        conn.close()


def test_transfer_import_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO transfer_ledger (
                entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
                fx_source, reference_type, reference_id, from_account, to_account, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-10",
                1000,
                "KZT",
                1000,
                1.0,
                "MANUAL",
                "TRANSFER",
                "T-001",
                "wallet",
                "bank",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    added = import_transfer_ledger(db_path, since=date(2026, 1, 10), until=date(2026, 1, 10), apply=True, run_id="test")
    assert added == 2

    added_again = import_transfer_ledger(db_path, since=date(2026, 1, 10), until=date(2026, 1, 10), apply=True, run_id="test")
    assert added_again == 0

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id = 'T-001'").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_no_double_count_statement_vs_transfer_ledger(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, ref_type, ref_id, source, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-10",
                "UNKNOWN",
                "CASH",
                -1000,
                "MT940",
                "ACC:1",
                "STATEMENT_ACTUAL",
                "hash1",
            ),
        )
        conn.execute(
            """
            INSERT INTO transfer_ledger (
                entry_date, amount, currency, amount_kzt, fx_rate_to_kzt,
                fx_source, reference_type, reference_id, from_account, to_account, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-10",
                1000,
                "KZT",
                1000,
                1.0,
                "MANUAL",
                "PO",
                "PO-001",
                "",
                "",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    added = import_transfer_ledger(db_path, since=date(2026, 1, 10), until=date(2026, 1, 10), apply=True, run_id="test")
    assert added == 1  # inventory inbound only; cash event skipped

    conn = sqlite3.connect(str(db_path))
    try:
        cash_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id = 'PO-001' AND event_type = 'PO_PAYMENT'"
        ).fetchone()[0]
        inv_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id = 'PO-001' AND account = 'INVENTORY_INBOUND_COST'"
        ).fetchone()[0]
        assert cash_count == 0
        assert inv_count == 1
    finally:
        conn.close()
