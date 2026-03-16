from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.north_star_workbook_utils import (
    apply_status_bridge,
    load_crm_workbook,
    load_reconciled_workbook,
)


def _write_crm_xlsx(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "Return": None,
                "Date": "05.02.2026",
                "STORE_NAME": "Universal",
                "HEIGHT": None,
                "WEIGHT": None,
                "Quantity": 2,
                "Kaspi_name_core": "Print",
                "OrderID": 123456789,
                "Phone": None,
                "MY_SIZE": "XL",
                "PROBABLE_SIZE": None,
                "KASPI_OFFER_NAME": "Offer A",
                "SKU_key": "SKU_A",
                "SKU_ID": "SKU_A_XL",
                "Sell_price_kzt": 10000,
                "Total_price": 20000,
                "Total_net_rev": 15000,
                "MODEL": "Line52",
                "PLANNED_SHIPPING_DATE": None,
                "Product_Type": "CL",
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Archive_sales", index=False)


def _write_reconciled_xlsx(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "№ заказа": 123456789,
                "Дата поступления заказа": "04.02.2026",
                "Название товара в Kaspi Магазине": None,
                "Название в системе продавца": "Offer A",
                "Артикул": "A",
                "Сумма": "20000",
                "Категория": None,
                "Адрес самовывоза/доставки": None,
                "Дата изменения статуса": "05.02.2026",
                "Статус": "Выдан",
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="sales_daily_sku_size_2024-06-06", index=False)


def test_load_crm_workbook_contract(tmp_path: Path) -> None:
    path = tmp_path / "crm.xlsx"
    _write_crm_xlsx(path)
    out = load_crm_workbook(path)
    assert set(["order_id", "sale_date", "store_code", "sku_key", "units", "net_rev_kzt"]).issubset(
        set(out.columns)
    )
    assert out.iloc[0]["order_id"] == "123456789"
    assert out.iloc[0]["sale_date"] == "2026-02-05"
    assert out.iloc[0]["store_code"] == "UNIVERSAL"


def test_load_reconciled_workbook_contract(tmp_path: Path) -> None:
    path = tmp_path / "reconciled.xlsx"
    _write_reconciled_xlsx(path)
    out = load_reconciled_workbook(path)
    assert set(["order_id", "status_internal", "status_change_date"]).issubset(set(out.columns))
    assert out.iloc[0]["order_id"] == "123456789"
    assert out.iloc[0]["status_internal"] == "DELIVERED"
    assert out.iloc[0]["status_change_date"] == "2026-02-05"


def test_apply_status_bridge_excludes_cancelled(tmp_path: Path) -> None:
    crm_path = tmp_path / "crm.xlsx"
    rec_path = tmp_path / "reconciled.xlsx"
    _write_crm_xlsx(crm_path)
    _write_reconciled_xlsx(rec_path)

    crm_df = load_crm_workbook(crm_path)
    rec_df = load_reconciled_workbook(rec_path)
    rec_df.loc[:, "status_internal"] = "CANCELLED"
    bridged = apply_status_bridge(crm_df, rec_df)
    assert bool(bridged.iloc[0]["bridge_excluded"]) is True


def test_load_reconciled_workbook_maps_russian_statuses(tmp_path: Path) -> None:
    path = tmp_path / "reconciled.xlsx"
    df = pd.DataFrame(
        [
            {"№ заказа": 1, "Дата изменения статуса": "05.02.2026", "Статус": "Завершен"},
            {"№ заказа": 2, "Дата изменения статуса": "05.02.2026", "Статус": "Возвращен"},
            {"№ заказа": 3, "Дата изменения статуса": "05.02.2026", "Статус": "Отменен"},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="sales_daily_sku_size_2024-06-06", index=False)
    out = load_reconciled_workbook(path)
    status_map = dict(zip(out["order_id"], out["status_internal"]))
    assert status_map["1"] == "DELIVERED"
    assert status_map["2"] == "RETURNED"
    assert status_map["3"] == "CANCELLED"


def test_apply_status_bridge_marks_date_source(tmp_path: Path) -> None:
    crm_path = tmp_path / "crm.xlsx"
    rec_path = tmp_path / "reconciled.xlsx"
    _write_crm_xlsx(crm_path)
    _write_reconciled_xlsx(rec_path)
    crm_df = load_crm_workbook(crm_path)
    rec_df = load_reconciled_workbook(rec_path)
    bridged = apply_status_bridge(crm_df, rec_df)
    assert bool(bridged.iloc[0]["bridge_date_verified"]) is True
    assert bridged.iloc[0]["bridge_date_source"] == "reconciled_status_change_date"


def test_load_crm_workbook_schema_drift_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"Date": "05.02.2026"}]).to_excel(
            writer, sheet_name="Archive_sales", index=False
        )
    with pytest.raises(ValueError, match="schema drift"):
        load_crm_workbook(path)
