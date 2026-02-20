from pathlib import Path

import openpyxl

from scripts.validate_sales_against_workbook import parse_workbook_daily_totals


def _write_workbook(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_parse_workbook_daily_totals_handles_ru_headers_and_text_ids(tmp_path: Path) -> None:
    workbook = tmp_path / "crm_ru.xlsx"
    _write_workbook(
        workbook,
        headers=[
            "\u2116 заказа",
            "Дата поступления заказа",
            "Название товара в Kaspi Магазине",
            "Количество",
            "Total_price",
            "Total_net_rev",
            "STORE_NAME",
        ],
        rows=[
            ["000123", "2026-02-05", "SKU A", 2, 12000, 10000, "ACMEWEAR"],
            ["000124", "2026-02-05", "SKU B", 3, 18000, 15000, "ACMEWEAR"],
            ["000125", "2026-02-06", "SKU C", 1, 7000, 5600, "ACMEWEAR"],
        ],
    )

    daily = parse_workbook_daily_totals(workbook, sheet_name="SALES_KSP_CRM_1")
    assert daily["2026-02-05"]["units"] == 5.0
    assert daily["2026-02-05"]["total_price_kzt"] == 30000.0
    assert daily["2026-02-05"]["net_rev_kzt"] == 25000.0
    assert daily["2026-02-06"]["units"] == 1.0
    assert daily["2026-02-06"]["total_price_kzt"] == 7000.0
    assert daily["2026-02-06"]["net_rev_kzt"] == 5600.0


def test_parse_workbook_daily_totals_handles_en_headers(tmp_path: Path) -> None:
    workbook = tmp_path / "crm_en.xlsx"
    _write_workbook(
        workbook,
        headers=[
            "OrderID",
            "Date",
            "KASPI_OFFER_NAME",
            "Quantity",
            "Total_price",
            "Total_net_rev",
            "STORE_NAME",
        ],
        rows=[
            ["A-1", "2026-02-07", "SKU A", 4, 28000, 24000, "ACMEWEAR"],
            ["A-2", "2026-02-07", "SKU B", 2, 12000, 10000, "ACMEWEAR"],
        ],
    )

    daily = parse_workbook_daily_totals(workbook, sheet_name="SALES_KSP_CRM_1")
    assert daily["2026-02-07"]["units"] == 6.0
    assert daily["2026-02-07"]["total_price_kzt"] == 40000.0
    assert daily["2026-02-07"]["net_rev_kzt"] == 34000.0
