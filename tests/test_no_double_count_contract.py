from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

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
        ) VALUES (1, '2026-02-26', 15000, 'KZT', 'PO', 'PO-6', 'Kaspi', 'Supplier', 'fixture')
        """
    )
    conn.commit()
    conn.close()


def _count_events(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0])


def test_apply_requires_env_gate_and_backup(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    backup = tmp_path / "backup.sqlite"
    backup.write_text("backup", encoding="utf-8")
    monkeypatch.delenv("ENABLE_CASHFLOW_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_WRITE=1"):
        translate_transfer_ledger_to_cashflow(
            db_path=db_path,
            as_of="2026-02-26",
            output_root=tmp_path,
            apply=True,
            backup_path=backup,
            strict=True,
        )


def test_apply_does_not_double_count_on_rerun(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    backup = tmp_path / "backup.sqlite"
    backup.write_text("backup", encoding="utf-8")
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    first = translate_transfer_ledger_to_cashflow(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        apply=True,
        backup_path=backup,
        strict=True,
    )
    assert first["ok"] is True
    assert first["payload"]["applied_count"] == 2
    assert _count_events(db_path) == 2

    second = translate_transfer_ledger_to_cashflow(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        apply=True,
        backup_path=backup,
        strict=True,
    )
    assert second["ok"] is True
    assert second["payload"]["applied_count"] == 0
    assert second["payload"]["post_apply_dry_run_count"] == 0
    assert _count_events(db_path) == 2
