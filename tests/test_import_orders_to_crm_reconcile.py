from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.import_orders_to_crm import (
    _build_line_dedupe_key,
    _order_to_update_fields,
    build_pending_append_mask,
    plan_append_date_reconcile,
)


@dataclass
class _Row:
    row_num: int
    line_key: str
    my_size: str | None = None


def test_build_pending_append_mask_allows_overdue_pending_when_missing_from_today_view():
    append_date = date(2026, 3, 7)
    df = pd.DataFrame(
        {
            "№ заказа": ["845767451"],
            "Название товара в Kaspi Магазине": ["Принт_5в1_черный"],
            "Артикул": ["LINE52_XL"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["05.03.2026"],
        }
    )

    base_key = _build_line_dedupe_key(
        "845767451",
        date(2026, 3, 5),
        "Принт_5в1_черный",
        "LINE52_XL",
        1,
    )

    _work, new_mask, stats = build_pending_append_mask(
        df,
        colmap={
            "order_id": "№ заказа",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
            "handover": "Плановая дата передачи курьеру",
        },
        existing_keys={base_key},
        existing_append_date_keys=set(),
        include_overdue=True,
        append_date=append_date,
    )

    assert new_mask.tolist() == [True]
    assert stats["dedupe_mode"] == "append_date_view"
    assert stats["carryforward_rows_to_append"] == 1


def test_build_pending_append_mask_blocks_overdue_pending_already_present_today():
    append_date = date(2026, 3, 7)
    df = pd.DataFrame(
        {
            "№ заказа": ["845767451"],
            "Название товара в Kaspi Магазине": ["Принт_5в1_черный"],
            "Артикул": ["LINE52_XL"],
            "Количество": [1],
            "Плановая дата передачи курьеру": ["05.03.2026"],
        }
    )

    base_key = _build_line_dedupe_key(
        "845767451",
        date(2026, 3, 5),
        "Принт_5в1_черный",
        "LINE52_XL",
        1,
    )

    _work, new_mask, stats = build_pending_append_mask(
        df,
        colmap={
            "order_id": "№ заказа",
            "offer_name": "Название товара в Kaspi Магазине",
            "sku": "Артикул",
            "quantity": "Количество",
            "handover": "Плановая дата передачи курьеру",
        },
        existing_keys={base_key},
        existing_append_date_keys={base_key},
        include_overdue=True,
        append_date=append_date,
    )

    assert new_mask.tolist() == [False]
    assert stats["duplicates_skipped"] == 1
    assert stats["carryforward_rows_to_append"] == 0


def test_plan_append_date_reconcile_drops_stale_today_rows_and_appends_missing():
    key_keep = _build_line_dedupe_key("1001", date(2026, 3, 7), "Item A", "SKU-A", 1)
    key_drop = _build_line_dedupe_key("1002", date(2026, 3, 6), "Item B", "SKU-B", 1)
    key_add = _build_line_dedupe_key("1003", date(2026, 3, 6), "Item C", "SKU-C", 1)

    plan = plan_append_date_reconcile(
        existing_rows=[
            _Row(row_num=20, line_key=key_keep, my_size="L"),
            _Row(row_num=21, line_key=key_drop, my_size="XL"),
        ],
        desired_keys=[key_keep, key_add],
    )

    assert plan.delete_row_numbers == [21]
    assert plan.keep_keys == {key_keep}
    assert plan.missing_keys == [key_add]


def test_plan_append_date_reconcile_keeps_row_with_manual_size_when_duplicate_exists():
    key_dup = _build_line_dedupe_key("1001", date(2026, 3, 7), "Item A", "SKU-A", 1)

    plan = plan_append_date_reconcile(
        existing_rows=[
            _Row(row_num=20, line_key=key_dup, my_size=""),
            _Row(row_num=21, line_key=key_dup, my_size="XL"),
        ],
        desired_keys=[key_dup],
    )

    assert plan.delete_row_numbers == [20]
    assert plan.keep_rows_by_key[key_dup].row_num == 21


def test_order_to_update_fields_uses_raw_courier_planning_date():
    order = {
        "attributes": {
            "state": "KASPI_DELIVERY",
            "status": "ACCEPTED_BY_MERCHANT",
            "creationDate": 1772877981264,  # 2026-03-07 15:06:21 +05:00
            "kaspiDelivery": {
                "courierTransmissionPlanningDate": 1772982000000,  # 2026-03-08 20:00:00 +05:00
                "plannedDeliveryDate": 1773230400000,
            },
        }
    }

    fields = _order_to_update_fields(order)

    assert fields["Плановая дата передачи курьеру"] == "08.03.2026"
