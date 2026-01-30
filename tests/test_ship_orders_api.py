from datetime import date

import pandas as pd

from scripts.ship_orders_api import read_crm_orders


def _write_crm(tmp_path, rows):
    df = pd.DataFrame(rows)
    path = tmp_path / "crm.xlsx"
    df.to_excel(path, index=False)
    return path


def test_read_crm_orders_includes_missing_size_by_default(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "OrderID": "123",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": date.today(),
                "STORE_NAME": "Store-C",
                "Kaspi_name_core": "PRINT_5V1_BLACK",
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "SKU_ID": "CL_OC_MEN_LINE52_BLACK_L",
                "Quantity": 1,
            }
        ],
    )

    orders = read_crm_orders(crm_path, "Sheet1", date.today())

    assert "123" in orders
    assert orders["123"][0].my_size == ""


def test_read_crm_orders_can_require_size(tmp_path):
    crm_path = _write_crm(
        tmp_path,
        [
            {
                "OrderID": "456",
                "MY_SIZE": "",
                "PLANNED_SHIPPING_DATE": date.today(),
                "STORE_NAME": "AcmeWear",
                "Kaspi_name_core": "LINE51",
                "SKU_key": "CL_NK_MEN_LINE51_WHITE",
                "SKU_ID": "CL_NK_MEN_LINE51_WHITE_L",
                "Quantity": 1,
            }
        ],
    )

    orders = read_crm_orders(crm_path, "Sheet1", date.today(), allow_missing_size=False)

    assert orders == {}
