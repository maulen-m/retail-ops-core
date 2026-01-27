import sqlite3
from datetime import date
from pathlib import Path

from scripts.translate_orders_to_cashflow_events import translate_orders


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                kaspi_status TEXT,
                internal_status TEXT,
                status_updated_at TEXT,
                actual_shipment_date TEXT,
                planned_shipment_date TEXT,
                created_at TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                sku_key TEXT,
                sku_id TEXT
            );
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
            CREATE TABLE dim_sku (
                sku_key TEXT,
                weight_kg REAL,
                cogs_kzt REAL,
                base_cost_cny REAL
            );
            """
        )
    finally:
        conn.close()


def test_translate_orders_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU1", 0.95, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD1",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                2,
                12000,
                "SKU1",
                "SKU1_S",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
        assert count == 2  # cash in + cogs recognized
    finally:
        conn.close()


def test_translate_orders_refund_requires_sale(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU2", 0.95, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD2",
                "UNIVERSAL",
                "Возврат",
                "CANCELLED",
                "2026-01-21",
                1,
                12000,
                "SKU2",
                "SKU2_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, ref_type, ref_id, source, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-20", "CASH_IN", "KASPI_PAY_UNIVERSAL", 1000, "ORDER", "ORD2", "ORDER_MODELLED", "hash"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 20), until=date(2026, 1, 22), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        refund_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type = 'CASH_IN' AND amount_kzt < 0"
        ).fetchone()[0]
        assert refund_count == 1
    finally:
        conn.close()
