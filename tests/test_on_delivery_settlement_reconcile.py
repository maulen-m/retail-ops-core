import sqlite3
from pathlib import Path

from scripts.reconcile_on_delivery_settlement import (
    find_settlement_gaps,
    reconcile_on_delivery_settlement,
)


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            sku_key TEXT,
            sku_id TEXT
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            event_hash TEXT UNIQUE
        );
        """
    )
    conn.commit()
    conn.close()


def _seed_gap(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-1', 'ACMEWEAR', 'COMPLETED', '2026-02-08', 'SKU_A', 'SKU_A_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-02-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 1500, 'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'ORD-1', 'ORDER_MODELLED', 'h1')
        """
    )
    conn.commit()
    conn.close()


def test_detects_completed_orders_with_nonzero_on_delivery_balance(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)

    gaps = find_settlement_gaps(db_path=db_path, since="2026-02-01", until="2026-02-08")
    assert len(gaps) == 1
    assert gaps[0]["order_id"] == "ORD-1"
    assert gaps[0]["balance_kzt"] == 1500.0


def test_reconcile_script_generates_settlement_events_idempotently(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    first = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        apply=True,
        run_id="TEST-RUN",
    )
    second = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        apply=True,
        run_id="TEST-RUN",
    )

    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='INVENTORY_SETTLEMENT'"
    ).fetchone()[0]
    balance = conn.execute(
        """
        SELECT SUM(amount_kzt) FROM fact_cashflow_events
        WHERE account='INVENTORY_ON_DELIVERY_COST' AND ref_id='ORD-1'
        """
    ).fetchone()[0]
    conn.close()

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert count == 1
    assert float(balance or 0.0) == 0.0
