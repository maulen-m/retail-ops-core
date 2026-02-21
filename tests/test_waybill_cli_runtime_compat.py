from __future__ import annotations

import sys

from core.integrations.kaspi_api_client import APIResponse, KaspiAPIClient
from scripts import download_waybills_api
from scripts import ship_orders_api


def test_list_all_orders_accepts_include_orders_passthrough() -> None:
    captured: dict[str, object] = {}

    client = KaspiAPIClient.__new__(KaspiAPIClient)

    def _fake_list_orders(**kwargs):
        captured.update(kwargs)
        return APIResponse(success=True, data={"data": []}, status_code=200)

    client.list_orders = _fake_list_orders  # type: ignore[attr-defined]

    rows = KaspiAPIClient.list_all_orders(  # type: ignore[misc]
        client,
        state="KASPI_DELIVERY",
        since="2026-02-17",
        include_orders="entries",
    )

    assert rows == []
    assert captured.get("include_orders") == "entries"


def test_list_all_orders_accepts_delivery_type_passthrough() -> None:
    captured: dict[str, object] = {}

    client = KaspiAPIClient.__new__(KaspiAPIClient)

    def _fake_list_orders(**kwargs):
        captured.update(kwargs)
        return APIResponse(success=True, data={"data": []}, status_code=200)

    client.list_orders = _fake_list_orders  # type: ignore[attr-defined]

    rows = KaspiAPIClient.list_all_orders(  # type: ignore[misc]
        client,
        state="KASPI_DELIVERY",
        since="2026-02-17",
        delivery_type="PICKUP",
    )

    assert rows == []
    assert captured.get("delivery_type") == "PICKUP"


def test_get_order_by_id_calls_orders_endpoint() -> None:
    captured: dict[str, object] = {}

    client = KaspiAPIClient.__new__(KaspiAPIClient)

    def _fake_request(method, endpoint, params=None, json_data=None, timeout=None):
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["params"] = params
        return APIResponse(success=True, data={"id": "ODI5MzM2NTk0"}, status_code=200)

    client._request = _fake_request  # type: ignore[attr-defined]

    response = KaspiAPIClient.get_order_by_id(client, "ODI5MzM2NTk0")  # type: ignore[misc]

    assert response.success is True
    assert captured["method"] == "GET"
    assert captured["endpoint"] == "orders/ODI5MzM2NTk0"
    assert captured["params"] is None


def test_download_waybills_cli_accepts_include_overdue(monkeypatch) -> None:
    monkeypatch.setattr(
        download_waybills_api,
        "download_all_waybills",
        lambda **_: {
            "downloaded": 0,
            "already_exists": 0,
            "missing_waybill": 0,
            "invalid_pdf": 0,
            "skipped_not_target": 0,
            "errors": [],
            "selection_status": "OK",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_waybills_api.py",
            "--include-overdue",
            "--dry-run",
            "--date",
            "2026-02-20",
        ],
    )

    download_waybills_api.main()


def test_ship_orders_cli_accepts_store-c_store(monkeypatch) -> None:
    monkeypatch.setattr(ship_orders_api, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        ship_orders_api,
        "get_pending_assembly_orders",
        lambda **_: ({}, {}, {}, {}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ship_orders_api.py",
            "--store",
            "Store-C",
            "--dry-run",
            "--date",
            "2026-02-20",
        ],
    )

    ship_orders_api.main()
