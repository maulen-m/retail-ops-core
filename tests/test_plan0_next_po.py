from datetime import date
from types import SimpleNamespace

import scripts.generate_po_dashboard_data as dashboard


def test_plan0_is_next_po_after_latest_real(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard,
        "resolve_last_real_po",
        lambda: ("PO-5", 5, "2026-01-21"),
    )
    monkeypatch.setattr(dashboard, "load_po_orders", lambda _po_id: None)

    def fake_generate_po_data(*_args, **_kwargs):
        return {
            "generated_at": "2026-02-05",
            "po_name": "PLAN-0",
            "plan_index": 0,
            "po_message_date": "2026-02-05",
            "cutoff_date": "2026-02-04",
            "sales_data_cutoff": "2026-02-04",
            "stock_date": "2026-02-04",
            "lead_time_L": 21,
            "reorder_cycle_R": 10,
            "prep_model": "B",
            "prep_days_clothes": 5,
            "roic_threshold_pct": 15.0,
            "summary": {
                "total_skus": 1,
                "skus_with_orders": 1,
                "skus_without_orders": 0,
                "total_units": 10,
                "total_weight_kg": 10.0,
                "low_roic_skus": 0,
                "priority_skus": 0,
                "no_demand_estimate": 0,
                "no_stock_snapshot": 0,
                "no_order_needed": 0,
                "cashflow_preflight_ok": True,
                "cashflow_preflight_reason": None,
            },
            "sku_level": [
                {
                    "sku_key": "CL_TEST",
                    "sku_name": "CL_TEST",
                    "stock": 100,
                    "inbound": 0,
                    "active_inbound": 0,
                    "inbound_total": 0,
                    "days_until_arrival": 26,
                    "consumption_until_arrival": 0.0,
                    "pre_arrival": 100,
                    "d_sku": 2.0,
                    "t_post_days": 10.0,
                    "target": 20.0,
                    "rop_total": 10.0,
                    "deficit_total": 0,
                    "po_qty_total": 10,
                    "size_orders": {"M": 10},
                    "po_weight_kg": 10.0,
                    "prep_days": 5,
                    "po_send_date": "2026-02-06",
                    "po_message_date": "2026-02-05",
                    "est_arr_date": "2026-02-26",
                    "pre_arr_doc": 50.0,
                    "post_arr_doc": 55.0,
                    "monthly_profit": 0.0,
                    "k_avg": 0.0,
                    "roic_pct": 10.0,
                    "profit_margin_pct": 0.0,
                    "base_cost_cny": 10.0,
                    "base_cost_kzt": 1000.0,
                    "weight_per_unit_kg": 1.0,
                    "unit_cogs": 900.0,
                    "avg_sell_price": 0.0,
                    "net_revenue_unit": 0.0,
                    "profit_unit": 0.0,
                    "po_base_cost_cny": 0.0,
                    "po_base_cost_kzt": 0.0,
                    "po_dlv_usd": 0.0,
                    "po_dlv_kzt": 0.0,
                    "po_cogs_kzt": 0.0,
                    "roic_below_threshold": False,
                    "d_anchor": 0.0,
                    "d_data": 0.0,
                    "d_model": 0.0,
                    "anchor_weight": 0.0,
                    "availability_score": 0.0,
                    "confidence": "TEST",
                    "oos_type": "NONE",
                    "partial_oos_sizes": "",
                    "notes": "",
                }
            ],
            "size_level": [
                {
                    "sku_key": "CL_TEST",
                    "sku_id": "CL_TEST_M",
                    "size": "M",
                    "stock": 100,
                    "inbound": 0,
                    "active_inbound": 0,
                    "inbound_total": 0,
                    "days_until_arrival": 26,
                    "consumption_until_arrival": 0.0,
                    "pre_arrival": 100,
                    "d_size": 2.0,
                    "t_post_days": 10.0,
                    "target": 20.0,
                    "rop_size": 10.0,
                    "deficit_size": 10,
                    "order_qty": 10,
                    "weight_kg": 10.0,
                    "prep_days": 5,
                    "po_send_date": "2026-02-06",
                    "po_message_date": "2026-02-05",
                    "est_arr_date": "2026-02-26",
                    "pre_arr_doc": 50.0,
                    "post_arr_doc": 55.0,
                    "roic_pct": 10.0,
                    "notes": "",
                }
            ],
            "size_horizontal": [],
            "skipped_skus": [],
        }

    monkeypatch.setattr(dashboard, "generate_po_data", fake_generate_po_data)

    def fake_build_schedule(_today, _params, _prep_days, max_po_num=10):
        schedule = {
            "PO-5": date(2026, 1, 21),
            "PO-6": date(2026, 2, 1),
        }
        return schedule, 11

    monkeypatch.setattr(dashboard, "_build_po_schedule", fake_build_schedule)
    monkeypatch.setattr(
        dashboard,
        "get_params",
        lambda: SimpleNamespace(L=21, R=10, z=1.65, TV=0.23, B=14.0),
    )
    monkeypatch.setattr(
        dashboard,
        "get_fx_rates",
        lambda *_args, **_kwargs: SimpleNamespace(dlv_rate_usd_kg=2.0, usd_kzt=500.0),
    )
    monkeypatch.setattr(dashboard, "TODAY", date(2026, 2, 5))

    all_pos, _ = dashboard.generate_multi_po_data(num_pos=2)

    assert "PO-5" not in all_pos
    assert all_pos["PLAN-0"]["po_message_date"] == "2026-02-01"
    assert all_pos["PLAN-0"]["po_message_date"] != "2026-01-21"
