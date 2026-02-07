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
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT,
                order_id TEXT,
                store_code TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_article TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT
            );
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity REAL,
                sell_price_kzt REAL
            );
            """
        )
    finally:
        conn.close()


def test_translate_orders_resolves_entries_when_sku_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_ENTRY", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_ENTRY",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("E1", "ORD_ENTRY", "UNIVERSAL", "OFFER1", 2, 12000, 24000, None),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, sku_key, sku_id
            ) VALUES (?, ?, ?, ?)
            """,
            ("UNIVERSAL", "OFFER1", "SKU_ENTRY", "SKU_ENTRY_S"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        cogs = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='COGS_RECOGNIZED' AND amount_kzt != 0"
        ).fetchone()[0]
        moves = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='INVENTORY_MOVE' AND amount_kzt != 0"
        ).fetchone()[0]
        assert cogs == 1
        assert moves == 2
    finally:
        conn.close()


def test_translate_orders_errors_when_sku_unresolved(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_MISS",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    try:
        translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")
        assert False, "Expected RuntimeError for missing SKU resolution"
    except RuntimeError as exc:
        msg = str(exc).lower()
        assert "enrichment" in msg
        assert "dim_kaspi_article_map" in msg


def test_translate_orders_resolves_from_sales_fact_v2_when_entries_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_SF2", 1.0, 4000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SF2",
                "STOREB",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                10000,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, store_code, sku_key, sku_id, quantity, sell_price_kzt
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ORD_SF2", "STOREB", "SKU_SF2", "SKU_SF2_M", 1, 10000),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        cogs = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_SF2' AND event_type='COGS_RECOGNIZED'"
        ).fetchone()[0]
        assert cogs == 1
    finally:
        conn.close()


def test_translate_orders_allows_missing_sku_for_new_status(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_NEW",
                "UNIVERSAL",
                "Новый",
                "NEW",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_translate_orders_ignores_cancelled_missing_sku_without_sale(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_CANCEL_NO_SALE",
                "UNIVERSAL",
                "Отменен",
                "CANCELLED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_translate_orders_ignores_accepted_kaspi_delivery_missing_sku(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                actual_shipment_date, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_ACCEPTED_NO_SKU",
                "UNIVERSAL",
                "KASPI_DELIVERY",
                "ACCEPTED",
                "2026-01-20",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_translate_orders_ignores_shadow_missing_sku_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_SHADOW", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHADOW",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                "SKU_SHADOW",
                "SKU_SHADOW_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHADOW",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_SHADOW'"
        ).fetchone()[0]
        assert count == 4
    finally:
        conn.close()


def test_translate_orders_ignores_shadow_missing_sku_outside_window(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_SHADOW_OLD", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHADOW_OLD",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2025-12-20",
                1,
                12000,
                "SKU_SHADOW_OLD",
                "SKU_SHADOW_OLD_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHADOW_OLD",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_SHADOW_OLD'"
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_translate_orders_skips_unknown_shadow_when_resolved_row_exists(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_RESOLVED", 1.0, 100.0, 0),
        )
        # Resolved API row exists outside current translate window.
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_DUP",
                "STOREB",
                "Завершен",
                "COMPLETED",
                "2026-02-07",
                1,
                12000,
                "SKU_RESOLVED",
                "SKU_RESOLVED_S",
            ),
        )
        # Legacy shadow row inside current window.
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                planned_shipment_date, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_DUP",
                "UNKNOWN",
                "Завершен",
                "COMPLETED",
                None,
                "2026-02-04",
                2,
                12000,
                "SKU_RESOLVED",
                "SKU_RESOLVED_S",
            ),
        )
        # Existing sale is already recorded (cash present, cogs absent) to mimic backfill branch.
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-04",
                "CASH_IN",
                "KASPI_PAY_STOREB",
                1000.0,
                "STOREB",
                "SKU_RESOLVED",
                "SKU_RESOLVED_S",
                "ORDER",
                "ORD_DUP",
                "",
                "ORDER_MODELLED",
                "seed",
                "ord_dup_cash",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 2, 1), until=date(2026, 2, 5), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        added = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id='ORD_DUP' AND event_hash != 'ord_dup_cash'
            """
        ).fetchone()[0]
        assert added == 0
    finally:
        conn.close()


def test_translate_orders_corrects_on_delivery_balance_for_completed_existing_sales(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_BAL", 1.0, 100.0, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_BAL",
                "STOREB",
                "Завершен",
                "COMPLETED",
                "2026-02-07",
                1,
                12000,
                "SKU_BAL",
                "SKU_BAL_S",
            ),
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-02-04",
                    "CASH_IN",
                    "KASPI_PAY_STOREB",
                    1000.0,
                    "STOREB",
                    "SKU_BAL",
                    "SKU_BAL_S",
                    "ORDER",
                    "ORD_BAL",
                    "",
                    "ORDER_MODELLED",
                    "seed",
                    "ord_bal_cash",
                ),
                (
                    "2026-02-04",
                    "INVENTORY_MOVE",
                    "INVENTORY_ON_DELIVERY_COST",
                    100.0,
                    "STOREB",
                    "SKU_BAL",
                    "SKU_BAL_S",
                    "ORDER",
                    "ORD_BAL",
                    "",
                    "ORDER_MODELLED",
                    "seed",
                    "ord_bal_move",
                ),
                (
                    "2026-02-04",
                    "COGS_RECOGNIZED",
                    "INVENTORY_ON_DELIVERY_COST",
                    -200.0,
                    "STOREB",
                    "SKU_BAL",
                    "SKU_BAL_S",
                    "ORDER",
                    "ORD_BAL",
                    "",
                    "ORDER_MODELLED",
                    "seed",
                    "ord_bal_cogs",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 2, 6), until=date(2026, 2, 8), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        correction_count = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id='ORD_BAL'
              AND account='INVENTORY_ON_DELIVERY_COST'
              AND event_type='COGS_RECOGNIZED'
              AND notes LIKE '%balance correction%'
            """
        ).fetchone()[0]
        net = conn.execute(
            """
            SELECT COALESCE(SUM(amount_kzt), 0.0)
            FROM fact_cashflow_events
            WHERE ref_id='ORD_BAL' AND account='INVENTORY_ON_DELIVERY_COST'
            """
        ).fetchone()[0]
        assert correction_count == 1
        assert round(net, 6) == 0.0
    finally:
        conn.close()


def test_translate_orders_allows_missing_sku_when_order_already_recorded(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_DONE",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-01-20",
                    "CASH_IN",
                    "KASPI_PAY_UNIVERSAL",
                    1000.0,
                    "UNIVERSAL",
                    "SKU_DONE",
                    "SKU_DONE_S",
                    "ORDER",
                    "ORD_DONE",
                    "",
                    "ORDER_MODELLED",
                    "seed",
                    "done_cash",
                ),
                (
                    "2026-01-20",
                    "COGS_RECOGNIZED",
                    "INVENTORY_ON_DELIVERY_COST",
                    -500.0,
                    "UNIVERSAL",
                    "SKU_DONE",
                    "SKU_DONE_S",
                    "ORDER",
                    "ORD_DONE",
                    "",
                    "ORDER_MODELLED",
                    "seed",
                    "done_cogs",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")


def test_translate_orders_ignores_missing_sku_when_resolved_in_other_store(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_XSTORE", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_XSTORE",
                "UNKNOWN",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                "SKU_XSTORE",
                "SKU_XSTORE_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_XSTORE",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")


def test_translate_orders_backfills_zero_cost_events(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_BACKFILL", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_BACKFILL",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("E2", "ORD_BACKFILL", "UNIVERSAL", "OFFER2", 1, 12000, 12000, None),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, sku_key, sku_id
            ) VALUES (?, ?, ?, ?)
            """,
            ("UNIVERSAL", "OFFER2", "SKU_BACKFILL", "SKU_BACKFILL_S"),
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-01-20", "COGS_RECOGNIZED", "INVENTORY_ON_DELIVERY_COST", 0.0,
                 "UNIVERSAL", "SKU_BACKFILL", "SKU_BACKFILL_S", "ORDER", "ORD_BACKFILL",
                 "seed zero", "ORDER_MODELLED", "seed", "hash1"),
                ("2026-01-20", "INVENTORY_MOVE", "INVENTORY_ON_HAND_COST", 0.0,
                 "UNIVERSAL", "SKU_BACKFILL", "SKU_BACKFILL_S", "ORDER", "ORD_BACKFILL",
                 "seed zero", "ORDER_MODELLED", "seed", "hash2"),
                ("2026-01-20", "INVENTORY_MOVE", "INVENTORY_ON_DELIVERY_COST", 0.0,
                 "UNIVERSAL", "SKU_BACKFILL", "SKU_BACKFILL_S", "ORDER", "ORD_BACKFILL",
                 "seed zero", "ORDER_MODELLED", "seed", "hash3"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        nonzero = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id='ORD_BACKFILL' AND amount_kzt != 0
              AND event_type IN ('COGS_RECOGNIZED', 'INVENTORY_MOVE')
            """
        ).fetchone()[0]
        assert nonzero == 3
    finally:
        conn.close()


def test_translate_orders_backfills_cogs_when_cash_exists_with_zero_inventory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_CASH_BACKFILL", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_CASH_BACKFILL",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                "SKU_CASH_BACKFILL",
                "SKU_CASH_BACKFILL_S",
            ),
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-01-20",
                    "CASH_IN",
                    "KASPI_PAY_UNIVERSAL",
                    10000.0,
                    "UNIVERSAL",
                    "SKU_CASH_BACKFILL",
                    "",
                    "ORDER",
                    "ORD_CASH_BACKFILL",
                    "seed cash",
                    "ORDER_MODELLED",
                    "seed",
                    "cash_hash",
                ),
                (
                    "2026-01-20",
                    "COGS_RECOGNIZED",
                    "INVENTORY_ON_DELIVERY_COST",
                    0.0,
                    "UNIVERSAL",
                    "SKU_CASH_BACKFILL",
                    "",
                    "ORDER",
                    "ORD_CASH_BACKFILL",
                    "seed zero",
                    "ORDER_MODELLED",
                    "seed",
                    "zero_cogs_hash",
                ),
                (
                    "2026-01-20",
                    "INVENTORY_MOVE",
                    "INVENTORY_ON_HAND_COST",
                    0.0,
                    "UNIVERSAL",
                    "SKU_CASH_BACKFILL",
                    "",
                    "ORDER",
                    "ORD_CASH_BACKFILL",
                    "seed zero",
                    "ORDER_MODELLED",
                    "seed",
                    "zero_move_h_hash",
                ),
                (
                    "2026-01-20",
                    "INVENTORY_MOVE",
                    "INVENTORY_ON_DELIVERY_COST",
                    0.0,
                    "UNIVERSAL",
                    "SKU_CASH_BACKFILL",
                    "",
                    "ORDER",
                    "ORD_CASH_BACKFILL",
                    "seed zero",
                    "ORDER_MODELLED",
                    "seed",
                    "zero_move_d_hash",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        nonzero_cogs = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id='ORD_CASH_BACKFILL'
              AND event_type='COGS_RECOGNIZED'
              AND amount_kzt != 0
            """
        ).fetchone()[0]
        nonzero_moves = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id='ORD_CASH_BACKFILL'
              AND event_type='INVENTORY_MOVE'
              AND amount_kzt != 0
            """
        ).fetchone()[0]
        assert nonzero_cogs >= 1
        assert nonzero_moves >= 2
    finally:
        conn.close()


def test_translate_orders_resolves_normalized_offer_id(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_NORM", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_NORM",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "E3",
                "ORD_NORM",
                "UNIVERSAL",
                "102529963\tCL_OC_MEN_LINE52_BLACK_2XL_102529963",
                1,
                12000,
                12000,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, sku_key, sku_id
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "UNIVERSAL",
                "CL_OC_MEN_LINE52_BLACK_2XL_102529963",
                "SKU_NORM",
                "SKU_NORM_2XL",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")


def test_translate_orders_resolves_by_offer_name_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_NAME", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_NAME",
                "ACMEWEAR",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "E4",
                "ORD_NAME",
                "ACMEWEAR",
                "108381956_888082755",
                1,
                12000,
                12000,
                '{"attributes":{"offer":{"name":"Комплект Podium RASH-32 комплект 5в1 черный 44"}}}',
            ),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "ACMEWEAR",
                "CL_OC_MEN_LINE52_BLACK_M_105133583",
                "Комплект Podium RASH-32 комплект 5в1 черный 44",
                "SKU_NAME",
                "SKU_NAME_M",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")


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
        assert count == 4  # cash in + cogs + on-hand move + on-delivery move
    finally:
        conn.close()


def test_translate_orders_skips_duplicate_completed_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_DUP", 0.95, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_DUP",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-20",
                2,
                12000,
                "SKU_DUP",
                "SKU_DUP_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_DUP",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-21",
                2,
                12000,
                "SKU_DUP",
                "SKU_DUP_S",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 22), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id = 'ORD_DUP'"
        ).fetchone()[0]
        assert count == 4  # cash in + cogs + on-hand move + on-delivery move
    finally:
        conn.close()


def test_translate_orders_shifts_on_delivery_timing(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_SHIFT", 0.95, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHIFT",
                "UNIVERSAL",
                "Завершен",
                "COMPLETED",
                "2026-01-22",
                1,
                12000,
                "SKU_SHIFT",
                "SKU_SHIFT_S",
            ),
        )
        conn.executemany(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "2026-01-20",
                    "CASH_IN",
                    "KASPI_PAY_UNIVERSAL",
                    1000,
                    "UNIVERSAL",
                    "SKU_SHIFT",
                    "SKU_SHIFT_S",
                    "ORDER",
                    "ORD_SHIFT",
                    "",
                    "ORDER_MODELLED",
                    "run1",
                    "h1",
                ),
                (
                    "2026-01-20",
                    "COGS_RECOGNIZED",
                    "INVENTORY_ON_DELIVERY_COST",
                    -500,
                    "UNIVERSAL",
                    "SKU_SHIFT",
                    "SKU_SHIFT_S",
                    "ORDER",
                    "ORD_SHIFT",
                    "",
                    "ORDER_MODELLED",
                    "run1",
                    "h2",
                ),
                (
                    "2026-01-22",
                    "INVENTORY_MOVE",
                    "INVENTORY_ON_DELIVERY_COST",
                    500,
                    "UNIVERSAL",
                    "SKU_SHIFT",
                    "SKU_SHIFT_S",
                    "ORDER",
                    "ORD_SHIFT",
                    "",
                    "ORDER_MODELLED",
                    "run1",
                    "h3",
                ),
                (
                    "2026-01-22",
                    "INVENTORY_MOVE",
                    "INVENTORY_ON_HAND_COST",
                    -500,
                    "UNIVERSAL",
                    "SKU_SHIFT",
                    "SKU_SHIFT_S",
                    "ORDER",
                    "ORD_SHIFT",
                    "",
                    "ORDER_MODELLED",
                    "run1",
                    "h4",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 23), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT COUNT(*) FROM fact_cashflow_events
            WHERE ref_id = 'ORD_SHIFT'
              AND notes LIKE 'Timing shift%'
            """
        ).fetchone()[0]
        assert rows == 4
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


def test_translate_orders_on_delivery_moves_inventory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU3", 0.95, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD3",
                "UNIVERSAL",
                "Передан курьеру",
                "SHIPPED",
                "2026-01-20",
                1,
                12000,
                "SKU3",
                "SKU3_S",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        events = conn.execute(
            """
            SELECT event_type, account, amount_kzt
            FROM fact_cashflow_events
            WHERE ref_id = 'ORD3'
            """
        ).fetchall()
    finally:
        conn.close()

    event_types = {row[0] for row in events}
    accounts = {row[1] for row in events}
    assert "CASH_IN" not in event_types
    assert event_types == {"INVENTORY_MOVE"}
    assert "INVENTORY_ON_HAND_COST" in accounts
    assert "INVENTORY_ON_DELIVERY_COST" in accounts


def test_translate_orders_ignores_kaspi_delivery_state_even_if_shipped(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU4", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                actual_shipment_date, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD4",
                "UNIVERSAL",
                "KASPI_DELIVERY",
                "SHIPPED",
                "2026-01-20",
                "2026-01-20",
                1,
                12000,
                "SKU4",
                "SKU4_S",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD4'").fetchone()[0]
        assert count == 0
    finally:
        conn.close()
