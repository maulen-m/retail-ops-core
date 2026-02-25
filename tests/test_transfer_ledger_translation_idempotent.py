from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.translate_transfer_ledger_to_cashflow import translate_transfer_ledger_to_cashflow


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE transfer_ledger (
            entry_id INTEGER PRIMARY KEY,
            entry_date TEXT,
            amount_kzt REAL,
            currency TEXT,
            reference_type TEXT,
            reference_id TEXT,
            from_account TEXT,
            to_account TEXT,
            notes TEXT
        );
        CREATE TABLE fact_cashflow_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            event_hash TEXT UNIQUE
        );
        """
    )
    conn.execute(
        """
        INSERT INTO transfer_ledger (
            entry_id, entry_date, amount_kzt, currency, reference_type, reference_id,
            from_account, to_account, notes
        ) VALUES (1, '2026-02-26', 10000, 'KZT', 'PO', 'PO-5', 'Kaspi', 'Supplier', 'fixture')
        """
    )
    conn.commit()
    conn.close()


def test_transfer_translation_dry_run_idempotence(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    report = translate_transfer_ledger_to_cashflow(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
        apply=False,
    )
    assert report["ok"] is True
    payload = report["payload"]
    assert payload["dry_run_first_count"] == 2
    assert payload["dry_run_second_count"] == 2
    assert payload["applied_count"] == 0
