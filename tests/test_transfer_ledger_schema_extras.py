import sqlite3

from core.transfer_ledger import repository


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def test_schema_has_transfer_ledger_extras(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    repository.ensure_schema(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        assert _has_column(conn, "binance_c2c_orders", "account_label")
        assert _has_column(conn, "binance_withdrawals", "account_label")

        for table in [
            "binance_deposits",
            "binance_transfers",
            "binance_account_snapshots",
            "binance_funding_balances",
            "exchanger_order_events",
            "po_funding_plan",
            "po_exchanger_allocations",
            "gmail_sync_state",
        ]:
            assert _table_exists(conn, table)
