from types import SimpleNamespace

from scripts.generate_po_dashboard_data import apply_po_overrides


def test_apply_po_overrides_recomputes_post_doc() -> None:
    base_data = {
        "po_message_date": "2026-01-01",
        "summary": {"total_units": 0, "skus_with_orders": 0, "skus_without_orders": 1},
        "sku_level": [
            {
                "sku_key": "SKU1",
                "pre_arrival": 770,
                "d_sku": 20.0,
                "pre_arr_doc": 38.5,
                "post_arr_doc": 38.5,
                "po_qty_total": 0,
                "size_orders": {},
                "weight_per_unit_kg": 1.0,
                "base_cost_cny": 10.0,
                "base_cost_kzt": 1000.0,
                "unit_cogs": 900.0,
                "po_weight_kg": 0.0,
                "po_base_cost_cny": 0.0,
                "po_base_cost_kzt": 0.0,
                "po_dlv_usd": 0.0,
                "po_dlv_kzt": 0.0,
                "po_cogs_kzt": 0.0,
                "prep_days": 1,
                "po_send_date": "2026-01-01",
                "po_message_date": "2026-01-01",
                "est_arr_date": "2026-01-01",
            }
        ],
        "size_level": [
            {
                "sku_key": "SKU1",
                "sku_id": "SKU1_M",
                "size": "M",
                "pre_arrival": 100,
                "d_size": 2.0,
                "pre_arr_doc": 50.0,
                "post_arr_doc": 50.0,
                "order_qty": 0,
                "weight_kg": 0.0,
                "prep_days": 1,
                "po_send_date": "2026-01-01",
                "po_message_date": "2026-01-01",
                "est_arr_date": "2026-01-01",
            }
        ],
    }

    po_data = {
        "orders_by_sku": {"SKU1": {"M": 1215}},
        "message_date": "2026-01-02",
        "ship_date_seller": "2026-01-03",
    }
    params = SimpleNamespace(L=21)
    fx_rates = SimpleNamespace(dlv_rate_usd_kg=2.0, usd_kzt=500.0)

    result = apply_po_overrides(base_data, po_data, params, fx_rates)
    sku_line = result["sku_level"][0]
    size_line = result["size_level"][0]

    expected_sku_doc = round((770 + 1215) / 20.0, 1)
    expected_size_doc = round((100 + 1215) / 2.0, 1)
    assert sku_line["post_arr_doc"] == expected_sku_doc
    assert size_line["post_arr_doc"] == expected_size_doc
