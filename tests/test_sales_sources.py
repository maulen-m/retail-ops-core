import pandas as pd

from core.analytics.sales_sources import merge_sales_sources


def test_merge_sales_sources_prefers_crm():
    crm_df = pd.DataFrame(
        [
            {
                "order_id": "A1",
                "order_date": "2026-01-02",
                "sku_key": "SKU1",
                "sku_id": "SKU1_XL",
                "my_size": "XL",
                "kaspi_offer_name": "Offer1",
                "store_code": "UNIVERSAL",
                "quantity": 2,
                "sell_price_kzt": 12000,
                "delivery_fee": 856,
                "cogs": None,
                "net_rev": 1000,
                "profit": None,
                "status": "DELIVERED",
                "return_flag": 0,
                "source_file": "CRM",
            }
        ]
    )
    fact_df = pd.DataFrame(
        [
            {
                "order_id": "A1",
                "order_date": "2026-01-02",
                "sku_key": "SKU1",
                "sku_id": "SKU1_XL",
                "my_size": "XL",
                "kaspi_offer_name": "Offer1",
                "store_code": "UNIVERSAL",
                "quantity": 1,
                "sell_price_kzt": 11000,
                "delivery_fee": 856,
                "cogs": 5000,
                "net_rev": 900,
                "profit": 400,
                "status": "DELIVERED",
                "return_flag": 0,
                "source_file": "FACT",
            },
            {
                "order_id": "B2",
                "order_date": "2025-12-30",
                "sku_key": "SKU2",
                "sku_id": "SKU2_L",
                "my_size": "L",
                "kaspi_offer_name": "Offer2",
                "store_code": "UNIVERSAL",
                "quantity": 1,
                "sell_price_kzt": 9000,
                "delivery_fee": 0,
                "cogs": 3000,
                "net_rev": 700,
                "profit": 400,
                "status": "DELIVERED",
                "return_flag": 0,
                "source_file": "FACT",
            },
        ]
    )

    combined, stats = merge_sales_sources(crm_df, fact_df)

    assert stats.overlap_rows == 0
    assert stats.fact_rows_dropped_by_date == 1
    assert stats.cutoff_date == "2026-01-02"
    assert stats.combined_rows == 2
    chosen = combined[combined["order_id"] == "A1"].iloc[0]
    assert chosen["quantity"] == 2
    assert chosen["source_file"] == "CRM"


def test_merge_sales_sources_drops_sizeless_duplicates():
    crm_df = pd.DataFrame(
        [
            {
                "order_id": "X1",
                "order_date": "2026-01-04",
                "sku_key": "SKU_PRINT",
                "sku_id": "SKU_PRINT_L",
                "my_size": "L",
                "kaspi_offer_name": "Offer",
                "store_code": "ACMEWEAR",
                "quantity": 1,
                "sell_price_kzt": 12000,
                "delivery_fee": 856,
                "cogs": None,
                "net_rev": 1000,
                "profit": None,
                "status": "DELIVERED",
                "return_flag": 0,
                "source_file": "CRM",
            },
            {
                "order_id": "X1",
                "order_date": "2026-01-04",
                "sku_key": "SKU_PRINT",
                "sku_id": "SKU_PRINT",
                "my_size": "BLACK",
                "kaspi_offer_name": "Offer",
                "store_code": "ACMEWEAR",
                "quantity": 1,
                "sell_price_kzt": 12000,
                "delivery_fee": 856,
                "cogs": None,
                "net_rev": 1000,
                "profit": None,
                "status": "DELIVERED",
                "return_flag": 0,
                "source_file": "CRM",
            },
        ]
    )
    fact_df = pd.DataFrame(columns=crm_df.columns)

    combined, stats = merge_sales_sources(crm_df, fact_df)

    assert stats.combined_rows == 1
    assert combined.iloc[0]["sku_id"] == "SKU_PRINT_L"
