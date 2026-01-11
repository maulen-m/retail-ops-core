import sqlite3
from datetime import datetime

from core.transfer_ledger.fx_derive import derive_daily_fx_rows


def test_derive_daily_fx_rows(tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE binance_c2c_orders (
                create_time TEXT,
                fiat_amount REAL,
                crypto_amount REAL,
                trade_type TEXT,
                asset TEXT,
                fiat TEXT,
                order_status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE exchanger_orders (
                message_date TEXT,
                amount_usdt REAL,
                amount_cny REAL,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO binance_c2c_orders
            (create_time, fiat_amount, crypto_amount, trade_type, asset, fiat, order_status)
            VALUES
            ('2026-01-09T10:00:00+05:00', 100000, 200, 'BUY', 'USDT', 'KZT', 'COMPLETED')
            """
        )
        conn.execute(
            """
            INSERT INTO exchanger_orders
            (message_date, amount_usdt, amount_cny, status)
            VALUES
            ('2026-01-09T12:00:00+05:00', 100, 680, 'COMPLETED')
            """
        )
        conn.commit()
    finally:
        conn.close()

    rows = derive_daily_fx_rows(db_path=db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["effective_date"] == "2026-01-09"
    assert abs(row["usdt_kzt"] - 500.0) < 1e-6
    assert abs(row["usdt_cny"] - 6.8) < 1e-6
    assert abs(row["cny_kzt"] - (500.0 / 6.8)) < 1e-6
