import sqlite3
import json
import zipfile
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from core.integrations.kaspi_api_client import APIResponse
from scripts import build_daily_waybills
from scripts import download_waybills_api
from scripts import validate_pending_orders


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _ts_for(d: date) -> int:
    dt = datetime(d.year, d.month, d.day, 12, 0, tzinfo=ALMATY_TZ)
    return int(dt.timestamp() * 1000)


def _make_order(
    code: str,
    status: str,
    signature: bool,
    planned: date,
    *,
    assembled: bool = False,
    courier_transmission_date: Optional[int] = None,
) -> dict:
    delivery = {"plannedDeliveryDate": _ts_for(planned)}
    if courier_transmission_date is not None:
        delivery["courierTransmissionDate"] = courier_transmission_date
    return {
        "id": f"id-{code}",
        "attributes": {
            "state": "KASPI_DELIVERY",
            "code": code,
            "status": status,
            "signatureRequired": signature,
            "assembled": assembled,
            "kaspiDelivery": delivery,
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
            signature_required INTEGER,
            courier_transmission_date TEXT
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
            kaspi_status_detail, internal_status, signature_required,
            courier_transmission_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    include_assembled = _make_order(
        "1002",
        "ACCEPTED_BY_MERCHANT",
        False,
        target_date,
        assembled=True,
    )
    include_overdue = _make_order(
        "1003",
        "ACCEPTED_BY_MERCHANT",
        False,
        target_date.replace(day=26),
    )
    excluded_signature = _make_order(
        "1004", "ACCEPTED_BY_MERCHANT", True, target_date
    )
    excluded_status = _make_order("1005", "KASPI_DELIVERY", False, target_date)
    excluded_handed = _make_order(
        "1006",
        "ACCEPTED_BY_MERCHANT",
        False,
        target_date,
        assembled=True,
        courier_transmission_date=_ts_for(target_date),
    )
    excluded_old = _make_order(
        "1007", "ACCEPTED_BY_MERCHANT", False, target_date.replace(day=20)
    )

    orders = [
        include_order,
        include_assembled,
        include_overdue,
        excluded_signature,
        excluded_status,
        excluded_handed,
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
    assert captured["signature_required"] is False
    assert "status" not in captured
    assert {o["attributes"]["code"] for o in filtered} == {"1001", "1002", "1003", "1005"}


def test_build_daily_waybills_api_filters_pending_handover(monkeypatch):
    target_date = date(2026, 1, 27)
    include_order = _make_order(
        "1101", "ACCEPTED_BY_MERCHANT", False, target_date
    )
    include_assembled = _make_order(
        "1102",
        "ACCEPTED_BY_MERCHANT",
        False,
        target_date,
        assembled=True,
    )
    exclude_handed = _make_order(
        "1103",
        "ACCEPTED_BY_MERCHANT",
        False,
        target_date,
        assembled=True,
        courier_transmission_date=_ts_for(target_date),
    )

    orders = [include_order, include_assembled, exclude_handed]

    class FakeClient:
        def __init__(self, store_code):
            self.store_code = store_code

        def list_all_orders(self, **kwargs):
            return orders

    monkeypatch.setattr(build_daily_waybills, "KaspiAPIClient", FakeClient)

    result, errored = build_daily_waybills.get_api_order_ids_for_date(
        target_date=target_date,
        since_days=3,
        store_filter="UNIVERSAL",
        include_overdue=True,
    )

    assert errored == set()
    assert result == {"UNIVERSAL": {"1101", "1102"}}


def test_get_target_order_ids_from_db_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("2001", "UNIVERSAL", "Item", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
        ("2002", "UNIVERSAL", "Item", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1, None),
        ("2003", "UNIVERSAL", "Item", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0, None),
        ("2004", "UNIVERSAL", "Item", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0, None),
        ("2005", "UNIVERSAL", "Item", "SKU", "SKU-5", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "SHIPPED", 0, target_date.isoformat()),
        ("2006", "UNIVERSAL", "Item", "SKU", "SKU-6", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "NEW", 0, None),
        ("2007", "UNIVERSAL", "Item", "SKU", "SKU-7", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, target_date.isoformat()),
    ]
    _insert_fact_orders(db_path, rows)

    result = download_waybills_api.get_target_order_ids_from_db(
        db_path=db_path,
        target_date=target_date,
        exact_date=True,
    )

    assert result == {"UNIVERSAL": {"2001", "2003", "2004", "2006"}}


def test_get_target_order_ids_from_db_include_overdue_uses_lookback_window(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("2101", "ACMEWEAR", "Item", "SKU", "SKU-1", 1, "XL", "", "2026-01-27", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
        ("2102", "ACMEWEAR", "Item", "SKU", "SKU-2", 1, "XL", "", "2026-01-26", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
        ("2103", "ACMEWEAR", "Item", "SKU", "SKU-3", 1, "XL", "", "2026-01-22", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
    ]
    _insert_fact_orders(db_path, rows)

    result = download_waybills_api.get_target_order_ids_from_db(
        db_path=db_path,
        target_date=target_date,
        exact_date=False,
        lookback_days=2,
    )

    assert result == {"ACMEWEAR": {"2101", "2102"}}


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
                "Статус": "Принят",
                "Требуется подписание": "Не требуется",
            },
            {
                "OrderID": "3003",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Передан курьеру",
                "Требуется подписание": "Не требуется",
            },
            {
                "OrderID": "3004",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": target_date,
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Требуется",
            },
            {
                "OrderID": "3005",
                "MY_SIZE": "L",
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

    assert result == {"UNIVERSAL": {"3001", "3002", "3005"}}


def test_get_target_order_ids_from_crm_requires_current_batch_rows(tmp_path):
    target_date = date(2026, 3, 10)
    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "849921993",
                "MY_SIZE": "4XL",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "AcmeWear",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850902537",
                "MY_SIZE": "XL",
                "PLANNED_SHIPPING_DATE": "2026-03-10",
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
        exact_date=False,
        lookback_days=3,
    )

    assert result == {"UNIVERSAL": {"850902537"}}


def test_get_target_order_ids_from_crm_backfills_blank_current_day_size_for_overdue_rows(
    tmp_path,
):
    target_date = date(2026, 3, 10)
    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "MY_SIZE": "M",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "SKU_ID": "SKU-TOP",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "SKU_ID": "SKU-TOP",
                "Quantity": 1,
            },
        ]
    )
    df.to_excel(crm_path, index=False)

    result = download_waybills_api.get_target_order_ids_from_crm(
        crm_path=crm_path,
        sheet_name="Sheet1",
        target_date=target_date,
        exact_date=False,
        lookback_days=3,
    )

    assert result == {"UNIVERSAL": {"850084962"}}


def test_get_target_order_ids_from_crm_does_not_backfill_same_day_blank_size(tmp_path):
    target_date = date(2026, 3, 10)
    crm_path = tmp_path / "crm.xlsx"
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "MY_SIZE": "M",
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "SKU_ID": "SKU-TOP",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "STORE_NAME": "Universal",
                "Статус": "Ожидает передачи курьеру",
                "Требуется подписание": "Не требуется",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "SKU_ID": "SKU-TOP",
                "Quantity": 1,
            },
        ]
    )
    df.to_excel(crm_path, index=False)

    result = download_waybills_api.get_target_order_ids_from_crm(
        crm_path=crm_path,
        sheet_name="Sheet1",
        target_date=target_date,
        exact_date=False,
        lookback_days=3,
    )

    assert result == {}


def test_download_all_waybills_uses_current_batch_crm_sizes_as_authoritative_targets(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_date = date(2026, 3, 10)
    api_order = _make_order(
        code="850902537",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(store_code: str, *_args, **_kwargs):
        if store_code == "UNIVERSAL":
            return [api_order], False
        return [], False

    def _fake_get_target_order_ids_from_crm(*_args, **_kwargs):
        return {
            "UNIVERSAL": {"849656111", "850084962", "850902537"},
            "STOREB": {"850732964"},
        }

    captured_targets: dict[str, set[str]] = {}

    def _fake_download_waybills_for_store(**kwargs):
        captured_targets[kwargs["store_code"]] = set(kwargs["target_order_ids"])
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "skipped_terminal": 0,
            "skipped_nonready": 0,
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "get_target_order_ids_from_crm", _fake_get_target_order_ids_from_crm)
    monkeypatch.setattr(
        download_waybills_api,
        "get_target_order_ids_from_db",
        lambda *_args, **_kwargs: {"ACMEWEAR": {"DB_EXTRA"}},
    )
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=tmp_path / "app.db",
        store_filter=None,
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=False,
        fallback_crm=True,
    )

    assert result["fallback_used"] is True
    assert captured_targets["UNIVERSAL"] == {"849656111", "850084962", "850902537"}
    assert captured_targets["STOREB"] == {"850732964"}
    assert "ACMEWEAR" not in captured_targets


def test_build_daily_waybills_read_db_orders_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("4001", "UNIVERSAL", "Item A", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
        ("4002", "UNIVERSAL", "Item B", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1, None),
        ("4003", "UNIVERSAL", "Item C", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0, None),
        ("4004", "UNIVERSAL", "Item D", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0, None),
        ("4005", "UNIVERSAL", "Item E", "SKU", "SKU-5", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "NEW", 0, None),
        ("4006", "UNIVERSAL", "Item F", "SKU", "SKU-6", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, target_date.isoformat()),
    ]
    _insert_fact_orders(db_path, rows)

    orders = build_daily_waybills.read_db_orders(
        db_path=db_path,
        target_date=target_date,
        lookback_days=None,
    )

    order_ids = {o.order_id for o in orders}
    assert order_ids == {"4001", "4003", "4004", "4005"}


def test_validate_pending_orders_db_filters_status_signature(tmp_path):
    db_path = tmp_path / "app.db"
    _init_fact_orders_db(db_path)
    target_date = date(2026, 1, 27)

    rows = [
        ("5001", "UNIVERSAL", "Item", "SKU", "SKU-1", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, None),
        ("5002", "UNIVERSAL", "Item", "SKU", "SKU-2", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "READY", 0, None),
        ("5003", "UNIVERSAL", "Item", "SKU", "SKU-3", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "KASPI_DELIVERY", "READY", 0, None),
        ("5004", "UNIVERSAL", "Item", "SKU", "SKU-4", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "SHIPPED", 0, target_date.isoformat()),
        ("5005", "UNIVERSAL", "Item", "SKU", "SKU-5", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 1, None),
        ("5006", "UNIVERSAL", "Item", "SKU", "SKU-6", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", None, "NEW", 0, None),
        ("5007", "UNIVERSAL", "Item", "SKU", "SKU-7", 1, "L", "", target_date.isoformat(), "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", "READY", 0, target_date.isoformat()),
    ]
    _insert_fact_orders(db_path, rows)

    total, pending = validate_pending_orders.read_db_pending(
        db_path=db_path,
        target_date=target_date,
        include_overdue=False,
        lookback_days=None,
    )

    assert total == 7
    assert pending == {"5001", "5002", "5003", "5006"}


def test_build_waybill_loader_respects_order_id_filter(tmp_path):
    waybill_dir = tmp_path / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    (waybill_dir / "1001.pdf").write_bytes(b"%PDF-1.4")
    (waybill_dir / "1002.pdf").write_bytes(b"%PDF-1.4")

    selected = {"1002"}
    loaded = build_daily_waybills.load_waybills_from_folder(
        waybill_dir, order_id_filter=selected
    )

    assert set(loaded.keys()) == {"1002"}


def test_build_zip_loader_respects_order_id_filter(tmp_path):
    zip_dir = tmp_path / "active"
    temp_dir = tmp_path / "temp"
    zip_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / "waybill_test.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("KASPI_SHOP-2001.pdf", b"%PDF-1.4")
        zf.writestr("KASPI_SHOP-2002.pdf", b"%PDF-1.4")

    loaded = build_daily_waybills.extract_waybills_from_zips(
        zip_dir, temp_dir, order_id_filter={"2001"}
    )

    assert set(loaded.keys()) == {"2001"}


def test_download_waybills_for_store_processes_fallback_targets_not_in_prefetch(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    prefetched_orders = [
        _make_order(
            code="7001",
            status="ACCEPTED_BY_MERCHANT",
            signature=False,
            planned=date(2026, 2, 22),
            assembled=True,
        )
    ]
    prefetched_orders[0]["attributes"]["kaspiDelivery"]["waybill"] = (
        "https://example.local/7001.pdf"
    )

    def _detail_order(code: str) -> dict:
        order = _make_order(
            code=code,
            status="ACCEPTED_BY_MERCHANT",
            signature=False,
            planned=date(2026, 2, 22),
            assembled=True,
        )
        order["attributes"]["kaspiDelivery"]["waybill"] = (
            f"https://example.local/{code}.pdf"
        )
        return order

    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def get_waybill_url(self, order: dict) -> Optional[str]:
            return order.get("attributes", {}).get("kaspiDelivery", {}).get("waybill")

        def get_order(self, order_code: str) -> APIResponse:
            return APIResponse(success=True, data=_detail_order(order_code), status_code=200)

        def download_waybill(self, waybill_url: str, timeout: Optional[int] = None) -> APIResponse:
            return APIResponse(success=True, data=b"%PDF-1.4 test\n", status_code=200)

    monkeypatch.setattr(download_waybills_api, "KaspiAPIClient", FakeClient)

    result = download_waybills_api.download_waybills_for_store(
        store_code="UNIVERSAL",
        target_order_ids={"7001", "7002"},
        output_dir=output_dir,
        since_days=1,
        download_timeout=10,
        dry_run=False,
        verbose=False,
        prefetched_orders=prefetched_orders,
    )

    assert result["downloaded"] == 2
    assert result["missing_waybill"] == 0
    assert (output_dir / "7001.pdf").exists()
    assert (output_dir / "7002.pdf").exists()


def test_download_waybills_for_store_skips_cancelled_fallback_without_retry(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    calls = {"get_order": 0, "download": 0}

    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def get_waybill_url(self, order: dict) -> Optional[str]:
            return order.get("attributes", {}).get("kaspiDelivery", {}).get("waybill")

        def get_order(self, order_code: str) -> APIResponse:
            calls["get_order"] += 1
            order = _make_order(
                code=order_code,
                status="CANCELLED",
                signature=False,
                planned=date(2026, 2, 22),
                assembled=False,
            )
            return APIResponse(success=True, data=order, status_code=200)

        def download_waybill(self, waybill_url: str, timeout: Optional[int] = None) -> APIResponse:
            calls["download"] += 1
            return APIResponse(success=True, data=b"%PDF-1.4 test\n", status_code=200)

    monkeypatch.setattr(download_waybills_api, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(download_waybills_api, "WAYBILL_RETRY_DELAY", 0)
    monkeypatch.setattr(download_waybills_api, "WAYBILL_RETRY_PASSES", 3)
    monkeypatch.setattr(download_waybills_api, "WAYBILL_RETRY_DELAY_UNIVERSAL", 0)
    monkeypatch.setattr(download_waybills_api, "WAYBILL_RETRY_PASSES_UNIVERSAL", 3)

    result = download_waybills_api.download_waybills_for_store(
        store_code="UNIVERSAL",
        target_order_ids={"835522716"},
        output_dir=output_dir,
        since_days=1,
        download_timeout=10,
        dry_run=False,
        verbose=False,
        prefetched_orders=[],
    )

    assert result["downloaded"] == 0
    assert result["missing_waybill"] == 0
    assert result["skipped_terminal"] == 1
    assert calls["get_order"] == 1
    assert calls["download"] == 0


def test_download_all_waybills_writes_selection_cache(tmp_path, monkeypatch):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_date = date(2026, 2, 22)
    fake_order = _make_order(
        code="8801",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(*args, **kwargs):
        return ([fake_order], False)

    def _fake_download_waybills_for_store(**kwargs):
        return {
            "downloaded": 1,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "missing.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=None,
        store_filter="UNIVERSAL",
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=True,
        fallback_crm=False,
    )

    assert result["downloaded"] == 1
    cache_path = output_dir / "_waybill_selection_orders.json"
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["target_date"] == target_date.isoformat()
    assert payload["stores"]["UNIVERSAL"] == ["8801"]


def test_download_all_waybills_excludes_terminal_orders_from_selection_cache(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_date = date(2026, 2, 22)
    api_order = _make_order(
        code="API100",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(*args, **kwargs):
        return ([api_order], False)

    def _fake_get_target_order_ids_from_crm(*_args, **_kwargs):
        return {"UNIVERSAL": {"API100", "CANCEL1"}}

    def _fake_download_waybills_for_store(**kwargs):
        # Store receives fallback union, but terminal orders must be removed
        # from persisted target selection for downstream parity.
        assert kwargs["target_order_ids"] == {"API100", "CANCEL1"}
        return {
            "downloaded": 1,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "skipped_terminal": 1,
            "terminal_skipped_order_ids": ["CANCEL1"],
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "get_target_order_ids_from_crm", _fake_get_target_order_ids_from_crm)
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=tmp_path / "app.db",
        store_filter="UNIVERSAL",
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=False,
        fallback_crm=True,
    )

    assert result["skipped_terminal"] == 1
    cache_path = output_dir / "_waybill_selection_orders.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["stores"]["UNIVERSAL"] == ["API100"]


def test_download_all_waybills_fallback_does_not_expand_store_when_api_has_orders(tmp_path, monkeypatch):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_date = date(2026, 2, 23)
    api_order = _make_order(
        code="API100",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(store_code: str, *_args, **_kwargs):
        if store_code == "UNIVERSAL":
            return [api_order], False
        return [], False

    def _fake_get_target_order_ids_from_crm(*_args, **_kwargs):
        return {
            "UNIVERSAL": {"CRM_EXTRA"},
            "ACMEWEAR": {"ACMEWEAR_FALLBACK"},
        }

    captured_targets: dict[str, set[str]] = {}

    def _fake_download_waybills_for_store(**kwargs):
        captured_targets[kwargs["store_code"]] = set(kwargs["target_order_ids"])
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "get_target_order_ids_from_crm", _fake_get_target_order_ids_from_crm)
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=tmp_path / "app.db",
        store_filter=None,
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=True,
        fallback_crm=True,
    )

    assert result["fallback_used"] is True
    assert captured_targets["UNIVERSAL"] == {"CRM_EXTRA"}
    assert captured_targets["ACMEWEAR"] == {"ACMEWEAR_FALLBACK"}


def test_download_all_waybills_include_overdue_skips_cached_fallback_when_api_has_orders(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "DB_EXTRA.pdf").write_bytes(b"%PDF-1.4")
    (output_dir / "CRM_EXTRA.pdf").write_bytes(b"%PDF-1.4")

    target_date = date(2026, 2, 23)
    api_order = _make_order(
        code="API100",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(store_code: str, *_args, **_kwargs):
        if store_code == "UNIVERSAL":
            return [api_order], False
        return [], False

    def _fake_get_target_order_ids_from_crm(*_args, **_kwargs):
        return {
            "UNIVERSAL": {"CRM_EXTRA"},
            "ACMEWEAR": {"ACMEWEAR_FALLBACK"},
        }

    captured_targets: dict[str, set[str]] = {}

    def _fake_download_waybills_for_store(**kwargs):
        captured_targets[kwargs["store_code"]] = set(kwargs["target_order_ids"])
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "get_target_order_ids_from_crm", _fake_get_target_order_ids_from_crm)
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=tmp_path / "app.db",
        store_filter=None,
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=False,
        fallback_crm=True,
    )

    assert result["fallback_used"] is True
    assert captured_targets["UNIVERSAL"] == {"CRM_EXTRA"}
    assert captured_targets["ACMEWEAR"] == {"ACMEWEAR_FALLBACK"}


def test_download_all_waybills_include_overdue_keeps_missing_pdf_fallback_when_api_has_orders(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "DB_EXTRA.pdf").write_bytes(b"%PDF-1.4")

    target_date = date(2026, 2, 23)
    api_order = _make_order(
        code="API100",
        status="ACCEPTED_BY_MERCHANT",
        signature=False,
        planned=target_date,
        assembled=True,
    )

    def _fake_get_target_orders_from_api(store_code: str, *_args, **_kwargs):
        if store_code == "UNIVERSAL":
            return [api_order], False
        return [], False

    def _fake_get_target_order_ids_from_crm(*_args, **_kwargs):
        return {
            "UNIVERSAL": {"CRM_EXTRA"},
        }

    captured_targets: dict[str, set[str]] = {}

    def _fake_download_waybills_for_store(**kwargs):
        captured_targets[kwargs["store_code"]] = set(kwargs["target_order_ids"])
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 0,
            "invalid_pdf": 0,
            "errors": [],
        }

    monkeypatch.setattr(download_waybills_api, "get_target_orders_from_api", _fake_get_target_orders_from_api)
    monkeypatch.setattr(download_waybills_api, "get_target_order_ids_from_crm", _fake_get_target_order_ids_from_crm)
    monkeypatch.setattr(download_waybills_api, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = download_waybills_api.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=target_date,
        db_path=tmp_path / "app.db",
        store_filter=None,
        since_days=3,
        download_timeout=20,
        dry_run=False,
        verbose=False,
        all_dates=False,
        exact_date=False,
        fallback_crm=True,
    )

    assert result["fallback_used"] is True
    assert captured_targets["UNIVERSAL"] == {"CRM_EXTRA"}
