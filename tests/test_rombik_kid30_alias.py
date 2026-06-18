from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from core.ingest.sales_ingest import parse_sales_excel
from core.product_truth.rombik_kid30_alias import apply_rombik_kid30_alias


def test_rombik_kid30_alias_is_future_only_and_product_code_scoped() -> None:
    before = apply_rombik_kid30_alias(
        sku_key="CL_NEW-CLO_KID_ROMBIK_BLACK",
        sku_id="CL_NEW-CLO_KID_ROMBIK_BLACK_S_135222379",
        my_size="S",
        event_at=datetime(2026, 6, 3, 10, 0, 0),
    )
    assert before == {
        "sku_key": "CL_NEW-CLO_KID_ROMBIK_BLACK",
        "sku_id": "CL_NEW-CLO_KID_ROMBIK_BLACK_S_135222379",
        "my_size": "S",
    }

    after = apply_rombik_kid30_alias(
        sku_key="CL_NEW-CLO_KID_ROMBIK_BLACK",
        sku_id="CL_NEW-CLO_KID_ROMBIK_BLACK_S_128541983",
        my_size="S",
        event_at=datetime(2026, 6, 3, 10, 30, 0),
    )
    assert after == {
        "sku_key": "CL_NEW-CLO_KID_ROMBIK_BLACK",
        "sku_id": "CL_NEW-CLO_KID_ROMBIK_BLACK_30",
        "my_size": "30",
    }

    neighbor = apply_rombik_kid30_alias(
        sku_key="CL_NEW-CLO_KID_ROMBIK_BLACK",
        sku_id="CL_NEW-CLO_KID_ROMBIK_BLACK_S_143893497",
        my_size="S",
        event_at=datetime(2026, 6, 3, 10, 30, 0),
    )
    assert neighbor["sku_id"] == "CL_NEW-CLO_KID_ROMBIK_BLACK_S_143893497"
    assert neighbor["my_size"] == "S"


def test_sales_excel_import_applies_rombik_kid30_alias_after_effective_timestamp(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "OrderID": ["ORD-AFTER", "ORD-BEFORE", "ORD-NEIGHBOR"],
            "Date": [
                datetime(2026, 6, 3, 10, 30, 0),
                datetime(2026, 6, 3, 10, 0, 0),
                datetime(2026, 6, 3, 10, 30, 0),
            ],
            "KASPI_OFFER_NAME": [
                "Рашгард 5 в 1 черный 158",
                "Рашгард 5 в 1 черный 152",
                "Рашгард 5 в 1 черный 164",
            ],
            "Kaspi_article": [
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_128541983",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_135222379",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_143893497",
            ],
            "SKU_ID": [
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_128541983",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_135222379",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S_143893497",
            ],
            "SKU_key": [
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
            ],
            "MY_SIZE": ["S", "S", "S"],
            "Quantity": [1, 1, 1],
            "Sell_price_kzt": [14990, 14990, 14990],
            "STORE_NAME": ["Universal", "Universal", "Universal"],
        }
    )
    xlsx_path = tmp_path / "rombik_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

    rows = {row["order_id"]: row for row in parse_sales_excel(str(xlsx_path))}

    assert rows["ORD-AFTER"]["sku_id"] == "CL_NEW-CLO_KID_ROMBIK_BLACK_30"
    assert rows["ORD-AFTER"]["my_size"] == "30"
    assert rows["ORD-AFTER"]["order_date"] == date(2026, 6, 3)

    assert rows["ORD-BEFORE"]["sku_id"] == "CL_NEW-CLO_KID_ROMBIK_BLACK_S_135222379"
    assert rows["ORD-BEFORE"]["my_size"] == "S"

    assert rows["ORD-NEIGHBOR"]["sku_id"] == "CL_NEW-CLO_KID_ROMBIK_BLACK_S_143893497"
    assert rows["ORD-NEIGHBOR"]["my_size"] == "S"
