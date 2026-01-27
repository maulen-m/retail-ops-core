import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from scripts import build_daily_waybills
from scripts import download_waybills_api
from scripts import validate_pending_orders


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _ts_for(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=ALMATY_TZ)
    return int(dt.timestamp() * 1000)


def _make_order(code: str, status: str, signature: bool, planned: date) -> dict:
    return {
        "id": f"id-{code}",
        "attributes": {
            "code": code,
            "status": status,
            "signatureRequired": signature,
            "kaspiDelivery": {"plannedDeliveryDate": _ts_for(planned)},
        },
    }


def _init_fact_orders_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity INTEGER,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            internal_status TEXT,
            signature_required INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_fact_orders(db_path, rows):
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, quantity,
            assigned_size, my_size, planned_shipment_date, kaspi_status,
            kaspi_status_detail, internal_status, signature_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_get_target_orders_from_api_filters_status_signature_and_date(monkeypatch):
    target_date = date(2026, 1, 27)
    include_order = _make_order(
        "1001", "ACCEPTED_BY_MERCHANT", False, target_date
    )
    include_overdue = _make_order(
        "1002", "ACCEPTED_BY_MERCHANT", False, target_date.replace(day=26)
    )
    excluded_signature = _make_order(
        "1003", "ACCEPTED_BY_MERCHANT", True, target_date
    )
    excluded_status = _make_order("1004", "KASPI_DELIVERY", False, target_date)
    excluded_old = _make_order(
        "1005", "ACCEPTED_BY_MERCHANT", False, target_date.replace(day=20)
    )

    orders = [
        include_order,
        include_overdue,
        excluded_signature,
        excluded_status,
        excluded_old,
    ]

    captured = {}

    class FakeClient:
        def __init__(self, store_code):
            self.store_code = store_code

        def list_all_orders(self, **kwargs):
            captured.update(kwargs)
            return orders

    monkeypatch.setattr(download_waybills_api, "KaspiAPIClient", FakeClient)

    filtered, errored = download_waybills_api.get_target_orders_from_api(
        store_code="UNIVERSAL",
        target_date=target_date,
        since_days=3,
        exact_date=False,
        include_overdue=True,
        verbose=False,
    )

    assert errored is False
    assert captured["status"] == "ACCEPTED_BY_MERCHANT"
    assert captured["signature_required"] is False
    assert {o["attributes"]["code"] for o in filtered} == {"1001", "1002"}


def test_get_target_order_ids_from_db_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("2001", "UNIVERSAL", "Item", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0),
        ("2002", "UNIVERSAL", "Item", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1),
        ("2003", "UNIVERSAL", "Item", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0),
        ("2004", "UNIVERSAL", "Item", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0),
        ("2005", "UNIVERSAL", "Item", "SKU", "SKU-5", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "SHIPPED", 0),
    ]
    _insert_fact_orders(db_path, rows)

    result = download_waybills_api.get_target_order_ids_from_db(
        db_path=db_path,
        target_date=target_date,
        exact_date=True,
    )

    assert result == {"UNIVERSAL": {"2001", "2003"}}


def test_get_target_order_ids_from_crm_filters_status_signature(tmp_path):
    target_date = date(2026, 1, 27)
    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        [
            {
                "OrderID": "3001",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
            },
            {
                "OrderID": "3002",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Передан курьеру",
                "Требуется подписание": "Не требуется",
            },
            {
                "OrderID": "3003",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Требуется",
            },
            {
                "OrderID": "3004",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
            },
        ]
    )
    df.to_excel(crm_path, index=False)

    result = download_waybills_api.get_target_order_ids_from_crm(
        crm_path=crm_path,
        sheet_name="Sheet1",
        target_date=target_date,
        exact_date=True,
    )

    assert result == {"UNIVERSAL": {"3001"}}


def test_build_daily_waybills_read_db_orders_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("4001", "UNIVERSAL", "Item A", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0),
        ("4002", "UNIVERSAL", "Item B", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1),
        ("4003", "UNIVERSAL", "Item C", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0),
        ("4004", "UNIVERSAL", "Item D", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0),
    ]
    _insert_fact_orders(db_path, rows)

    orders = build_daily_waybills.read_db_orders(
        db_path=db_path,
        target_date=target_date,
        lookback_days=None,
    )

    order_ids = {o.order_id for o in orders}
    assert order_ids == {"4001", "4003"}


def test_validate_pending_orders_db_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("5001", "UNIVERSAL", "Item", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0),
        ("5002", "UNIVERSAL", "Item", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0),
        ("5003", "UNIVERSAL", "Item", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0),
        ("5004", "UNIVERSAL", "Item", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "SHIPPED", 0),
        ("5005", "UNIVERSAL", "Item", "SKU", "SKU-5", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1),
    ]
    _insert_fact_orders(db_path, rows)

    total, pending = validate_pending_orders.read_db_pending(
        db_path=db_path,
        target_date=target_date,
        include_overdue=False,
        lookback_days=None,
    )

    assert total == 5
    assert pending == {"5001", "5002"}
