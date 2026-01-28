import sqlite3
from pathlib import Path

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
                event_hash TEXT
            );
            """
        )
    finally:
        conn.close()


def test_dedupe_cashflow_order_events(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-01-20", "CASH_IN", "KASPI_PAY_UNIVERSAL", 1000, "UNIVERSAL", "SKU1", "SKU1_S", "ORDER", "ORD1", "", "ORDER_MODELLED", "run1", "h1"),
                ("2026-01-21", "CASH_IN", "KASPI_PAY_UNIVERSAL", 1000, "UNIVERSAL", "SKU1", "SKU1_S", "ORDER", "ORD1", "", "ORDER_MODELLED", "run2", "h2"),
                ("2026-01-20", "COGS_RECOGNIZED", "INVENTORY_ON_DELIVERY_COST", -500, "UNIVERSAL", "SKU1", "SKU1_S", "ORDER", "ORD1", "", "ORDER_MODELLED", "run1", "h3"),
                ("2026-01-21", "COGS_RECOGNIZED", "INVENTORY_ON_DELIVERY_COST", -500, "UNIVERSAL", "SKU1", "SKU1_S", "ORDER", "ORD1", "", "ORDER_MODELLED", "run2", "h4"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    added = dedupe_order_events(db_path, apply=True, run_id="dedupe_test")
    assert added == 2

    conn = sqlite3.connect(str(db_path))
    try:
        cash_sum = conn.execute(
            "SELECT SUM(amount_kzt) FROM fact_cashflow_events WHERE ref_id='ORD1' AND event_type='CASH_IN'"
        ).fetchone()[0]
        cogs_sum = conn.execute(
            "SELECT SUM(amount_kzt) FROM fact_cashflow_events WHERE ref_id='ORD1' AND event_type='COGS_RECOGNIZED'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert cash_sum == 1000
    assert cogs_sum == -500

    added_again = dedupe_order_events(db_path, apply=True, run_id="dedupe_test")
    assert added_again == 0
