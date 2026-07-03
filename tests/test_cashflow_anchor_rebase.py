import sqlite3
from datetime import date
from pathlib import Path

from scripts import cashflow_preflight_po as preflight
from scripts.cashflow_preflight_po import evaluate_preflight
from scripts.rebuild_cashflow_calendar import rebuild_cashflow_calendar


def _init_anchor_rebase_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_ts TEXT,
                event_type TEXT NOT NULL,
                account TEXT NOT NULL,
                amount_kzt REAL NOT NULL,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                ref_type TEXT,
                ref_id TEXT,
                notes TEXT,
                source TEXT NOT NULL DEFAULT 'SYSTEM',
                run_id TEXT,
                event_hash TEXT NOT NULL
            );

            CREATE TABLE fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                cash_open REAL NOT NULL DEFAULT 0,
                cash_close REAL NOT NULL DEFAULT 0,
                receivables_open REAL NOT NULL DEFAULT 0,
                receivables_close REAL NOT NULL DEFAULT 0,
                inventory_cost_open REAL NOT NULL DEFAULT 0,
                inventory_cost_close REAL NOT NULL DEFAULT 0,
                capital_close REAL NOT NULL DEFAULT 0,
                inventory_on_hand_open REAL NOT NULL DEFAULT 0,
                inventory_on_hand_close REAL NOT NULL DEFAULT 0,
                inventory_inbound_open REAL NOT NULL DEFAULT 0,
                inventory_inbound_close REAL NOT NULL DEFAULT 0,
                inventory_on_delivery_open REAL NOT NULL DEFAULT 0,
                inventory_on_delivery_close REAL NOT NULL DEFAULT 0,
                sales_accrued_kzt REAL NOT NULL DEFAULT 0,
                payouts_received_kzt REAL NOT NULL DEFAULT 0,
                refunds_kzt REAL NOT NULL DEFAULT 0,
                po_payments_kzt REAL NOT NULL DEFAULT 0,
                expenses_kzt REAL NOT NULL DEFAULT 0,
                cogs_kzt REAL NOT NULL DEFAULT 0,
                cash_flow_kzt REAL NOT NULL DEFAULT 0,
                receivables_flow_kzt REAL NOT NULL DEFAULT 0,
                inventory_cost_flow_kzt REAL NOT NULL DEFAULT 0,
                profit_accrual_kzt REAL NOT NULL DEFAULT 0,
                run_id TEXT
            );

            CREATE TABLE cashflow_cash_anchor (
                anchor_date TEXT NOT NULL,
                anchor_closing_balance_kzt REAL NOT NULL,
                reconciliation_status TEXT NOT NULL,
                trust_class TEXT NOT NULL,
                created_by_run_id TEXT NOT NULL,
                created_at TEXT,
                source_store_dir TEXT,
                notes_redacted TEXT
            );
            """
        )
        conn.executemany(
            """
            INSERT INTO cashflow_cash_anchor (
                anchor_date, anchor_closing_balance_kzt, reconciliation_status, trust_class,
                created_by_run_id, created_at, source_store_dir, notes_redacted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-01-03",
                    600.0,
                    "RECONCILED",
                    "ACTUAL_ANCHOR",
                    "anchor-run",
                    "2026-01-03 12:01:00",
                    "owner.xlsx :: sheet Cash_Balances :: 03.01.2026_12_00_00",
                    "reserve_kzt=100; grand_total_with_reserve_kzt=1100",
                ),
                (
                    "2026-01-03",
                    400.0,
                    "RECONCILED",
                    "ACTUAL_ANCHOR",
                    "anchor-run",
                    "2026-01-03 12:01:00",
                    "owner.xlsx :: sheet Cash_Balances :: 03.01.2026_12_00_00",
                    "reserve_kzt=100; grand_total_with_reserve_kzt=1100",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_ts, event_type, account, amount_kzt,
                source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-01-02", None, "CASH_IN", "KASPI_PAY_TEST", 500.0, "ORDER_MODELLED", "events", "h1"),
                ("2026-01-03", None, "CASH_IN", "KASPI_PAY_TEST", 700.0, "ORDER_MODELLED", "events", "h2"),
                (
                    "2026-01-03",
                    "2026-01-03T12:05:00",
                    "CASH_IN",
                    "KASPI_PAY_TEST",
                    50.0,
                    "ORDER_MODELLED",
                    "events",
                    "h3",
                ),
                ("2026-01-04", None, "CASH_IN", "KASPI_PAY_TEST", 200.0, "ORDER_MODELLED", "events", "h4"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_daily_row(conn: sqlite3.Connection, day: str, cash_close: float, sales: float = 0.0) -> None:
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
        ) VALUES (?, 0, ?, 0, 0, 0, 0, ?, 0, 0, 0, 0, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, ?, 'daily')
        """,
        (day, cash_close, cash_close, sales, sales),
    )


def test_rebuild_rebases_cash_at_actual_anchor_without_replaying_past_events(tmp_path):
    db_path = tmp_path / "cashflow.db"
    _init_anchor_rebase_db(db_path)

    rows, _ = rebuild_cashflow_calendar(
        db_path=db_path,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 4),
        apply=False,
        run_id="rebase-test",
    )

    by_date = {row["date"]: row for row in rows}
    assert by_date["2026-01-02"]["cash_close"] == 500.0
    assert by_date["2026-01-03"]["cash_open"] == 1000.0
    assert by_date["2026-01-03"]["cash_flow_kzt"] == 50.0
    assert by_date["2026-01-03"]["cash_close"] == 1050.0
    assert by_date["2026-01-04"]["cash_open"] == 1050.0
    assert by_date["2026-01-04"]["cash_close"] == 1250.0


def test_preflight_uses_anchor_opening_instead_of_replayed_daily_close(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_anchor_rebase_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _insert_daily_row(conn, "2026-01-02", 5000.0, sales=100.0)
        _insert_daily_row(conn, "2026-01-03", 6500.0, sales=100.0)
        conn.commit()

    class DummyPayout:
        base_lag_days = 0
        conservative_lag_days = 0

    monkeypatch.setattr(preflight, "get_cutoff_date_almaty", lambda: date(2026, 1, 3))
    monkeypatch.setattr(preflight, "load_payout_model", lambda: DummyPayout())

    result = evaluate_preflight(
        db_path=db_path,
        horizon_days=2,
        scenario="base",
        min_cash_threshold=3000.0,
    )

    assert result.ok is False
    assert result.min_cash == 1050.0
    assert result.min_cash_date == "2026-01-03"
    assert result.anchor_date == "2026-01-03"
    assert result.anchor_opening_cash == 1000.0
    assert result.modelled_inflows_after_anchor is True
    assert result.forecast_modelled_inflows is True
