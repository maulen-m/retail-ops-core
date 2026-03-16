from scripts import export_api_orders as mod
from scripts.export_api_orders import filter_rows_by_planned_date


def _delivery_order(
    code: str,
    *,
    assembled: bool = False,
    courier_transmission_date=None,
    creation_date=None,
    courier_transmission_planning_date=1772920800000,
):
    attrs = {
        "code": code,
        "state": "KASPI_DELIVERY",
        "status": "ACCEPTED_BY_MERCHANT",
        "assembled": assembled,
        "creationDate": creation_date,
        "kaspiDelivery": {
            "courierTransmissionPlanningDate": courier_transmission_planning_date,
        },
        "customer": {},
    }
    if courier_transmission_date is not None:
        attrs["courierTransmissionDate"] = courier_transmission_date
    return {"id": f"base64-{code}", "attributes": attrs}


def test_filter_rows_by_planned_date_exact():
    rows = [
        {"Плановая дата передачи курьеру": "01.01.2026"},
        {"Плановая дата передачи курьеру": "03.01.2026"},
    ]

    filtered = filter_rows_by_planned_date(
        rows, target_date="03.01.2026", include_overdue=False
    )

    assert len(filtered) == 1
    assert filtered[0]["Плановая дата передачи курьеру"] == "03.01.2026"


def test_filter_rows_by_planned_date_include_overdue():
    rows = [
        {"Плановая дата передачи курьеру": "01.01.2026"},
        {"Плановая дата передачи курьеру": "03.01.2026"},
        {"Плановая дата передачи курьеру": "05.01.2026"},
    ]

    filtered = filter_rows_by_planned_date(
        rows, target_date="03.01.2026", include_overdue=True
    )

    planned = [row["Плановая дата передачи курьеру"] for row in filtered]
    assert planned == ["01.01.2026", "03.01.2026"]


def test_export_store_orders_excludes_in_delivery_orders_from_pending_export(monkeypatch):
    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return [
                _delivery_order("PENDING", assembled=False),
                _delivery_order("SHIPPED", assembled=True, courier_transmission_date=1772973600000),
            ]

        def get_order_entries_by_id(self, _order_id: str):
            return type("Resp", (), {"success": True, "data": {"data": []}})()

    monkeypatch.setattr(mod, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(
        mod,
        "order_to_rows",
        lambda order, entries, store_code, client=None: [
            {"№ заказа": order.get("attributes", {}).get("code", ""), "store": store_code, "entries": len(entries)}
        ],
    )

    rows = mod.export_store_orders(
        store_code="UNIVERSAL",
        state="KASPI_DELIVERY",
        days=3,
        include_archive=False,
    )

    assert [row["№ заказа"] for row in rows] == ["PENDING"]


def test_order_to_rows_keeps_pending_delivery_rows_unissued():
    rows = mod.order_to_rows(
        _delivery_order("PENDING", assembled=True),
        entries=[{"attributes": {"offer": {"name": "Item", "merchantProductId": "SKU1"}, "quantity": 1, "basePrice": 1000}}],
        store_code="UNIVERSAL",
    )

    assert len(rows) == 1
    assert rows[0]["Статус"] == "Ожидает передачи курьеру"
    assert rows[0]["Выдал"] == ""


def test_order_to_rows_uses_raw_courier_planning_date_for_next_day_orders():
    rows = mod.order_to_rows(
        _delivery_order(
            "NEXTDAY",
            creation_date=1772877981000,  # 2026-03-07 15:06:21 +05:00
            courier_transmission_planning_date=1772982000000,  # 2026-03-08 20:00:00 +05:00
        ),
        entries=[
            {
                "attributes": {
                    "offer": {"name": "Item", "merchantProductId": "SKU1"},
                    "quantity": 1,
                    "basePrice": 1000,
                }
            }
        ],
        store_code="UNIVERSAL",
    )

    assert len(rows) == 1
    assert rows[0]["Плановая дата передачи курьеру"] == "08.03.2026"
