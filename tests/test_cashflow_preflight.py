import sqlite3
from datetime import date
from pathlib import Path

from core.db.queries import get_cutoff_date_almaty
from scripts.cashflow_preflight_po import evaluate_preflight


def _init_db(db_path: Path, cash_close: float) -> None:
    cutoff = get_cutoff_date_almaty().isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_daily (
                date TEXT,
                cash_open REAL,
                cash_close REAL,
                receivables_open REAL,
                receivables_close REAL,
                inventory_cost_open REAL,
                inventory_cost_close REAL,
                capital_close REAL,
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
            CREATE TABLE fact_cashflow_commitments (
                commit_date TEXT,
                commit_type TEXT,
                amount_kzt REAL,
                scenario_tag TEXT,
                ref_id TEXT,
                notes TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close,
                sales_accrued_kzt, payouts_received_kzt, refunds_kzt, po_payments_kzt,
                expenses_kzt, cogs_kzt, cash_flow_kzt, receivables_flow_kzt,
                inventory_cost_flow_kzt, profit_accrual_kzt, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cutoff,
                0,
                cash_close,
                0,
                0,
                0,
                0,
                cash_close,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "test",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_preflight_fails_on_negative_cash(tmp_path):
    db_path = tmp_path / "preflight.db"
    _init_db(db_path, cash_close=-100)
    result = evaluate_preflight(db_path, horizon_days=10, scenario="base", min_cash_threshold=0)
    assert result.ok is False


def test_preflight_passes_on_positive_cash(tmp_path):
    db_path = tmp_path / "preflight.db"
    _init_db(db_path, cash_close=100)
    result = evaluate_preflight(db_path, horizon_days=10, scenario="base", min_cash_threshold=0)
    assert result.ok is True
