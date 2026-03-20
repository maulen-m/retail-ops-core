from __future__ import annotations

from datetime import date

from scripts.backfill_crm_archive_period import (
    DbPatch,
    _build_db_patch_from_row,
    normalize_order_id,
    parse_date_any,
    update_archive_rows,
)


def test_normalize_order_id_digits_only() -> None:
    assert normalize_order_id("  838091970.0 ") == "838091970"
    assert normalize_order_id("OD-838-091-970") == "838091970"
    assert normalize_order_id(None) == ""


def test_parse_date_any_common_formats() -> None:
    assert parse_date_any("2026-03-03") == date(2026, 3, 3)
    assert parse_date_any("2026-03-03 12:01:59") == date(2026, 3, 3)
    assert parse_date_any("03.03.2026") == date(2026, 3, 3)


def test_build_db_patch_from_row_archive_status() -> None:
    patch = _build_db_patch_from_row(
        {
            "kaspi_status": "ARCHIVE",
            "kaspi_status_detail": "ARCHIVE",
            "status_updated_at": "2026-03-03 15:00:00",
            "courier_transmission_planning_date": "2026-03-02",
            "planned_shipment_date": "2026-03-02",
            "courier_transmission_date": "2026-03-02",
            "delivery_cost_for_seller": "783",
        }
    )
    assert patch.status == "Завершен"
    assert patch.issued_flag in {"", "Да"}
    assert patch.status_change_date == "03.03.2026"
    assert patch.planned_handover_date == "02.03.2026"
    assert patch.seller_fee == "783"


def test_update_archive_rows_prefers_crm_send_date_and_patches_missing() -> None:
    rows = [
        {
            "№ заказа": "838091970",
            "Дата поступления заказа": "28.02.2026",
            "Статус": "",
            "Выдал": "",
            "Дата изменения статуса": "",
            "Плановая дата передачи курьеру": "",
            "Стоимость доставки для продавца": "0",
        }
    ]
    updated_rows, stats = update_archive_rows(
        rows=rows,
        date_from=date(2026, 2, 28),
        date_to=date(2026, 3, 3),
        target_order_ids={"838091970"},
        crm_patch_map={
            "838091970": {
                "status": "Ожидает передачи курьеру",
                "issued_flag": "",
                "status_change_date": "28.02.2026",
                "planned_handover_date": "28.02.2026",
                "seller_fee": "783",
            }
        },
        db_patches={
            "838091970": DbPatch(
                status="Ожидает передачи курьеру",
                issued_flag="",
                status_change_date="28.02.2026",
                planned_handover_date="28.02.2026",
                seller_fee="783",
            )
        },
        crm_send_dates={"838091970": {date(2026, 2, 28)}},
        truth_send_dates={"838091970": "27.02.2026"},
    )

    row = updated_rows[0]
    assert row["Статус"] == "Ожидает передачи курьеру"
    assert row["Дата изменения статуса"] == "28.02.2026"
    assert row["Плановая дата передачи курьеру"] == "28.02.2026"
    assert row["Стоимость доставки для продавца"] == "783"
    assert row["send_date"] == "28.02.2026"
    assert stats["send_date_from_crm"] == 1
