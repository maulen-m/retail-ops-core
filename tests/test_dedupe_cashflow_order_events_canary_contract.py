from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from scripts.dedupe_cashflow_order_events import dedupe_order_events


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
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
                event_hash TEXT UNIQUE
            );
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES
                ('2026-02-22', 'CASH_IN', 'KASPI_PAY', 1000.0, 'UNIVERSAL', 'SKU1', 'SKU1_M', 'ORDER', 'O1', '', 'SYSTEM', 'R0', 'h1'),
                ('2026-02-22', 'CASH_IN', 'KASPI_PAY', 1000.0, 'UNIVERSAL', 'SKU1', 'SKU1_M', 'ORDER', 'O1', '', 'SYSTEM', 'R0', 'h2');
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_dedupe_canary_fails_closed_when_max_new_events_exceeded(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _init_db(db)
    with pytest.raises(RuntimeError, match="max_new_events"):
        dedupe_order_events(db, apply=False, run_id="TEST", max_new_events=0)


def test_dedupe_canary_apply_requires_env_gate_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    _init_db(db)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_WRITE=1"):
        dedupe_order_events(db, apply=True, run_id="R1", max_new_events=5)

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    inserted_first = dedupe_order_events(db, apply=True, run_id="R1", max_new_events=5)
    inserted_second = dedupe_order_events(db, apply=True, run_id="R1", max_new_events=5)
    assert inserted_first == 1
    assert inserted_second == 0

    conn = sqlite3.connect(str(db))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE source='ORDER_DEDUP'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
