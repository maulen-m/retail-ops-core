from datetime import date

import pandas as pd

from scripts.restore_my_size_from_backup import build_row_key, compute_restore_updates


def test_build_row_key_is_line_stable():
    row_a = {
        "№ заказа": "812315649",
        "Date": date(2026, 2, 7),
        "Артикул": "CL_OC_MEN_LINE52_BLACK_103217238_56-58/56, 58_(4XL)",
        "Название товара в Kaspi Магазине": "Комплект Antec RASH-921 Рашгард 5 в 1 черный 56, 58",
        "Количество": 1,
    }
    row_b = {
        "№ заказа": "812315649",
        "Date": date(2026, 2, 7),
        "Артикул": "CL_OC_MEN_LINE52_BLACK_L_116515378",
        "Название товара в Kaspi Магазине": "Спортивный костюм PRO COMBAT 528742263 черный M",
        "Количество": 1,
    }
    assert build_row_key(row_a) != build_row_key(row_b)


def test_compute_restore_updates_strict_overwrites():
    source = pd.DataFrame(
        [
            {
                "№ заказа": "812500001",
                "Date": date(2026, 2, 7),
                "Артикул": "OF_SUIT-61_BLK_3XL",
                "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR ... 3XL",
                "Количество": 1,
                "MY_SIZE": "3XL",
            }
        ]
    )
    target = pd.DataFrame(
        [
            {
                "№ заказа": "812500001",
                "Date": date(2026, 2, 7),
                "Артикул": "OF_SUIT-61_BLK_3XL",
                "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR ... 3XL",
                "Количество": 1,
                "MY_SIZE": "M",
            }
        ]
    )

    updates, stats = compute_restore_updates(source, target, mode="strict")
    assert len(updates) == 1
    assert updates[0]["new_my_size"] == "3XL"
    assert stats["matched_rows"] == 1
    assert stats["updated_rows"] == 1


def test_compute_restore_updates_fill_missing_only():
    source = pd.DataFrame(
        [
            {
                "№ заказа": "812500002",
                "Date": date(2026, 2, 7),
                "Артикул": "OF_SUIT-61_BLK_XL_48",
                "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR ... 48",
                "Количество": 1,
                "MY_SIZE": "XL",
            }
        ]
    )
    target = pd.DataFrame(
        [
            {
                "№ заказа": "812500002",
                "Date": date(2026, 2, 7),
                "Артикул": "OF_SUIT-61_BLK_XL_48",
                "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR ... 48",
                "Количество": 1,
                "MY_SIZE": "L",
            }
        ]
    )
    updates, stats = compute_restore_updates(source, target, mode="fill-missing")
    assert len(updates) == 0
    assert stats["matched_rows"] == 1
    assert stats["updated_rows"] == 0
