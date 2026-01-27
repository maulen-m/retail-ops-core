import sqlite3
from datetime import date
from pathlib import Path

from scripts.rebuild_cashflow_calendar import rebuild_cashflow_calendar


def _init_cashflow_db(db_path: Path) -> None:
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

            CREATE TABLE fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                cash_open REAL,
                cash_close REAL,
                receivables_open REAL,
                receivables_close REAL,
                inventory_cost_open REAL,
                inventory_cost_close REAL,
                capital_close REAL,
                inventory_on_hand_open REAL,
                inventory_on_hand_close REAL,
                inventory_inbound_open REAL,
                inventory_inbound_close REAL,
                inventory_on_delivery_open REAL,
                inventory_on_delivery_close REAL,
                sales_accrued_kzt REAL,
                payouts_received_kzt REAL,
                refunds_kzt REAL,
                po_payments_kzt REAL,
                expenses_kzt REAL,
                cogs_kzt REAL,
                cash_flow_kzt REAL,
                receivables_flow_kzt REAL,
                inventory_cost_flow_kzt REAL,
                profit_accrual_kzt REAL,
                run_id TEXT
            );

            CREATE TABLE fact_sales (
                order_date TEXT,
                quantity REAL,
                cogs_unit REAL
            );
            """
        )
        conn.execute(
            "INSERT INTO fact_sales (order_date, quantity, cogs_unit) VALUES (?, ?, ?)",
            ("2026-01-01", 1, 1000),
        )
        conn.commit()
    finally:
        conn.close()


def test_cashflow_rebuild_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_cashflow_db(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    start = date(2026, 1, 1)
    end = date(2026, 1, 1)

    rows_first, _ = rebuild_cashflow_calendar(
        db_path=db_path, start_date=start, end_date=end, apply=True, run_id="test"
    )
    rows_second, _ = rebuild_cashflow_calendar(
        db_path=db_path, start_date=start, end_date=end, apply=True, run_id="test"
    )

    conn = sqlite3.connect(str(db_path))
    try:
        event_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_cashflow_events
            WHERE event_type = 'COGS_RECOGNIZED' AND source = 'SYSTEM'
            """
        ).fetchone()[0]
        daily_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_daily"
        ).fetchone()[0]
    finally:
        conn.close()

    assert event_count == 1
    assert daily_count == 1
    assert rows_first == rows_second
