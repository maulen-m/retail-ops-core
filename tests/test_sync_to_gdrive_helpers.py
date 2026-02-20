import pytest

pytest.importorskip("xlwings")

from datetime import date

from scripts.sync_to_gdrive import (
    clean_order_id,
    parse_excel_date,
    resolve_target_date,
    find_header_index,
)


def test_clean_order_id():
    assert clean_order_id(123.0) == "123"
    assert clean_order_id(" 000123 ") == "000123"
    assert clean_order_id(None) == ""


def test_parse_excel_date_serial():
    assert parse_excel_date(1) == date(1899, 12, 31)
    assert parse_excel_date(2.0) == date(1900, 1, 1)


def test_parse_excel_date_string():
    assert parse_excel_date("2026-01-07") == date(2026, 1, 7)


def test_resolve_target_date():
    assert resolve_target_date("2026-01-07") == date(2026, 1, 7)


def test_find_header_index():
    headers = ["A", "OrderID", "Статус", "Плановая дата передачи курьеру"]
    assert find_header_index(headers, ("OrderID", "№ заказа")) == 1
    assert find_header_index(headers, ("Статус",)) == 2
    assert find_header_index(headers, ("Missing",)) is None
