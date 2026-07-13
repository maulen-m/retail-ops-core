import sqlite3
import hashlib
from datetime import date
from pathlib import Path

from scripts.rebuild_cashflow_calendar import compute_daily_rows
from scripts.validate_cashflow_invariants import validate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_daily_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
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
                cash_flow_kzt REAL,
                receivables_flow_kzt REAL,
                inventory_cost_flow_kzt REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close,
                inventory_on_hand_open, inventory_on_hand_close,
                inventory_inbound_open, inventory_inbound_close,
                inventory_on_delivery_open, inventory_on_delivery_close,
                cash_flow_kzt, receivables_flow_kzt, inventory_cost_flow_kzt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-02",
                100.0,
                100.0,
                0.0,
                0.0,
                0.0,
                0.0,
                100.0,
                0.0,
                -1.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_inventory_accounts_never_negative(tmp_path):
    db_path = tmp_path / "cashflow.db"
    _init_daily_db(db_path)
    db_sha_before = _sha256(db_path)
    assert validate(db_path, tolerance=0.01) == 1
    assert _sha256(db_path) == db_sha_before


def test_inbound_to_onhand_transfer_no_cash_effect():
    events = [
        {
            "event_date": "2026-01-01",
            "event_type": "INVENTORY_MOVE",
            "account": "INVENTORY_INBOUND_COST",
            "amount_kzt": -500.0,
        },
        {
            "event_date": "2026-01-01",
            "event_type": "INVENTORY_MOVE",
            "account": "INVENTORY_ON_HAND_COST",
            "amount_kzt": 500.0,
        },
    ]
    rows = compute_daily_rows(events, date(2026, 1, 1), date(2026, 1, 1), run_id="test")
    row = rows[0]
    assert row["inventory_cost_flow_kzt"] == 0.0
    assert row["cash_flow_kzt"] == 0.0
