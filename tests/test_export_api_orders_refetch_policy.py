from __future__ import annotations

from types import SimpleNamespace

from scripts import export_api_orders as mod


def _order(code: str, *, buyer: float | None, seller: float | None) -> dict:
    return {
        "id": f"base64-{code}",
        "attributes": {
            "code": code,
            "kaspiDelivery": {
                "customerDeliveryCost": buyer,
                "deliveryCostForSeller": seller,
            },
        },
    }


def _response(data: dict) -> SimpleNamespace:
    return SimpleNamespace(success=True, data=data)


def test_refetch_missing_costs_only_for_orders_with_missing_delivery_fields(monkeypatch) -> None:
    calls: list[str] = []

    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return [
                _order("A1", buyer=100.0, seller=50.0),
                _order("B2", buyer=100.0, seller=None),
            ]

        def get_order_entries_by_id(self, _order_id: str):
            return _response({"data": []})

    monkeypatch.setattr(mod, "KaspiAPIClient", FakeClient)

    def fake_refetch(client, order, verbose=False, force=False):
        del client, verbose, force
        calls.append(order.get("attributes", {}).get("code", ""))
        return order

    monkeypatch.setattr(mod, "_maybe_refetch_order_details", fake_refetch)
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
        refetch_missing_costs=True,
    )

    assert {row["№ заказа"] for row in rows} == {"A1", "B2"}
    assert calls == ["B2"]


def test_export_uses_order_id_entries_endpoint_when_available(monkeypatch) -> None:
    by_id_calls: list[str] = []
    by_code_calls: list[str] = []

    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return [_order("A1", buyer=100.0, seller=50.0)]

        def get_order_entries_by_id(self, order_id: str):
            by_id_calls.append(order_id)
            return _response({"data": []})

        def get_order_entries(self, order_code: str):
            by_code_calls.append(order_code)
            return _response({"data": []})

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
        refetch_missing_costs=False,
    )

    assert len(rows) == 1
    assert by_id_calls == ["base64-A1"]
    assert by_code_calls == []
