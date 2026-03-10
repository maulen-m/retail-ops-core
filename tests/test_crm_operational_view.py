from datetime import date

import pandas as pd

from core.ops.crm_operational_view import select_operational_crm_rows


def test_select_operational_crm_rows_prefers_today_rows_for_carry_forward_duplicates():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-06",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-07",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-08",
                "OrderID": "846479842",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "L",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_700546788 черный М",
                "Quantity": 1,
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 8),
        order_id_filter={"846479842"},
    )

    assert len(resolved) == 1
    assert resolved.iloc[0]["_order_id"] == "846479842"
    assert resolved.iloc[0]["_batch_date"] == date(2026, 3, 8)
    assert stats["historical_rows_dropped"] == 2
    assert stats["selected_today_orders"] == 1


def test_select_operational_crm_rows_falls_back_to_latest_prior_row():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-06",
                "OrderID": "845867376",
                "STORE_NAME": "Universal",
                "MY_SIZE": "XL",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард однотонный 18209877_863780079 черный XL",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-07",
                "OrderID": "845867376",
                "STORE_NAME": "Universal",
                "MY_SIZE": "XL",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард однотонный 18209877_863780079 черный XL",
                "Quantity": 1,
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 8),
        order_id_filter={"845867376"},
    )

    assert len(resolved) == 1
    assert resolved.iloc[0]["_batch_date"] == date(2026, 3, 7)
    assert stats["selected_fallback_orders"] == 1


def test_select_operational_crm_rows_keeps_distinct_same_day_lines():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-08",
                "OrderID": "848253366",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "3XL",
                "Kaspi_name_core": "Трусы_черные",
                "KASPI_OFFER_NAME": "Тайтсы PRO COMBAT 17 черный 3XL",
                "Quantity": 1,
                "SKU_ID": "SKU-3XL",
            },
            {
                "Date": "2026-03-08",
                "OrderID": "848253366",
                "STORE_NAME": "STORE-B",
                "MY_SIZE": "2XL",
                "Kaspi_name_core": "Трусы_черные",
                "KASPI_OFFER_NAME": "Тайтсы PRO COMBAT 17 черный XL",
                "Quantity": 1,
                "SKU_ID": "SKU-2XL",
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 8),
        order_id_filter={"848253366"},
    )

    assert len(resolved) == 2
    assert set(resolved["MY_SIZE"]) == {"2XL", "3XL"}
    assert stats["same_day_line_duplicates_dropped"] == 0


def test_select_operational_crm_rows_can_require_current_batch_date():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "849921993",
                "STORE_NAME": "AcmeWear",
                "MY_SIZE": "4XL",
                "Kaspi_name_core": "Line51",
                "KASPI_OFFER_NAME": "Спортивный костюм ACMEWEAR AcmeWear 05 черный, белый 4XL",
                "Quantity": 1,
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850902537",
                "STORE_NAME": "Universal",
                "MY_SIZE": "XL",
                "Kaspi_name_core": "Футболка_черная",
                "KASPI_OFFER_NAME": "Рашгард 30260620_662528941 черный 2XL",
                "Quantity": 1,
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 10),
        allow_historical_fallback=False,
    )

    assert list(resolved["_order_id"]) == ["850902537"]
    assert stats["selected_today_orders"] == 1
    assert stats["selected_fallback_orders"] == 0


def test_select_operational_crm_rows_can_backfill_blank_overdue_size_from_latest_prior_row():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "M",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "SKU_ID": "SKU-TOP",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-09",
                "SKU_ID": "SKU-TOP",
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 10),
        order_id_filter={"850084962"},
        allow_historical_fallback=False,
        backfill_overdue_my_size_from_history=True,
    )

    assert len(resolved) == 1
    assert resolved.iloc[0]["_batch_date"] == date(2026, 3, 10)
    assert resolved.iloc[0]["MY_SIZE"] == "M"
    assert bool(resolved.iloc[0]["_my_size_backfilled"]) is True
    assert stats["overdue_my_size_backfilled_rows"] == 1


def test_select_operational_crm_rows_does_not_backfill_same_day_blank_size():
    df = pd.DataFrame(
        [
            {
                "Date": "2026-03-09",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "M",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "SKU_ID": "SKU-TOP",
            },
            {
                "Date": "2026-03-10",
                "OrderID": "850084962",
                "STORE_NAME": "Universal",
                "MY_SIZE": "",
                "Kaspi_name_core": "Длинный_рашгард_Белый",
                "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
                "Quantity": 1,
                "PLANNED_SHIPPING_DATE": "2026-03-10",
                "SKU_ID": "SKU-TOP",
            },
        ]
    )

    resolved, stats = select_operational_crm_rows(
        df,
        target_date=date(2026, 3, 10),
        order_id_filter={"850084962"},
        allow_historical_fallback=False,
        backfill_overdue_my_size_from_history=True,
    )

    assert len(resolved) == 1
    assert resolved.iloc[0]["MY_SIZE"] == ""
    assert bool(resolved.iloc[0]["_my_size_backfilled"]) is False
    assert stats["overdue_my_size_backfilled_rows"] == 0
