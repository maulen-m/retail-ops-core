import os
import sqlite3
from pathlib import Path

from scripts import import_cashflow_balance_checks as importer
from scripts import update_cashflow_dashboard as dashboard


def _init_cashflow_events_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                account TEXT NOT NULL,
                amount_kzt REAL NOT NULL,
                store_code TEXT,
                ref_type TEXT,
                ref_id TEXT,
                notes TEXT,
                source TEXT,
                run_id TEXT,
                event_hash TEXT NOT NULL
            );
            CREATE UNIQUE INDEX idx_cashflow_events_hash ON fact_cashflow_events (event_hash);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_import_balance_checks_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "cashflow.db"
    _init_cashflow_events_db(db_path)

    config_path = tmp_path / "bank_accounts.yaml"
    config_path.write_text(
        "\n".join(
            [
                "as_of: 2026-01-24 13:49:00 GMT+5",
                "stores:",
                "  STOREB:",
                "    accounts:",
                "      kaspi_gold:",
                "        balance_kzt: 1000",
                "      binance_usdt:",
                "        balance_usdt: 2",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    importer.import_balance_checks(config_path, db_path, apply=True, run_id="TEST")
    conn = sqlite3.connect(str(db_path))
    try:
        first_count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
    finally:
        conn.close()

    importer.import_balance_checks(config_path, db_path, apply=True, run_id="TEST")
    conn = sqlite3.connect(str(db_path))
    try:
        second_count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
    finally:
        conn.close()

    assert first_count == second_count
    assert first_count > 0


def test_balance_check_drift_computation(tmp_path):
    db_path = tmp_path / "cashflow.db"
    _init_cashflow_events_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        events = [
            ("2026-01-10", "BALANCE_CHECK", "CASH", 1000.0, "STOREB"),
            ("2026-01-10", "BALANCE_CHECK", "CASH", 2000.0, "ACMEWEAR"),
            ("2026-01-10", "CASH_IN", "CASH", 900.0, "STOREB"),
            ("2026-01-10", "CASH_IN", "CASH", 2500.0, "ACMEWEAR"),
        ]
        for idx, (date, etype, account, amount, store) in enumerate(events):
            conn.execute(
                """
                INSERT INTO fact_cashflow_events (
                    event_date, event_type, account, amount_kzt, store_code,
                    ref_type, ref_id, source, run_id, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    etype,
                    account,
                    amount,
                    store,
                    etype,
                    f"{etype}-{idx}",
                    "SYSTEM",
                    "TEST",
                    f"hash-{idx}",
                ),
            )
        conn.commit()

        drift = dashboard._load_balance_check_drift(conn, "2026-01-10")
    finally:
        conn.close()

    assert drift["actual_total_kzt"] == 3000.0
    assert drift["model_total_kzt"] == 3400.0
    assert drift["drift_total_kzt"] == -400.0
    assert drift["by_store"]["STOREB"]["drift_kzt"] == 100.0
    assert drift["by_store"]["ACMEWEAR"]["drift_kzt"] == -500.0


def test_balance_check_currency_totals(tmp_path):
    config_path = tmp_path / "bank_accounts.yaml"
    config_path.write_text(
        "\n".join(
            [
                "as_of: 2026-01-28 14:11:00 GMT+5",
                "stores:",
                "  UNIVERSAL:",
                "    accounts:",
                "      kaspi_gold:",
                "        balance_kzt: 1000",
                "      cash_usd:",
                "        balance_usd: 2",
                "      binance_usdt:",
                "        balance_usdt: 3",
                "      cash_rub:",
                "        balance_rub: 10",
            ]
        ),
        encoding="utf-8",
    )

    summary = dashboard._load_balance_check_currency_totals(config_path, db_path=tmp_path / "db.db")

    assert summary["as_of_date"] == "2026-01-28"
    assert summary["by_currency"]["KZT"]["amount"] == 1000.0
    assert summary["by_currency"]["USD"]["amount"] == 2.0
    assert summary["by_currency"]["USDT"]["amount"] == 3.0
    assert summary["by_currency"]["RUB"]["amount"] == 10.0
    assert summary["by_currency"]["USD"]["kzt_equiv"] == 1060.0
    assert summary["by_currency"]["USDT"]["kzt_equiv"] == 1590.0
