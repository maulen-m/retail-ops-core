from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import waybill_handover_check as handover_mod


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _ms(year: int, month: int, day: int, hour: int = 20) -> int:
    return int(datetime(year, month, day, hour, 0, tzinfo=ALMATY_TZ).timestamp() * 1000)


def _kaspi_delivery_order(
    order_id: str,
    *,
    planned_ms: int,
    assembled: bool = True,
    courier_transmission_ms: int | None = None,
) -> dict:
    delivery = {
        "courierTransmissionPlanningDate": planned_ms,
        "waybill": f"https://kaspi.example/{order_id}.pdf",
    }
    if courier_transmission_ms is not None:
        delivery["courierTransmissionDate"] = courier_transmission_ms
    return {
        "id": f"base64-{order_id}",
        "attributes": {
            "code": order_id,
            "state": "KASPI_DELIVERY",
            "status": "ACCEPTED_BY_MERCHANT",
            "assembled": assembled,
            "kaspiDelivery": delivery,
        },
    }


def _write_telegram_ledger(root: Path, *, order_id: str, filename: str, message_id: str) -> Path:
    batch_root = root / "excel_ui" / "Kaspi_orders" / "Today" / "MERGED" / "SEND" / "07.05.26_MERGED_qnt72"
    batch_root.mkdir(parents=True)
    ledger_path = batch_root / "telegram_send_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_label": "07.05.26_MERGED_qnt72",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "filename": filename,
                        "order_ids": [order_id],
                        "telegram_message_id": message_id,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ledger_path


def test_handover_report_flags_assembled_orders_without_courier_transmission(tmp_path: Path):
    _write_telegram_ledger(
        tmp_path,
        order_id="914180723",
        filename="6в1_Черный_+Сумка_2XL-2.pdf",
        message_id="632",
    )

    report = handover_mod.build_handover_report_from_orders(
        target_date=date(2026, 5, 7),
        store_orders_by_code={
            "ACMEWEAR": [
                _kaspi_delivery_order("914180723", planned_ms=_ms(2026, 5, 7)),
                _kaspi_delivery_order(
                    "914180724",
                    planned_ms=_ms(2026, 5, 7),
                    courier_transmission_ms=_ms(2026, 5, 7, 18),
                ),
            ],
            "UNIVERSAL": [
                _kaspi_delivery_order("913542227", planned_ms=_ms(2026, 5, 6)),
            ],
        },
        ledger_roots=[tmp_path],
        lookback_days=3,
        now=datetime(2026, 5, 7, 18, 40, tzinfo=ALMATY_TZ),
    )

    assert report["ok"] is False
    assert report["status"] == "PHYSICAL_HANDOVER_PENDING"
    assert report["pending_count"] == 2
    assert report["by_store"] == {"AcmeWear": 1, "Universal": 1}
    assert report["pending_orders"][0]["order_id"] == "913542227"
    assert report["pending_orders"][1]["order_id"] == "914180723"
    assert report["pending_orders"][1]["telegram_state"] == "confirmed"
    assert report["pending_orders"][1]["telegram_message_id"] == "632"
    assert report["pending_orders"][1]["telegram_filename"] == "6в1_Черный_+Сумка_2XL-2.pdf"

    message = handover_mod.format_handover_status_message(report)
    assert "PHYSICAL_HANDOVER_PENDING" in message
    assert "914180723" in message
    assert "913542227" in message
    assert "632" in message


def test_handover_compact_message_summarizes_large_pending_list(tmp_path: Path):
    pending_orders = [
        {
            "store": "STORE-B",
            "planned_date": "2026-05-07",
            "delay_days": "1",
            "order_id": "913810395",
            "telegram_state": "confirmed",
            "telegram_message_id": "668",
        },
        {
            "store": "AcmeWear",
            "planned_date": "2026-05-07",
            "delay_days": "1",
            "order_id": "914180723",
            "telegram_state": "confirmed",
            "telegram_message_id": "661",
        },
    ]
    pending_orders.extend(
        {
            "store": "Universal",
            "planned_date": "2026-05-08",
            "delay_days": "0",
            "order_id": str(915000000 + index),
            "telegram_state": "confirmed",
            "telegram_message_id": str(700 + index),
        }
        for index in range(30)
    )
    report = {
        "ok": False,
        "status": "PHYSICAL_HANDOVER_PENDING",
        "target_date": "2026-05-08",
        "as_of": "2026-05-08T18:07:49+05:00",
        "pending_count": len(pending_orders),
        "by_store": {"STORE-B": 1, "AcmeWear": 1, "Universal": 30},
        "pending_orders": pending_orders,
        "api_errors": {},
    }

    message = handover_mod.format_handover_compact_status_message(report)

    assert "Передача: НЕ ЗАКРЫТО" in message
    assert "pending: <code>32</code>" in message
    assert "overdue: <code>2</code>" in message
    assert "STORE-B: <code>1</code>" in message
    assert "Universal: <code>30</code>" in message
    assert "913810395" in message
    assert "914180723" in message
    assert "915000000" not in message
    assert "/hfull" in message
    assert "+-" not in message
    assert len(message) < 900


def test_handover_report_green_when_all_expected_orders_have_courier_transmission(tmp_path: Path):
    report = handover_mod.build_handover_report_from_orders(
        target_date=date(2026, 5, 7),
        store_orders_by_code={
            "STOREB": [
                _kaspi_delivery_order(
                    "914313118",
                    planned_ms=_ms(2026, 5, 7),
                    courier_transmission_ms=_ms(2026, 5, 7, 18),
                )
            ]
        },
        ledger_roots=[tmp_path],
        lookback_days=3,
        now=datetime(2026, 5, 7, 18, 40, tzinfo=ALMATY_TZ),
    )

    assert report["ok"] is True
    assert report["status"] == "PHYSICAL_HANDOVER_COMPLETE"
    assert report["pending_count"] == 0
    assert "PHYSICAL_HANDOVER_COMPLETE" in handover_mod.format_handover_status_message(report)
