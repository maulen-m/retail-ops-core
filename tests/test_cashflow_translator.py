import hashlib
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.translate_orders_to_cashflow_events as cashflow_translator
from scripts.translate_orders_to_cashflow_events import _unit_cost_kzt_for_sku, translate_orders


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                kaspi_status_detail TEXT,
                internal_status TEXT,
                status_updated_at TEXT,
                actual_shipment_date TEXT,
                planned_shipment_date TEXT,
                created_at TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                sku_key TEXT,
                sku_id TEXT,
                delivery_mode TEXT,
                signature_required INTEGER,
                pre_order INTEGER,
                waybill_url TEXT,
                returned_to_warehouse INTEGER,
                courier_transmission_date TEXT
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
            CREATE TABLE order_status_event (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT,
                order_id TEXT,
                stage_code TEXT,
                event_ts TEXT,
                source TEXT,
                idempotency_key TEXT
            );
            """
        )
    finally:
        conn.close()


def test_production_cashflow_apply_requires_dedicated_prod_env(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    monkeypatch.setattr(cashflow_translator, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.delenv("ENABLE_CASHFLOW_PROD_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_CASHFLOW_PROD_WRITE=1"):
        translate_orders(
            db_path,
            since=date(2026, 1, 1),
            until=date(2026, 1, 1),
            apply=True,
            run_id="blocked-prod",
            expected_pre_sha256=_sha256(db_path),
            backup_dir=tmp_path / "backups",
        )


def test_production_cashflow_apply_requires_expected_sha_and_backup_dir(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    monkeypatch.setattr(cashflow_translator, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.setenv("ENABLE_CASHFLOW_PROD_WRITE", "1")

    with pytest.raises(RuntimeError, match="--expected-pre-sha256"):
        translate_orders(
            db_path,
            since=date(2026, 1, 1),
            until=date(2026, 1, 1),
            apply=True,
            run_id="missing-sha",
            backup_dir=tmp_path / "backups",
        )

    with pytest.raises(RuntimeError, match="--backup-dir"):
        translate_orders(
            db_path,
            since=date(2026, 1, 1),
            until=date(2026, 1, 1),
            apply=True,
            run_id="missing-backup",
            expected_pre_sha256=_sha256(db_path),
        )


def test_production_cashflow_apply_creates_verified_backup_and_report(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    backup_dir = tmp_path / "backups"
    report_path = tmp_path / "cashflow_report.txt"
    monkeypatch.setattr(cashflow_translator, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.setenv("ENABLE_CASHFLOW_PROD_WRITE", "1")

    translate_orders(
        db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 1),
        apply=True,
        run_id="prod-ok",
        output_path=report_path,
        expected_pre_sha256=_sha256(db_path),
        backup_dir=backup_dir,
    )

    backups = list(backup_dir.glob("app_*.db"))
    assert len(backups) == 1
    report = report_path.read_text(encoding="utf-8")
    assert "Apply production target: True" in report
    assert f"Production backup path: {backups[0]}" in report


def test_translate_orders_uses_stagecode_over_stale_internal_completed(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_STAGE", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_STALE_COMPLETED",
                "UNIVERSAL",
                "KASPI_DELIVERY",
                "ACCEPTED_BY_MERCHANT",
                "COMPLETED",
                "2026-01-20",
                1,
                12000,
                "SKU_STAGE",
                "SKU_STAGE_M",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        cash_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='CASH_IN'"
        ).fetchone()[0]
        assert cash_count == 0
    finally:
        conn.close()


def test_translate_orders_completed_stagecode_overrides_stale_shipped_internal(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_DONE", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_STAGE_DONE",
                "ACMEWEAR",
                "ARCHIVE",
                "COMPLETED",
                "SHIPPED",
                "2026-01-20",
                1,
                12000,
                "SKU_DONE",
                "SKU_DONE_M",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        cash_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='CASH_IN' AND amount_kzt > 0"
        ).fetchone()[0]
        assert cash_count == 1
    finally:
        conn.close()


def test_translate_orders_creates_entry_backed_cash_in_without_synthetic_sku(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_ENTRY_CASH",
                "STOREB",
                "ARCHIVE",
                "COMPLETED",
                "COMPLETED",
                "2026-01-20",
                1,
                15000,
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
            ("E_ENTRY_CASH", "ORD_ENTRY_CASH", "STOREB", "UNMAPPED-OFFER", 1, 15000, 15000, None),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT ref_type, ref_id, sku_key, sku_id, event_type, amount_kzt
            FROM fact_cashflow_events
            WHERE event_type='CASH_IN'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "ORDER_ENTRY"
        assert row[1] == "E_ENTRY_CASH"
        assert row[2] in (None, "")
        assert row[3] in (None, "")
        assert row[5] > 0
    finally:
        conn.close()


def test_translate_orders_uses_order_header_amount_when_line_identity_is_missing(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_HEADER_CASH",
                "ACMEWEAR",
                "ARCHIVE",
                "COMPLETED",
                "COMPLETED",
                "2026-01-20",
                1,
                15990,
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ACMEWEAR",
                "ORD_HEADER_CASH",
                "COMPLETED",
                "2026-01-20T10:00:00+05:00",
                "fixture",
                "ose-header-cash",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 19), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT ref_type, ref_id, sku_key, sku_id, event_type, amount_kzt
            FROM fact_cashflow_events
            WHERE event_type='CASH_IN'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == "ORDER"
        assert row[1] == "ORD_HEADER_CASH"
        assert row[2] in (None, "")
        assert row[3] in (None, "")
        assert row[5] > 0
    finally:
        conn.close()


def test_translate_orders_returned_stage_reverses_existing_cash(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_RETURN_STAGE", 1.0, 5000, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_RETURN_STAGE",
                "UNIVERSAL",
                "ARCHIVE",
                "RETURNED",
                "COMPLETED",
                "2026-01-21",
                1,
                12000,
                "SKU_RETURN_STAGE",
                "SKU_RETURN_STAGE_M",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                ref_type, ref_id, notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-20",
                "CASH_IN",
                "KASPI_PAY_UNIVERSAL",
                1000.0,
                "UNIVERSAL",
                "SKU_RETURN_STAGE",
                "SKU_RETURN_STAGE_M",
                "ORDER",
                "ORD_RETURN_STAGE",
                "",
                "ORDER_MODELLED",
                "seed",
                "cash-seed-return-stage",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 1, 21), until=date(2026, 1, 21), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        refund_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_cashflow_events
            WHERE event_type='CASH_IN'
              AND amount_kzt < 0
              AND ref_id='ORD_RETURN_STAGE'
            """
        ).fetchone()[0]
        assert refund_count == 1
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


def test_unit_cost_prefers_formula_landed_cogs_over_stored_legacy():
    fx = SimpleNamespace(cny_kzt=73.0, usd_kzt=514.0, dlv_rate_usd_kg=2.66)
    dim_costs = {
        "SKU_FORMULA": {
            "cogs_kzt": 3666.0,
            "base_cost_cny": 47.0,
            "weight_kg": 0.95,
        }
    }

    actual = _unit_cost_kzt_for_sku("SKU_FORMULA", fx, dim_costs)
    expected = 47.0 * 73.0 + 0.95 * 2.66 * 514.0

    assert actual == expected
    assert actual > dim_costs["SKU_FORMULA"]["cogs_kzt"]


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


def test_translate_orders_allow_missing_continues_for_resolved_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_OK", 0.2, 500.0, 0.0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_OK",
                "UNIVERSAL",
                "KASPI_DELIVERY",
                "SHIPPED",
                "2026-01-20",
                1,
                12000,
                "SKU_OK",
                "SKU_OK_M",
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
                "ORD_MISS",
                "UNIVERSAL",
                "KASPI_DELIVERY",
                "SHIPPED",
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
    translate_orders(
        db_path,
        since=date(2026, 1, 19),
        until=date(2026, 1, 21),
        apply=True,
        run_id="test",
        allow_missing=True,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT ref_id, event_type FROM fact_cashflow_events ORDER BY ref_id, event_type"
        ).fetchall()
        assert ("ORD_OK", "INVENTORY_MOVE") in rows
        assert all(ref_id != "ORD_MISS" for ref_id, _ in rows)
    finally:
        conn.close()


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


def test_translate_orders_does_not_duplicate_order_cash_for_blank_recovered_entries(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source, idempotency_key
            ) VALUES ('UNIVERSAL', 'ORD_RECOV', 'COMPLETED',
                      '2026-04-20T10:00:00+05:00', 'fixture', 'ose-ord-recov')
            """
        )
        conn.executemany(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity,
                unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, 'ORD_RECOV', 'UNIVERSAL', ?, 1, 1500, 1500, NULL)
            """,
            [
                ("RECOV-CURRENT_CRM-a", "OFFER-A"),
                ("RECOV-CURRENT_CRM-b", "OFFER-B"),
            ],
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                ref_type, ref_id, source, event_hash
            ) VALUES ('2026-04-20', 'CASH_IN', 'KASPI_PAY_UNIVERSAL', 3000,
                      'UNIVERSAL', NULL, NULL, 'ORDER', 'ORD_RECOV',
                      'ORDER_MODELLED', 'cash-ord-recov')
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(
        db_path,
        since=date(2026, 4, 20),
        until=date(2026, 4, 20),
        apply=True,
        run_id="test-recov",
        allow_missing=True,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        cash_rows = conn.execute(
            """
            SELECT ref_type, ref_id, sku_key, sku_id
            FROM fact_cashflow_events
            WHERE event_type='CASH_IN' AND amount_kzt > 0
            ORDER BY ref_type, ref_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert cash_rows == [("ORDER", "ORD_RECOV", None, None)]


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


def test_translate_orders_creates_on_delivery_for_shipped_kaspi_delivery(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_SHIP", 1.0, 1234.0, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_SHIP",
                "STOREB",
                "KASPI_DELIVERY",
                "SHIPPED",
                "2026-02-08",
                1,
                10000,
                "SKU_SHIP",
                "SKU_SHIP_S",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 2, 8), until=date(2026, 2, 8), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        move = conn.execute(
            """
            SELECT COALESCE(SUM(amount_kzt), 0.0)
            FROM fact_cashflow_events
            WHERE ref_id='ORD_SHIP'
              AND event_type='INVENTORY_MOVE'
              AND account='INVENTORY_ON_DELIVERY_COST'
            """
        ).fetchone()[0]
        assert move > 0
    finally:
        conn.close()


def test_translate_orders_order_id_allowlist_excludes_non_allowlisted_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            [
                ("SKU_ALLOWED", 1.0, 100.0, 0),
                ("SKU_BLOCKED", 1.0, 200.0, 0),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, actual_shipment_date, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "ORD_ALLOWED",
                    "STOREB",
                    "KASPI_DELIVERY",
                    "ACCEPTED_BY_MERCHANT",
                    "SHIPPED",
                    "2026-02-08",
                    "2026-02-08",
                    1,
                    10000,
                    "SKU_ALLOWED",
                    "SKU_ALLOWED_S",
                ),
                (
                    "ORD_BLOCKED",
                    "STOREB",
                    "KASPI_DELIVERY",
                    "ACCEPTED_BY_MERCHANT",
                    "SHIPPED",
                    "2026-02-08",
                    "2026-02-08",
                    1,
                    10000,
                    "SKU_BLOCKED",
                    "SKU_BLOCKED_S",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(
        db_path,
        since=date(2026, 2, 8),
        until=date(2026, 2, 8),
        apply=True,
        run_id="test",
        order_id_allowlist={"ORD_ALLOWED"},
    )

    conn = sqlite3.connect(str(db_path))
    try:
        allowed_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_ALLOWED'"
        ).fetchone()[0]
        blocked_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_BLOCKED'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert allowed_count == 2
    assert blocked_count == 0


def test_translate_orders_order_id_allowlist_filters_stagecode_d1_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            [
                ("SKU_STAGE_ALLOWED", 1.0, 100.0, 0),
                ("SKU_STAGE_BLOCKED", 1.0, 100.0, 0),
            ],
        )
        conn.executemany(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source, idempotency_key
            ) VALUES (?, ?, 'COMPLETED', '2026-02-08T10:00:00+05:00', 'fixture', ?)
            """,
            [
                ("STOREB", "ORD_STAGE_ALLOWED", "ose-stage-allowed"),
                ("STOREB", "ORD_STAGE_BLOCKED", "ose-stage-blocked"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity,
                unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (?, ?, 'STOREB', ?, 1, 10000, 10000, ?)
            """,
            [
                (
                    "ENTRY_STAGE_ALLOWED",
                    "ORD_STAGE_ALLOWED",
                    "OFFER_ALLOWED",
                    '{"attributes":{"sku_key":"SKU_STAGE_ALLOWED","sku_id":"SKU_STAGE_ALLOWED_S"}}',
                ),
                (
                    "ENTRY_STAGE_BLOCKED",
                    "ORD_STAGE_BLOCKED",
                    "OFFER_BLOCKED",
                    '{"attributes":{"sku_key":"SKU_STAGE_BLOCKED","sku_id":"SKU_STAGE_BLOCKED_S"}}',
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(
        db_path,
        since=date(2026, 2, 8),
        until=date(2026, 2, 8),
        apply=True,
        run_id="test",
        order_id_allowlist={"ORD_STAGE_ALLOWED"},
    )

    conn = sqlite3.connect(str(db_path))
    try:
        allowed_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ENTRY_STAGE_ALLOWED'"
        ).fetchone()[0]
        blocked_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ENTRY_STAGE_BLOCKED'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert allowed_count == 1
    assert blocked_count == 0


def test_translate_orders_only_on_delivery_excludes_completed_rows_same_window(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            [
                ("SKU_SHIPPED_ONLY", 1.0, 100.0, 0),
                ("SKU_DONE_ONLY", 1.0, 200.0, 0),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, actual_shipment_date, quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "ORD_SHIPPED_ONLY",
                    "STOREB",
                    "KASPI_DELIVERY",
                    "ACCEPTED_BY_MERCHANT",
                    "SHIPPED",
                    "2026-02-08",
                    "2026-02-08",
                    1,
                    10000,
                    "SKU_SHIPPED_ONLY",
                    "SKU_SHIPPED_ONLY_S",
                ),
                (
                    "ORD_DONE_ONLY",
                    "STOREB",
                    "ARCHIVE",
                    "COMPLETED",
                    "COMPLETED",
                    "2026-02-08",
                    "2026-02-08",
                    1,
                    10000,
                    "SKU_DONE_ONLY",
                    "SKU_DONE_ONLY_S",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(
        db_path,
        since=date(2026, 2, 8),
        until=date(2026, 2, 8),
        apply=True,
        run_id="test",
        only_cashflow_status="ON_DELIVERY",
    )

    conn = sqlite3.connect(str(db_path))
    try:
        shipped_events = conn.execute(
            """
            SELECT event_type, account
            FROM fact_cashflow_events
            WHERE ref_id='ORD_SHIPPED_ONLY'
            """
        ).fetchall()
        completed_count = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='ORD_DONE_ONLY'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert len(shipped_events) == 2
    assert {row[0] for row in shipped_events} == {"INVENTORY_MOVE"}
    assert {row[1] for row in shipped_events} == {
        "INVENTORY_ON_HAND_COST",
        "INVENTORY_ON_DELIVERY_COST",
    }
    assert completed_count == 0


def test_translate_orders_rejects_empty_order_id_allowlist(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    with pytest.raises(RuntimeError, match="order_id_allowlist must not be empty"):
        translate_orders(
            db_path,
            since=date(2026, 2, 8),
            until=date(2026, 2, 8),
            apply=False,
            run_id="test",
            order_id_allowlist=set(),
        )


def test_translate_orders_settles_returned_on_delivery_balance_without_cash(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key, weight_kg, cogs_kzt, base_cost_cny) VALUES (?, ?, ?, ?)",
            ("SKU_RET", 1.0, 250.0, 0),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, internal_status, status_updated_at,
                quantity, unit_price_kzt, sku_key, sku_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ORD_RET",
                "STOREB",
                "RETURNED",
                "RETURNED",
                "2026-02-08",
                1,
                10000,
                "SKU_RET",
                "SKU_RET_S",
            ),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt,
                store_code, sku_key, sku_id, ref_type, ref_id,
                notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-07",
                "INVENTORY_MOVE",
                "INVENTORY_ON_DELIVERY_COST",
                250.0,
                "STOREB",
                "SKU_RET",
                "SKU_RET_S",
                "ORDER",
                "ORD_RET",
                "",
                "ORDER_MODELLED",
                "seed",
                "ord_ret_seed_move",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    translate_orders(db_path, since=date(2026, 2, 8), until=date(2026, 2, 8), apply=True, run_id="test")

    conn = sqlite3.connect(str(db_path))
    try:
        on_delivery_net = conn.execute(
            """
            SELECT COALESCE(SUM(amount_kzt), 0.0)
            FROM fact_cashflow_events
            WHERE ref_id='ORD_RET'
              AND account='INVENTORY_ON_DELIVERY_COST'
            """
        ).fetchone()[0]
        assert round(float(on_delivery_net), 6) == 0.0
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


def test_translate_orders_creates_on_delivery_for_kaspi_delivery_state_when_shipped(tmp_path, monkeypatch):
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
        rows = conn.execute(
            """
            SELECT event_type, account
            FROM fact_cashflow_events
            WHERE ref_id='ORD4'
            """
        ).fetchall()
        assert len(rows) == 2
        assert {row[0] for row in rows} == {"INVENTORY_MOVE"}
        assert {row[1] for row in rows} == {"INVENTORY_ON_HAND_COST", "INVENTORY_ON_DELIVERY_COST"}
    finally:
        conn.close()
