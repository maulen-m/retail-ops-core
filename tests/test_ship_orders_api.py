import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo
import sys

import pandas as pd
import pytest

from core.integrations.kaspi_api_client import APIResponse
from scripts import ship_orders_api as ship_mod
from scripts.ship_orders_api import parse_date, read_crm_orders


def _write_crm(tmp_path, rows):
    df = pd.DataFrame(rows)
    path = tmp_path / "crm.xlsx"
    df.to_excel(path, index=False)
    return path


def test_read_crm_orders_includes_missing_size_by_default(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "OrderID": "123",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": date.today(),
                "STORE_NAME": "Store-C",
                "Kaspi_name_core": "PRINT_5V1_BLACK",
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "SKU_ID": "CL_OC_MEN_LINE52_BLACK_L",
                "Quantity": 1,
            }
        ],
    )

    orders = read_crm_orders(crm_path, "Sheet1", date.today())

    assert "123" in orders
    assert orders["123"][0].my_size == ""


def test_read_crm_orders_can_require_size(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "OrderID": "456",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": date.today(),
                "STORE_NAME": "AcmeWear",
                "Kaspi_name_core": "LINE51",
                "SKU_key": "CL_NK_MEN_LINE51_WHITE",
                "SKU_ID": "CL_NK_MEN_LINE51_WHITE_L",
                "Quantity": 1,
            }
        ],
    )

    orders = read_crm_orders(crm_path, "Sheet1", date.today(), allow_missing_size=False)

    assert orders == {}


def test_read_crm_orders_drops_historical_carry_forward_duplicates(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "Date": "2026-03-06",
                "OrderID": "846479842",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": "2026-03-06",
                "STORE_NAME": "STORE-B",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-07",
                "OrderID": "846479842",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": "2026-03-06",
                "STORE_NAME": "STORE-B",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-08",
                "OrderID": "846479842",
                "MY_SIZE": "L",
                "PLANNED_SHIPPING_DATE": "2026-03-06",
                "STORE_NAME": "STORE-B",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-08",
                "OrderID": "848253366",
                "MY_SIZE": "3XL",
                "PLANNED_SHIPPING_DATE": "2026-03-08",
                "STORE_NAME": "STORE-B",
                "Kaspi_name_core": "Трусы_черные",
                "KASPI_OFFER_NAME": "Тайтсы PRO COMBAT 17 черный 3XL",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-08",
                "OrderID": "848253366",
                "MY_SIZE": "2XL",
                "PLANNED_SHIPPING_DATE": "2026-03-08",
                "STORE_NAME": "STORE-B",
                "Kaspi_name_core": "Трусы_черные",
                "KASPI_OFFER_NAME": "Тайтсы PRO COMBAT 17 черный XL",
                "Quantity": 1,
            },
        ],
    )

    orders = read_crm_orders(
        crm_path,
        "Sheet1",
        date(2026, 3, 8),
        target_order_ids={"846479842", "848253366"},
        apply_date_filter=False,
    )

    assert len(orders["846479842"]) == 1
    assert len(orders["848253366"]) == 2


def test_read_crm_orders_requires_current_batch_rows_and_manual_crm_sizes(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "Date": "2026-03-09",
                "OrderID": "849921993",
                "MY_SIZE": "4XL",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "AcmeWear",
                "Kaspi_name_core": "Line51",
                "KASPI_OFFER_NAME": "Спортивный костюм ACMEWEAR AcmeWear 05 черный, белый 4XL",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850750129",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "STORE_NAME": "Universal",
                "Kaspi_name_core": "Леггинсы_белый",
                "KASPI_OFFER_NAME": "Леггинсы PRO COMBAT 2010 белый XL",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850902537",
                "MY_SIZE": "XL",
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "STORE_NAME": "Universal",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_662528941 черный 2XL",
                "Quantity": 1,
            },
        ],
    )

    orders = read_crm_orders(
        crm_path,
        "Sheet1",
        date(2026, 3, 10),
        target_order_ids={"849921993", "850750129", "850902537"},
        db_order_info={
            "849921993": {"size": "4XL"},
            "850750129": {"size": "XL"},
        },
        allow_missing_size=False,
    )

    assert set(orders.keys()) == {"850902537"}
    assert orders["850902537"][0].my_size == "XL"


def test_read_crm_orders_backfills_blank_current_day_size_for_overdue_rows(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "MY_SIZE": "M",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "Universal",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "SKU_ID": "SKU-TOP",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "STORE_NAME": "Universal",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "SKU_ID": "SKU-TOP",
            },
        ],
    )

    orders = read_crm_orders(
        crm_path,
        "Sheet1",
        date(2026, 3, 10),
        target_order_ids={"850084962"},
        allow_missing_size=False,
    )

    assert set(orders.keys()) == {"850084962"}
    assert orders["850084962"][0].my_size == "M"


def test_parse_date_handles_iso_datetime_without_dayfirst_flip():
    assert parse_date("2026-03-06 20:00:00") == date(2026, 3, 6)


def test_get_pending_assembly_orders_status_first_without_creation_lookback(monkeypatch):
    calls = []
    tz = ZoneInfo("Asia/Almaty")

    def _ms(dt_str: str) -> int:
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=tz)
        return int(dt.timestamp() * 1000)

    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_orders(
            self,
            state=None,
            status=None,
            since=None,
            until=None,
            page_number=0,
            page_size=100,
            delivery_type=None,
            signature_required=None,
            include_orders=None,
        ):
            calls.append(
                {
                    "state": state,
                    "status": status,
                    "since": since,
                    "page_number": page_number,
                    "page_size": page_size,
                }
            )
            if page_number > 0:
                return APIResponse(success=True, data={"data": [], "meta": {"pageCount": 1}}, status_code=200)
            return APIResponse(
                success=True,
                data={
                    "data": [
                        {
                            "id": "base64-818884703",
                            "attributes": {
                                "code": "818884703",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-02-12T14:11:44"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-02-17T20:00:00")},
                            },
                        },
                        {
                            "id": "base64-future",
                            "attributes": {
                                "code": "900000001",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-02-12T15:00:00"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-02-18T20:00:00")},
                            },
                        },
                        {
                            "id": "base64-assembled",
                            "attributes": {
                                "code": "900000002",
                                "assembled": True,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-02-12T16:00:00"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-02-17T20:00:00")},
                            },
                        },
                    ],
                    "meta": {"pageCount": 1},
                },
                status_code=200,
            )

    monkeypatch.setattr(ship_mod, "STORE_TOKEN_MAP", {"STOREB": "token"})
    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)

    pending, base64_map, planned_map, pending_meta = ship_mod.get_pending_assembly_orders(
        target_date=date(2026, 2, 17),
        since_days=None,
        store_codes={"STOREB"},
    )

    assert pending == {"STOREB": {"818884703"}}
    assert base64_map["STOREB"]["818884703"] == "base64-818884703"
    assert planned_map["STOREB"]["818884703"] == date(2026, 2, 17)
    assert pending_meta["STOREB"]["818884703"]["created_at"].date() == date(2026, 2, 12)
    assert all(call["since"] is None for call in calls)
    assert calls[0]["state"] == "KASPI_DELIVERY"
    assert calls[0]["status"] == "ACCEPTED_BY_MERCHANT"


def test_get_pending_assembly_orders_include_overdue_honors_lookback(monkeypatch):
    tz = ZoneInfo("Asia/Almaty")

    def _ms(dt_str: str) -> int:
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=tz)
        return int(dt.timestamp() * 1000)

    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_orders(
            self,
            state=None,
            status=None,
            since=None,
            until=None,
            page_number=0,
            page_size=100,
            delivery_type=None,
            signature_required=None,
            include_orders=None,
        ):
            if page_number > 0:
                return APIResponse(success=True, data={"data": [], "meta": {"pageCount": 1}}, status_code=200)
            return APIResponse(
                success=True,
                data={
                    "data": [
                        {
                            "id": "base64-today",
                            "attributes": {
                                "code": "845767451",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-03-05T14:11:44"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-03-07T20:00:00")},
                            },
                        },
                        {
                            "id": "base64-overdue",
                            "attributes": {
                                "code": "845784291",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-03-05T15:11:44"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-03-06T20:00:00")},
                            },
                        },
                        {
                            "id": "base64-too-old",
                            "attributes": {
                                "code": "845785318",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-03-04T15:11:44"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-03-04T20:00:00")},
                            },
                        },
                    ],
                    "meta": {"pageCount": 1},
                },
                status_code=200,
            )

    monkeypatch.setattr(ship_mod, "STORE_TOKEN_MAP", {"STOREB": "token"})
    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)

    pending, base64_map, planned_map, _pending_meta = ship_mod.get_pending_assembly_orders(
        target_date=date(2026, 3, 7),
        since_days=None,
        store_codes={"STOREB"},
        include_overdue=True,
        overdue_lookback_days=1,
    )

    assert pending == {"STOREB": {"845767451", "845784291"}}
    assert base64_map["STOREB"]["845767451"] == "base64-today"
    assert base64_map["STOREB"]["845784291"] == "base64-overdue"
    assert planned_map["STOREB"]["845767451"] == date(2026, 3, 7)
    assert planned_map["STOREB"]["845784291"] == date(2026, 3, 6)
    assert "845785318" not in pending["STOREB"]


def test_summarize_pending_backlog_flags_stale_overdue_orders():
    pending_meta = {
        "STOREB": {
            "818884703": {
                "planned_date": date(2026, 2, 17),
                "created_at": datetime(2026, 2, 12, 14, 11, 44),
            },
            "900000001": {
                "planned_date": date(2026, 2, 18),
                "created_at": datetime(2026, 2, 18, 8, 0, 0),
            },
        }
    }

    report = ship_mod.summarize_pending_backlog(
        pending_meta_by_store=pending_meta,
        target_date=date(2026, 2, 17),
        stale_hours=24,
        now_dt=datetime(2026, 2, 18, 12, 0, 0),
    )

    assert report["total_pending"] == 2
    assert report["overdue_pending"] == 1
    assert report["stale_pending"] == 1
    assert report["stale_orders"][0]["order_id"] == "818884703"


def test_build_pending_backlog_report_includes_age_buckets_and_exact_ids():
    pending_meta = {
        "STOREB": {
            "818884703": {
                "planned_date": date(2026, 2, 17),
                "created_at": datetime(2026, 2, 12, 14, 11, 44),
                "fetch_mode": "status_first",
            },
            "900000001": {
                "planned_date": date(2026, 2, 14),
                "created_at": datetime(2026, 2, 13, 8, 0, 0),
                "fetch_mode": "fallback_since",
            },
        }
    }

    report = ship_mod.build_pending_backlog_report(
        pending_meta,
        target_date=date(2026, 2, 17),
        stale_hours=24,
        now_dt=datetime(2026, 2, 18, 12, 0, 0),
    )

    assert report["summary"]["overdue_pending"] == 2
    assert report["age_buckets"]["1d"] == 1
    assert report["age_buckets"]["4-7d"] == 1
    assert [row["order_id"] for row in report["overdue_orders"]] == ["900000001", "818884703"]


def test_write_pending_backlog_report_creates_json_and_md(tmp_path):
    report = ship_mod.build_pending_backlog_report(
        {
            "STOREB": {
                "818884703": {
                    "planned_date": date(2026, 2, 17),
                    "created_at": datetime(2026, 2, 12, 14, 11, 44),
                }
            }
        },
        target_date=date(2026, 2, 17),
        now_dt=datetime(2026, 2, 18, 12, 0, 0),
    )

    json_path, md_path = ship_mod.write_pending_backlog_report(
        target_date=date(2026, 2, 17),
        store_scope="STORE-B",
        dry_run=True,
        include_overdue=True,
        overdue_lookback_days=7,
        initial_report=report,
        remaining_report=None,
        output_root=tmp_path,
    )

    assert json_path.exists()
    assert md_path.exists()
    assert "818884703" in md_path.read_text(encoding="utf-8")
    assert '"store_scope": "STORE-B"' in json_path.read_text(encoding="utf-8")


def test_get_pending_assembly_orders_falls_back_when_status_first_api_requires_since(monkeypatch):
    calls = {"status_first": 0, "fallback_since": []}
    tz = ZoneInfo("Asia/Almaty")

    def _ms(dt_str: str) -> int:
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=tz)
        return int(dt.timestamp() * 1000)

    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_orders(
            self,
            state=None,
            status=None,
            since=None,
            until=None,
            page_number=0,
            page_size=100,
            delivery_type=None,
            signature_required=None,
            include_orders=None,
        ):
            calls["status_first"] += 1
            return APIResponse(
                success=False,
                data={},
                error={"errors": [{"title": "Required filter [orders][creationDate][$ge] is empty."}]},
                status_code=400,
            )

        def get_pending_assembly_orders(self, since=None):
            calls["fallback_since"].append(since)
            return APIResponse(
                success=True,
                data={
                    "data": [
                        {
                            "id": "base64-818884703",
                            "attributes": {
                                "code": "818884703",
                                "assembled": False,
                                "status": "ACCEPTED_BY_MERCHANT",
                                "creationDate": _ms("2026-02-12T14:11:44"),
                                "kaspiDelivery": {"courierTransmissionPlanningDate": _ms("2026-02-17T20:00:00")},
                            },
                        }
                    ],
                    "meta": {"totalCount": 1},
                },
                status_code=200,
            )

    monkeypatch.setattr(ship_mod, "STORE_TOKEN_MAP", {"STOREB": "token"})
    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)

    pending, base64_map, planned_map, pending_meta = ship_mod.get_pending_assembly_orders(
        target_date=date(2026, 2, 17),
        since_days=None,
        store_codes={"STOREB"},
        fallback_since_days=30,
    )

    assert pending == {"STOREB": {"818884703"}}
    assert base64_map["STOREB"]["818884703"] == "base64-818884703"
    assert planned_map["STOREB"]["818884703"] == date(2026, 2, 17)
    assert pending_meta["STOREB"]["818884703"]["fetch_mode"] == "fallback-creation-lookback-30d"
    assert calls["status_first"] >= 1
    assert len(calls["fallback_since"]) == 1


def test_derive_dynamic_since_days_expands_window_for_stale_backlog(tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_status TEXT,
            internal_status TEXT,
            planned_shipment_date TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, kaspi_status, internal_status, planned_shipment_date, created_at)
        VALUES
        ('818884703', 'STOREB', 'KASPI_DELIVERY', 'ACCEPTED', '2026-02-17', '2026-01-20 09:00:00')
        """
    )
    conn.commit()
    conn.close()

    days = ship_mod.derive_dynamic_since_days(
        db_path=db_path,
        target_date=date(2026, 2, 17),
        store_codes={"STOREB"},
        default_days=14,
        max_days=120,
    )

    assert days >= 29


def test_ship_orders_does_not_count_unconfirmed_assemble(monkeypatch):
    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def assemble_order_by_id(self, base64_id, order_code, parcel_count=1):
            return APIResponse(success=True, data={"ok": True}, status_code=200)

        def assemble_order(self, order_code, parcel_count=1):
            return APIResponse(success=True, data={"ok": True}, status_code=200)

        def get_order_by_id(self, base64_id):
            return APIResponse(
                success=True,
                data={"attributes": {"assembled": False, "kaspiDelivery": {"waybill": None}}},
                status_code=200,
            )

        def get_order(self, order_code):
            return APIResponse(
                success=True,
                data={"attributes": {"assembled": False, "kaspiDelivery": {"waybill": None}}},
                status_code=200,
            )

        def get_waybill_url(self, order):
            return None

        def get_pending_assembly_orders(self, since=None):
            return APIResponse(success=True, data={"data": []}, status_code=200)

    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_RETRIES", 1)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_DELAY", 0)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_REFRESH_RETRIES", 0)
    monkeypatch.setattr(ship_mod, "STORE_NAME_TO_API_CODE", {"Universal": "UNIVERSAL"})

    orders_by_id = {
        "829336594": [
            ship_mod.OrderItem(
                order_id="829336594",
                store_name="Universal",
                kaspi_name_core="Принт_5в1_черный",
                my_size="XL",
                sku_key="CL_OC_MEN_LINE52_BLACK",
                sku_id="CL_OC_MEN_LINE52_BLACK_XL",
                quantity=1,
                planned_date=date(2026, 2, 20),
            )
        ]
    }
    pending_orders = {"UNIVERSAL": {"829336594"}}
    order_id_to_base64 = {"UNIVERSAL": {"829336594": "ODI5MzM2NTk0"}}

    result = ship_mod.ship_orders(
        orders_by_id=orders_by_id,
        pending_orders=pending_orders,
        order_id_to_base64=order_id_to_base64,
        dry_run=False,
        verbose=False,
        since_days=1,
    )

    assert result["shipped"] == 0
    assert any("829336594" in err for err in result["errors"])


def test_main_limits_pending_fetch_scope_when_store_filter_is_set(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_get_pending_assembly_orders(
        *,
        target_date,
        since_days,
        store_codes=None,
        fallback_since_days=30,
        include_overdue=False,
        overdue_lookback_days=None,
    ):
        captured["target_date"] = target_date
        captured["since_days"] = since_days
        captured["store_codes"] = store_codes
        captured["fallback_since_days"] = fallback_since_days
        captured["include_overdue"] = include_overdue
        captured["overdue_lookback_days"] = overdue_lookback_days
        return {"UNIVERSAL": set()}, {}, {}, {}

    monkeypatch.setattr(ship_mod, "get_pending_assembly_orders", fake_get_pending_assembly_orders)
    monkeypatch.setattr(ship_mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship_orders_api.py",
            "--store",
            "Universal",
            "--crm-file",
            str(tmp_path / "unused.xlsx"),
            "--dry-run",
        ],
    )

    rc = ship_mod.main()

    assert rc == 0
    assert captured["store_codes"] == {"UNIVERSAL"}
    assert captured["include_overdue"] is True
    assert captured["overdue_lookback_days"] == 7


def test_main_returns_nonzero_when_overdue_backlog_remains(monkeypatch, tmp_path):
    calls = {"count": 0}
    pending_meta = {
        "STOREB": {
            "845767451": {
                "planned_date": date(2026, 3, 5),
                "created_at": datetime(2026, 3, 5, 8, 0, 0),
            }
        }
    }

    def fake_get_pending_assembly_orders(
        *,
        target_date,
        since_days,
        store_codes=None,
        fallback_since_days=30,
        include_overdue=False,
        overdue_lookback_days=None,
    ):
        calls["count"] += 1
        return {"STOREB": {"845767451"}}, {"STOREB": {"845767451": "base64"}}, {}, pending_meta

    monkeypatch.setattr(ship_mod, "get_pending_assembly_orders", fake_get_pending_assembly_orders)
    monkeypatch.setattr(ship_mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(ship_mod, "resolve_db_path", lambda _path: tmp_path / "app.db")
    monkeypatch.setattr(ship_mod, "load_db_order_info", lambda _db, _ids: {})
    monkeypatch.setattr(
        ship_mod,
        "read_crm_orders",
        lambda *args, **kwargs: {
            "845767451": [
                ship_mod.OrderItem(
                    order_id="845767451",
                    store_name="STORE-B",
                    kaspi_name_core="Принт_5в1_черный",
                    my_size="XL",
                    sku_key="CL_OC_MEN_LINE52_BLACK",
                    sku_id="CL_OC_MEN_LINE52_BLACK_XL",
                    quantity=1,
                    planned_date=date(2026, 3, 5),
                )
            ]
        },
    )
    monkeypatch.setattr(
        ship_mod,
        "ship_orders",
        lambda *args, **kwargs: {"shipped": 1, "skipped": 0, "errors": []},
    )
    monkeypatch.setattr(
        ship_mod,
        "write_pending_backlog_report",
        lambda **kwargs: (tmp_path / "backlog.json", tmp_path / "backlog.md"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship_orders_api.py",
            "--store",
            "STORE-B",
            "--crm-file",
            str(tmp_path / "unused.xlsx"),
            "--date",
            "2026-03-06",
        ],
    )

    rc = ship_mod.main()

    assert rc == 1
    assert calls["count"] == 2


def test_ship_orders_counts_when_assemble_is_confirmed(monkeypatch):
    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def assemble_order_by_id(self, base64_id, order_code, parcel_count=1):
            return APIResponse(success=True, data={"ok": True}, status_code=200)

        def get_order_by_id(self, base64_id):
            return APIResponse(
                success=True,
                data={"attributes": {"assembled": True, "kaspiDelivery": {"waybill": "https://example"}}},
                status_code=200,
            )

        def get_order(self, order_code):
            return APIResponse(
                success=True,
                data={"attributes": {"assembled": True, "kaspiDelivery": {"waybill": "https://example"}}},
                status_code=200,
            )

        def get_waybill_url(self, order):
            return "https://example"

        def get_pending_assembly_orders(self, since=None):
            return APIResponse(success=True, data={"data": []}, status_code=200)

    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_RETRIES", 1)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_DELAY", 0)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_REFRESH_RETRIES", 0)
    monkeypatch.setattr(ship_mod, "STORE_NAME_TO_API_CODE", {"Universal": "UNIVERSAL"})

    orders_by_id = {
        "829336594": [
            ship_mod.OrderItem(
                order_id="829336594",
                store_name="Universal",
                kaspi_name_core="Принт_5в1_черный",
                my_size="XL",
                sku_key="CL_OC_MEN_LINE52_BLACK",
                sku_id="CL_OC_MEN_LINE52_BLACK_XL",
                quantity=1,
                planned_date=date(2026, 2, 20),
            )
        ]
    }
    pending_orders = {"UNIVERSAL": {"829336594"}}
    order_id_to_base64 = {"UNIVERSAL": {"829336594": "ODI5MzM2NTk0"}}

    result = ship_mod.ship_orders(
        orders_by_id=orders_by_id,
        pending_orders=pending_orders,
        order_id_to_base64=order_id_to_base64,
        dry_run=False,
        verbose=False,
        since_days=1,
    )

    assert result["shipped"] == 1
    assert result["errors"] == []


def test_ship_orders_confirm_check_falls_back_to_get_order_when_no_get_order_by_id(monkeypatch):
    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def assemble_order_by_id(self, base64_id, order_code, parcel_count=1):
            return APIResponse(success=True, data={"ok": True}, status_code=200)

        def get_order(self, order_code):
            return APIResponse(
                success=True,
                data={"attributes": {"assembled": True, "kaspiDelivery": {"waybill": "https://example"}}},
                status_code=200,
            )

        def get_waybill_url(self, order):
            return "https://example"

        def get_pending_assembly_orders(self, since=None):
            return APIResponse(success=True, data={"data": []}, status_code=200)

    monkeypatch.setattr(ship_mod, "KaspiAPIClient", _FakeClient)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_RETRIES", 1)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_VERIFY_DELAY", 0)
    monkeypatch.setattr(ship_mod, "ASSEMBLE_REFRESH_RETRIES", 0)
    monkeypatch.setattr(ship_mod, "STORE_NAME_TO_API_CODE", {"Universal": "UNIVERSAL"})

    orders_by_id = {
        "829336594": [
            ship_mod.OrderItem(
                order_id="829336594",
                store_name="Universal",
                kaspi_name_core="Принт_5в1_черный",
                my_size="XL",
                sku_key="CL_OC_MEN_LINE52_BLACK",
                sku_id="CL_OC_MEN_LINE52_BLACK_XL",
                quantity=1,
                planned_date=date(2026, 2, 20),
            )
        ]
    }
    pending_orders = {"UNIVERSAL": {"829336594"}}
    order_id_to_base64 = {"UNIVERSAL": {"829336594": "ODI5MzM2NTk0"}}

    result = ship_mod.ship_orders(
        orders_by_id=orders_by_id,
        pending_orders=pending_orders,
        order_id_to_base64=order_id_to_base64,
        dry_run=False,
        verbose=False,
        since_days=1,
    )

    assert result["shipped"] == 1
    assert result["errors"] == []
