from __future__ import annotations

from datetime import date

from scripts import export_api_orders as export_mod
from scripts import ship_orders_api as ship_mod


def _pending_order(order_code: str, planned: date) -> dict:
    return {
        "id": f"base64-{order_code}",
        "attributes": {
            "code": order_code,
            "assembled": False,
            "status": "ACCEPTED_BY_MERCHANT",
            "kaspiDelivery": {
                "courierTransmissionPlanningDate": int(planned.strftime("%s")) * 1000,
            },
        },
    }


def test_store_scoped_pending_fetch_matches_full_fetch_for_selected_store(monkeypatch) -> None:
    target_date = date(2026, 2, 24)
    store_payloads = {
        "UNIVERSAL": [_pending_order("U-1", target_date)],
        "ACMEWEAR": [_pending_order("O-1", target_date)],
        "STOREB": [_pending_order("M-1", target_date)],
    }

    class FakeClient:
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
            del state, status, since, until, page_size, delivery_type, signature_required, include_orders
            if page_number > 0:
                return ship_mod.APIResponse(success=True, data={"data": [], "meta": {"pageCount": 1}}, status_code=200)
            return ship_mod.APIResponse(
                success=True,
                data={"data": store_payloads.get(self.store_code, []), "meta": {"pageCount": 1}},
                status_code=200,
            )

    monkeypatch.setattr(ship_mod, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(ship_mod, "STORE_TOKEN_MAP", {"UNIVERSAL": "x", "ACMEWEAR": "y", "STOREB": "z"})

    full_pending, _, _, _ = ship_mod.get_pending_assembly_orders(
        target_date=target_date,
        since_days=3,
        store_codes=None,
    )
    scoped_pending, _, _, _ = ship_mod.get_pending_assembly_orders(
        target_date=target_date,
        since_days=3,
        store_codes={"UNIVERSAL"},
    )

    assert scoped_pending["UNIVERSAL"] == full_pending["UNIVERSAL"]


def test_selective_refetch_preserves_export_rows_vs_force_refetch_baseline(monkeypatch) -> None:
    orders = [
        {
            "id": "base64-A1",
            "attributes": {"code": "A1", "kaspiDelivery": {"customerDeliveryCost": 100, "deliveryCostForSeller": 50}},
        },
        {
            "id": "base64-B2",
            "attributes": {"code": "B2", "kaspiDelivery": {"customerDeliveryCost": 100, "deliveryCostForSeller": None}},
        },
    ]

    class FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return list(orders)

        def get_order_entries_by_id(self, _order_id: str):
            return type("Resp", (), {"success": True, "data": {"data": []}})()

    monkeypatch.setattr(export_mod, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(
        export_mod,
        "order_to_rows",
        lambda order, entries, store_code, client=None: [{"code": order["attributes"]["code"], "entries": len(entries)}],
    )
    monkeypatch.setattr(
        export_mod,
        "_maybe_refetch_order_details",
        lambda client, order, verbose=False, force=False: order,
    )

    selective = export_mod.export_store_orders(
        store_code="UNIVERSAL",
        include_archive=False,
        refetch_missing_costs=True,
    )

    original_predicate = export_mod._order_missing_delivery_costs
    monkeypatch.setattr(export_mod, "_order_missing_delivery_costs", lambda _order: True)
    force_like_baseline = export_mod.export_store_orders(
        store_code="UNIVERSAL",
        include_archive=False,
        refetch_missing_costs=True,
    )
    monkeypatch.setattr(export_mod, "_order_missing_delivery_costs", original_predicate)

    assert selective == force_like_baseline
