import pandas as pd

from core.analytics.reconciliation import compare_sales_frames


def test_compare_sales_frames_detects_mismatches():
    crm_df = pd.DataFrame(
        [
            {"order_date": "2026-01-01", "units": 2, "net_rev_line": 1000, "order_id": "A", "sku_id": "SKU1"},
            {"order_date": "2026-01-02", "units": 1, "net_rev_line": 500, "order_id": "B", "sku_id": "SKU2"},
        ]
    )
    fact_df = pd.DataFrame(
        [
            {"order_date": "2026-01-01", "units": 2, "net_rev_line": 900, "order_id": "A", "sku_id": "SKU1"},
            {"order_date": "2026-01-03", "units": 1, "net_rev_line": 400, "order_id": "C", "sku_id": "SKU3"},
        ]
    )

    result = compare_sales_frames(crm_df, fact_df)
    summary = result["summary"]

    assert summary["crm_units"] == 3
    assert summary["fact_units"] == 3
    assert summary["missing_in_fact"] == 1
    assert summary["missing_in_crm"] == 1

    by_date = result["by_date"]
    jan1 = by_date[by_date["date"].astype(str) == "2026-01-01"].iloc[0]
    assert jan1["delta_net_rev"] == 100
