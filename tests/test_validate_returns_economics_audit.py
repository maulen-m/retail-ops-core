from __future__ import annotations

import sqlite3
from datetime import date
import hashlib
from pathlib import Path

import pytest

import scripts.validate_returns_economics_audit as returns_economics
from scripts.validate_returns_economics_audit import (
    ReturnsEconomicsError,
    validate_returns_economics_audit,
)


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            updated_at TEXT,
            created_at TEXT
        );
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT
        );
        CREATE TABLE fact_cashflow_events (
            event_date TEXT,
            event_type TEXT,
            amount_kzt REAL,
            store_code TEXT,
            ref_type TEXT,
            ref_id TEXT,
            source TEXT,
            notes TEXT
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT,
            order_id TEXT,
            store_code TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU', 10, 0.5)")
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at, updated_at, created_at)
        VALUES ('R1', 'UNIVERSAL', 'RETURNED', '2026-03-03', '2026-03-03', '2026-02-20')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (event_date, event_type, amount_kzt, store_code)
        VALUES ('2026-02-10', 'REFUND', -2000, 'UNIVERSAL')
        """
    )
    conn.commit()
    conn.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_validate_returns_economics_pass_within_volatility(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["stale_leaked_orders"] == 0


def test_validate_returns_economics_does_not_mutate_source_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    before = _sha256(db_path)

    validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert _sha256(db_path) == before


def test_validate_returns_economics_prefers_canonical_view_over_raw_projection(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, quantity, net_rev, cogs, profit, status,
            return_flag, sku_key, sku_id, my_size
        ) VALUES ('R1', '2026-02-10', 'UNIVERSAL', 1, 3000, 1000, 2000, 'DELIVERED', 0, 'SKU', 'SKU_1', 'L')
        """
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["stale_leaked_orders"] == 0


def test_validate_returns_economics_fails_canonical_stale_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, quantity, net_rev, cogs, profit, status,
            return_flag, sku_key, sku_id, my_size
        ) VALUES ('R1', '2026-02-10', 'UNIVERSAL', 1, 3000, 1000, 2000, 'DELIVERED', 0, 'SKU', 'SKU_1', 'L')
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT order_id, order_date AS sale_date, store_code
        FROM sales_fact_v2
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(returns_economics, "ensure_sales_truth_views", lambda conn: None)

    with pytest.raises(ReturnsEconomicsError):
        validate_returns_economics_audit(
            db_path=db_path,
            as_of=date(2026, 3, 25),
            since=date(2026, 2, 1),
            output_root=tmp_path / "out",
            volatility_days=14,
            strict=True,
        )


def _make_mature_february_return(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE fact_orders_kaspi
        SET status_updated_at='2026-02-03', updated_at='2026-02-03'
        WHERE order_id='R1'
        """
    )


def test_mature_return_without_recognized_cash_needs_no_refund_event(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["cash_reversal_required_orders"] == 0
    assert report["no_recognized_cash_to_reverse_orders"] == 1
    assert report["missing_cash_reversal_orders"] == 0


def test_latest_duplicate_return_observation_controls_maturity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, updated_at, created_at)
        VALUES ('R1', 'UNIVERSAL', 'RETURNED', '2026-03-20', '2026-03-20', '2026-02-20')
        """
    )
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,amount_kzt,store_code,ref_type,ref_id,source)
        VALUES ('2026-02-02','CASH_IN',2000,'UNIVERSAL','ORDER','R1','ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["mature_returned_orders"] == 0
    assert report["cash_reversal_required_orders"] == 0


def test_unrelated_monthly_refund_does_not_satisfy_exact_return(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,amount_kzt,store_code,ref_type,ref_id,source)
        VALUES ('2026-02-02','CASH_IN',2000,'UNIVERSAL','ORDER','R1','ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["error_code"] == "RETURNS_CASH_REVERSAL_GAP"
    assert report["cash_reversal_required_orders"] == 1
    assert report["missing_cash_reversal_orders"] == 1


def test_matching_order_cash_reversal_satisfies_return(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.executemany(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,amount_kzt,store_code,ref_type,ref_id,source)
        VALUES (?,?,?,?,?,?,?)
        """,
        [
            ("2026-02-02", "CASH_IN", 2000, "UNIVERSAL", "ORDER", "R1", "ORDER_MODELLED"),
            ("2026-02-03", "CASH_IN", -2000, "UNIVERSAL", "ORDER", "R1", "ORDER_MODELLED"),
        ],
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["cash_reversal_required_orders"] == 1
    assert report["cash_reversal_covered_orders"] == 1


def test_matching_order_entry_cash_reversal_satisfies_return(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.execute(
        "INSERT INTO fact_order_entries_kaspi(entry_id,order_id,store_code) VALUES ('E1','R1','UNIVERSAL')"
    )
    conn.executemany(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,amount_kzt,store_code,ref_type,ref_id,source)
        VALUES (?,?,?,?,?,?,?)
        """,
        [
            ("2026-02-02", "CASH_IN", 2000, "UNIVERSAL", "ORDER_ENTRY", "E1", "ORDER_MODELLED"),
            ("2026-02-03", "REFUND", -2000, "UNIVERSAL", "ORDER_ENTRY", "E1", "ORDER_MODELLED"),
        ],
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["cash_reversal_covered_orders"] == 1


def test_order_cash_repair_supersession_is_not_customer_refund(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    _make_mature_february_return(conn)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.executemany(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,amount_kzt,store_code,ref_type,ref_id,source,notes)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        [
            ("2026-02-02", "CASH_IN", 2000, "UNIVERSAL", "ORDER", "R1", "ORDER_MODELLED", ""),
            (
                "2026-02-02",
                "CASH_IN",
                -2000,
                "UNIVERSAL",
                "ORDER",
                "R1",
                "ORDER_CASH_REPAIR",
                "supersedes_cash_id=1",
            ),
        ],
    )
    conn.commit()
    conn.close()

    report = validate_returns_economics_audit(
        db_path=db_path,
        as_of=date(2026, 3, 25),
        since=date(2026, 2, 1),
        output_root=tmp_path / "out",
        volatility_days=14,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["error_code"] == "RETURNS_CASH_REVERSAL_GAP"
    assert report["cash_reversal_covered_orders"] == 0
