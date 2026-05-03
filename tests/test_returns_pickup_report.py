from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import returns_pickup_report as mod


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            quantity INTEGER,
            kaspi_status_detail TEXT,
            returned_to_warehouse INTEGER,
            status_updated_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            delivery_mode TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_order(
    db_path: Path,
    *,
    order_id: str,
    store_code: str,
    returned_to_warehouse: int,
    status: str,
    status_updated_at: str,
    quantity: int = 1,
    duplicate_rows: int = 1,
) -> None:
    conn = sqlite3.connect(db_path)
    for idx in range(duplicate_rows):
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, quantity, kaspi_status_detail, returned_to_warehouse,
                status_updated_at, planned_shipment_date, actual_shipment_date, delivery_mode
            ) VALUES (?, ?, ?, ?, ?, ?, '2026-04-28', '2026-04-27 18:00:00', 'DELIVERY_PICKUP')
            """,
            (
                order_id,
                store_code,
                quantity,
                status,
                returned_to_warehouse,
                status_updated_at,
            ),
        )
    conn.commit()
    conn.close()


def test_build_pickup_ready_snapshot_dedupes_orders_and_formats_store_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    ack_path = tmp_path / "acks.json"
    _init_db(db_path)
    _insert_order(
        db_path,
        order_id="1001",
        store_code="ACMEWEAR",
        returned_to_warehouse=1,
        status="CANCELLED",
        status_updated_at="2026-04-26 10:00:00",
        duplicate_rows=2,
    )
    _insert_order(
        db_path,
        order_id="1002",
        store_code="ACMEWEAR",
        returned_to_warehouse=1,
        status="CANCELLING",
        status_updated_at="2026-04-27 11:00:00",
    )
    _insert_order(
        db_path,
        order_id="2001",
        store_code="UNIVERSAL",
        returned_to_warehouse=1,
        status="CANCELLED",
        status_updated_at="2026-04-25 09:30:00",
    )
    _insert_order(
        db_path,
        order_id="9999",
        store_code="UNIVERSAL",
        returned_to_warehouse=0,
        status="CANCELLED",
        status_updated_at="2026-04-28 12:00:00",
    )

    snapshot = mod.build_pickup_ready_snapshot(
        db_path=db_path,
        ack_path=ack_path,
        as_of=datetime(2026, 4, 28, 14, 0, tzinfo=ALMATY_TZ),
    )

    assert snapshot["total_orders"] == 3
    assert snapshot["hidden_acked_orders"] == 0
    assert [row["order_id"] for row in snapshot["orders"]] == ["1001", "1002", "2001"]

    acmewear = next(row for row in snapshot["stores"] if row["store_code"] == "ACMEWEAR")
    universal = next(row for row in snapshot["stores"] if row["store_code"] == "UNIVERSAL")

    assert acmewear["orders"] == 2
    assert acmewear["first_order_id"] == "1001"
    assert acmewear["oldest_day"] == "2026-04-26"
    assert acmewear["newest_day"] == "2026-04-27"
    assert universal["orders"] == 1
    assert universal["first_order_id"] == "2001"

    message = mod.format_returns_pickup_message(snapshot)
    assert "Returns Pickup Ready" in message
    assert "FIRST_ORDER_ID" in message
    assert "AcmeWear" in message
    assert "1001" in message
    assert "Universal" in message


def test_ack_store_hides_orders_and_unack_restores_them(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    ack_path = tmp_path / "acks.json"
    _init_db(db_path)
    _insert_order(
        db_path,
        order_id="3001",
        store_code="ACMEWEAR",
        returned_to_warehouse=1,
        status="CANCELLED",
        status_updated_at="2026-04-26 10:00:00",
    )
    _insert_order(
        db_path,
        order_id="3002",
        store_code="ACMEWEAR",
        returned_to_warehouse=1,
        status="CANCELLED",
        status_updated_at="2026-04-27 10:00:00",
    )
    _insert_order(
        db_path,
        order_id="4001",
        store_code="STOREB",
        returned_to_warehouse=1,
        status="CANCELLED",
        status_updated_at="2026-04-27 10:30:00",
    )

    ack_result = mod.ack_current_pickup_orders_for_stores(
        store_codes=["ACMEWEAR"],
        db_path=db_path,
        ack_path=ack_path,
        acked_by="42",
        as_of=datetime(2026, 4, 28, 15, 0, tzinfo=ALMATY_TZ),
    )

    assert ack_result["acked_orders"] == 2
    assert ack_result["stores"] == [{"store_code": "ACMEWEAR", "display_name": "AcmeWear", "acked_orders": 2}]

    snapshot = mod.build_pickup_ready_snapshot(
        db_path=db_path,
        ack_path=ack_path,
        as_of=datetime(2026, 4, 28, 15, 1, tzinfo=ALMATY_TZ),
    )
    assert snapshot["total_orders"] == 1
    assert snapshot["hidden_acked_orders"] == 2
    assert [row["order_id"] for row in snapshot["orders"]] == ["4001"]

    restore = mod.unack_pickup_orders(order_ids=["3001"], ack_path=ack_path)
    assert restore["restored_orders"] == 1

    snapshot = mod.build_pickup_ready_snapshot(
        db_path=db_path,
        ack_path=ack_path,
        as_of=datetime(2026, 4, 28, 15, 2, tzinfo=ALMATY_TZ),
    )
    assert {row["order_id"] for row in snapshot["orders"]} == {"3001", "4001"}
