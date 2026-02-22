from __future__ import annotations

from types import SimpleNamespace

import scripts.validate_kaspi_api as validate_mod


def _resp(success: bool, data: dict | None = None, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(success=success, data=data or {}, error=error)


def test_validate_assemble_order_fails_when_state_transition_not_confirmed(monkeypatch) -> None:
    class FakeClient:
        writes_enabled = True

        def __init__(self, store_code: str):
            self.store_code = store_code

        def get_pending_assembly_orders(self):
            return _resp(True, {"data": [{"attributes": {"code": "ORDER-1"}}]})

        def assemble_order(self, order_code: str):
            return _resp(True, {"ok": True})

        def get_order(self, order_code: str):
            return _resp(True, {"attributes": {"code": order_code, "assembled": False}})

        def get_waybill_url(self, order_payload):
            return None

    monkeypatch.setattr(validate_mod, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(validate_mod.time, "sleep", lambda _seconds: None)

    assert validate_mod.validate_assemble_order("UNIVERSAL") is False


def test_validate_assemble_order_passes_when_state_transition_confirmed(monkeypatch) -> None:
    class FakeClient:
        writes_enabled = True

        def __init__(self, store_code: str):
            self.store_code = store_code

        def get_pending_assembly_orders(self):
            return _resp(True, {"data": [{"attributes": {"code": "ORDER-1"}}]})

        def assemble_order(self, order_code: str):
            return _resp(True, {"ok": True})

        def get_order(self, order_code: str):
            return _resp(
                True,
                {"attributes": {"code": order_code, "assembled": True, "kaspiDelivery": {"waybill": None}}},
            )

        def get_waybill_url(self, order_payload):
            return None

    monkeypatch.setattr(validate_mod, "KaspiAPIClient", FakeClient)
    monkeypatch.setattr(validate_mod.time, "sleep", lambda _seconds: None)

    assert validate_mod.validate_assemble_order("UNIVERSAL") is True
