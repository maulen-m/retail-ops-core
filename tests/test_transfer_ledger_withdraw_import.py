import sqlite3
from datetime import datetime, timezone

from core.transfer_ledger.binance_withdraw_import import normalize_binance_withdrawal, import_binance_withdrawals
from core.transfer_ledger import repository


def seed_fx(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_fx_rates (
                effective_date TEXT PRIMARY KEY,
                usdt_kzt REAL NOT NULL,
                usdt_cny REAL NOT NULL,
                cny_kzt REAL NOT NULL,
                usd_kzt REAL NOT NULL,
                dlv_rate_usd_kg REAL NOT NULL,
                provider TEXT,
                source TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO dim_fx_rates
            (effective_date, usdt_kzt, usdt_cny, cny_kzt, usd_kzt, dlv_rate_usd_kg, provider, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            ("2026-01-01", 500.0, 6.8, 73.5, 520.0, 2.66, "MANUAL", "pytest"),
        )
        conn.commit()
    finally:
        conn.close()


def test_withdraw_import_creates_ledger(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.touch()
    seed_fx(db_path)

    raw = {
        "id": "wd-123",
        "coin": "USDT",
        "network": "TRX",
        "amount": "100",
        "transactionFee": "1",
        "address": "Txxxx",
        "applyTime": int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        "status": 6,
    }

    wd = normalize_binance_withdrawal(raw)
    assert wd["withdraw_id"] == "wd-123"
    assert wd["amount"] == 100.0

    result = import_binance_withdrawals([raw], db_path=db_path, write_ledger=True, auto_allocate=False)
    assert result["inserted"] == 1
    assert result["ledger_entries"] == 1

    entries = repository.list_entries(db_path=db_path)
    assert len(entries) >= 1
