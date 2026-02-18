import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from core.integrations.kaspi_api_client import APIResponse
from scripts import ship_orders_api as ship_mod
from scripts.ship_orders_api import read_crm_orders


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
