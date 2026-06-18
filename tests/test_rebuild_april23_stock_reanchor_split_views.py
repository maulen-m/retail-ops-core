from __future__ import annotations

from datetime import date

import pandas as pd

from scripts.rebuild_april23_stock_reanchor_split_views import (
    LINE51_SKU,
    LINE61_SKU,
    build_status_change_sales_ledger_from_frames,
    build_stock_views,
    map_target_family,
)


def test_map_target_family_normalizes_parent_and_child_variants() -> None:
    suit = map_target_family(
        {
            "article": "CL_NEW-CLO2_MEN_SUIT-61_BLACK_K-O_XL_2_156408385",
            "seller_system_name": "Спортивный_костюм_ACMEWEAR_SUIT-61_K-O_черный",
        },
        prefer_size_fields=("article",),
    )
    assert suit is not None
    assert suit.sku_key == LINE61_SKU
    assert suit.my_size == "XL"
    assert suit.sku_id == f"{LINE61_SKU}_XL"

    beli_child = map_target_family(
        {
            "SKU_key": "LINE-31-TS",
            "MY_SIZE": "3XL",
            "KASPI_OFFER_NAME": "Спортивный костюм ACMEWEAR LINE-31-TS-ST-3XL-54 черный, белый 3XL",
        },
        prefer_size_fields=("MY_SIZE",),
    )
    assert beli_child is not None
    assert beli_child.sku_key == LINE51_SKU
    assert beli_child.my_size == "3XL"
    assert beli_child.child_bundle_flag is True
    assert "CHILD_BUNDLE_COMPONENT_STOCK_SPLIT_NOT_PROVEN" in beli_child.mapping_blocker


def test_status_change_ledger_uses_status_change_not_order_intake_for_sale_date() -> None:
    frame = pd.DataFrame(
        [
            {
                "_source_pack": "live_all_enabled_20260505_to_20260525",
                "_source_priority": 0,
                "_source_path": "/tmp/live.csv",
                "_source_sha256": "abc",
                "store_code": "ACMEWEAR",
                "order_id": "O1",
                "created_at": "2026-04-24",
                "status_change_at": "2026-05-05",
                "status_internal": "DELIVERED",
                "status_raw": "Выдан",
                "quantity": "2",
                "net_rev_kzt": "1000",
                "article": "CL_NEW-CLO2_MEN_SUIT-61_BLACK_K-O_2XL_156399703",
            },
            {
                "_source_pack": "live_all_enabled_20260505_to_20260525",
                "_source_priority": 0,
                "_source_path": "/tmp/live.csv",
                "_source_sha256": "abc",
                "store_code": "ACMEWEAR",
                "order_id": "O2",
                "created_at": "2026-04-24",
                "status_change_at": "2026-05-06",
                "status_internal": "RETURNED",
                "status_raw": "Возврат",
                "quantity": "1",
                "net_rev_kzt": "0",
                "article": "CL_OC_MEN_LINE51_WHITE_K-O_ST_XL_159720316",
            },
            {
                "_source_pack": "live_all_enabled_20260505_to_20260525",
                "_source_priority": 0,
                "_source_path": "/tmp/live.csv",
                "_source_sha256": "abc",
                "store_code": "ACMEWEAR",
                "order_id": "O3",
                "created_at": "2026-04-24",
                "status_change_at": "2026-05-07",
                "status_internal": "CANCELLED",
                "status_raw": "Отменен",
                "quantity": "1",
                "net_rev_kzt": "0",
                "article": "CL_OC_MEN_LINE51_WHITE_2XL_134547481",
            },
        ]
    )

    ledger = build_status_change_sales_ledger_from_frames(
        [frame],
        anchor_date=date(2026, 4, 23),
        as_of=date(2026, 5, 26),
    )

    delivered = ledger[ledger["order_id"] == "O1"].iloc[0]
    assert delivered["order_intake_date"] == "2026-04-24"
    assert delivered["sale_date"] == "2026-05-05"
    assert delivered["transaction_date"] == "2026-05-05"
    assert delivered["economic_final_sales_depletion_qty"] == 2.0

    returned = ledger[ledger["order_id"] == "O2"].iloc[0]
    assert returned["return_date"] == "2026-05-06"
    assert returned["economic_final_sales_depletion_qty"] == 0.0

    cancelled = ledger[ledger["order_id"] == "O3"].iloc[0]
    assert cancelled["cancel_date"] == "2026-05-07"
    assert cancelled["economic_final_sales_depletion_qty"] == 0.0


def test_stock_views_keep_physical_and_economic_quantities_separate() -> None:
    anchor = pd.DataFrame(
        [
            {
                "family": "LINE61",
                "sku_key": LINE61_SKU,
                "my_size": "XL",
                "sku_id": f"{LINE61_SKU}_XL",
                "april23_anchor_qty": 10.0,
                "cogs_kzt": 4000.0,
                "anchor_source": "test",
                "anchor_workbook_sha256": "anchor",
                "anchor_risk_flags": "",
            }
        ]
    )
    status_ledger = pd.DataFrame(
        [
            {
                "sku_key": LINE61_SKU,
                "my_size": "XL",
                "economic_final_sales_depletion_qty": 2.0,
                "return_date": "",
                "cancel_date": "",
                "quantity": 2.0,
                "mapping_blocker": "",
            }
        ]
    )
    shipped_ledger = pd.DataFrame(
        [
            {
                "sku_key": LINE61_SKU,
                "my_size": "XL",
                "physical_warehouse_depletion_qty": 3.0,
                "mapping_blocker": "",
            }
        ]
    )

    physical, economic, exposure, _ = build_stock_views(anchor, status_ledger, shipped_ledger)

    assert physical.iloc[0]["estimated_warehouse_on_hand_qty"] == 7.0
    assert economic.iloc[0]["estimated_final_sales_stock_qty"] == 8.0
    assert exposure.iloc[0]["on_delivery_exposure_qty"] == 1.0
