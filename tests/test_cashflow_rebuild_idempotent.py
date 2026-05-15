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


def test_partial_cashflow_rebuild_carries_previous_daily_close(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_cashflow_db(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close,
                inventory_on_hand_open, inventory_on_hand_close,
                inventory_inbound_open, inventory_inbound_close,
                inventory_on_delivery_open, inventory_on_delivery_close,
                sales_accrued_kzt, payouts_received_kzt, refunds_kzt, po_payments_kzt,
                expenses_kzt, cogs_kzt, cash_flow_kzt, receivables_flow_kzt,
                inventory_cost_flow_kzt, profit_accrual_kzt, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-01",
                900,
                1000,
                40,
                50,
                490,
                500,
                1550,
                190,
                200,
                290,
                300,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                100,
                10,
                10,
                0,
                "prior",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, source, run_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-02", "CASH_IN", "KASPI_PAY_TEST", 250, "ORDER_MODELLED", "event"),
        )
        conn.commit()
    finally:
        conn.close()

    rows, _ = rebuild_cashflow_calendar(
        db_path=db_path,
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 2),
        apply=True,
        run_id="partial",
    )

    assert rows[0]["cash_open"] == 1000
    assert rows[0]["cash_close"] == 1250
    assert rows[0]["receivables_open"] == 50
    assert rows[0]["receivables_close"] == 50
    assert rows[0]["inventory_on_hand_open"] == 200
    assert rows[0]["inventory_inbound_open"] == 300
    assert rows[0]["inventory_cost_open"] == 500
    assert rows[0]["capital_close"] == 1800
