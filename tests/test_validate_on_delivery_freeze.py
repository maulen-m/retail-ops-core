import sqlite3
from datetime import date
from pathlib import Path

from scripts.validate_on_delivery_freeze import validate_on_delivery_freeze


def _seed_schema(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT
        );
        CREATE TABLE fact_cashflow_events (
            event_date TEXT,
            account TEXT,
            amount_kzt REAL,
            ref_type TEXT,
            ref_id TEXT,
            sku_id TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_shipped_api_lines_have_on_delivery_inventory_move(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_schema(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at)
        VALUES ('ORD-1', 'ACMEWEAR', 'SHIPPED', '2026-02-08')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (event_date, account, amount_kzt, ref_type, ref_id, sku_id)
        VALUES ('2026-02-08', 'INVENTORY_ON_DELIVERY_COST', 12000.0, 'ORDER', 'ORD-1', 'SKU-1')
        """
    )
    conn.commit()
    conn.close()

    errors = validate_on_delivery_freeze(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 2, 8),
    )
    assert errors == []


def test_completed_lines_settle_on_delivery_balance_to_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_schema(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status, status_updated_at)
        VALUES ('ORD-2', 'ACMEWEAR', 'COMPLETED', '2026-02-08')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events (event_date, account, amount_kzt, ref_type, ref_id, sku_id)
        VALUES ('2026-02-08', 'INVENTORY_ON_DELIVERY_COST', 8000.0, 'ORDER', 'ORD-2', 'SKU-2')
        """
    )
    conn.commit()
    conn.close()

    errors = validate_on_delivery_freeze(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 2, 8),
    )
    assert any("ORD-2" in err for err in errors)
