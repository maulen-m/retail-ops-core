from datetime import date
from types import SimpleNamespace

import yaml

import scripts.generate_po_dashboard_data as dashboard


def _base_template() -> dict:
    return {
        "generated_at": "2026-02-08",
        "po_name": "PLAN-0",
        "plan_index": 0,
        "po_message_date": "2026-02-08",
        "cutoff_date": "2026-02-07",
        "sales_data_cutoff": "2026-02-07",
        "stock_date": "2026-02-07",
        "lead_time_L": 21,
        "reorder_cycle_R": 10,
        "prep_model": "B",
        "prep_days_clothes": 14,
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
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "sku_name": "LINE61",
                "stock": 100,
                "inbound": 0,
                "active_inbound": 0,
                "inbound_total": 0,
                "days_until_arrival": 35,
                "consumption_until_arrival": 700.0,
                "pre_arrival": 0,
                "d_sku": 20.0,
                "t_post_days": 29.0,
                "target": 580.0,
                "rop_total": 800.0,
                "deficit_total": 700,
                "po_qty_total": 700,
                "size_orders": {"M": 700},
                "po_weight_kg": 700.0,
                "prep_days": 14,
                "po_send_date": "2026-02-22",
                "po_message_date": "2026-02-08",
                "est_arr_date": "2026-03-14",
                "pre_arr_doc": 0.0,
                "post_arr_doc": 35.0,
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
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "sku_id": "CL_NEW-CLO2_MEN_SUIT-61_BLACK_M",
                "size": "M",
                "stock": 100,
                "inbound": 0,
                "active_inbound": 0,
                "inbound_total": 0,
                "days_until_arrival": 35,
                "consumption_until_arrival": 700.0,
                "pre_arrival": 0,
                "d_size": 20.0,
                "t_post_days": 29.0,
                "target": 580.0,
                "rop_size": 800.0,
                "deficit_size": 700,
                "order_qty": 700,
                "weight_kg": 700.0,
                "prep_days": 14,
                "po_send_date": "2026-02-22",
                "po_message_date": "2026-02-08",
                "est_arr_date": "2026-03-14",
                "pre_arr_doc": 0.0,
                "post_arr_doc": 35.0,
                "roic_pct": 10.0,
                "notes": "",
            }
        ],
        "size_horizontal": [],
        "skipped_skus": [],
    }


def _stub_runtime(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "resolve_last_real_po", lambda: ("PO-5", 5, "2026-01-21"))
    monkeypatch.setattr(dashboard, "load_po_orders", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard, "generate_po_data", lambda *_args, **_kwargs: _base_template())
    monkeypatch.setattr(
        dashboard,
        "get_params",
        lambda: SimpleNamespace(L=21, R=10, z=1.65, TV=0.23, B=14.0),
    )
    monkeypatch.setattr(
        dashboard,
        "get_fx_rates",
        lambda *_args, **_kwargs: SimpleNamespace(dlv_rate_usd_kg=2.0, usd_kzt=520.0),
    )
    monkeypatch.setattr(dashboard, "TODAY", date(2026, 2, 8))


def test_plan0_message_date_is_2026_02_25(tmp_path, monkeypatch) -> None:
    _stub_runtime(monkeypatch)
    schedule_cfg = tmp_path / "po_schedule.yaml"
    schedule_cfg.write_text(
        yaml.safe_dump(
            {
                "plan0_anchor_message_date": "2026-02-25",
                "reorder_cycle_days": 10,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "PO_SCHEDULE_PATH", schedule_cfg)

    all_pos, _ = dashboard.generate_multi_po_data(num_pos=1)
    assert all_pos["PLAN-0"]["po_message_date"] == "2026-02-25"


def test_following_plans_are_plus_10_days(tmp_path, monkeypatch) -> None:
    _stub_runtime(monkeypatch)
    schedule_cfg = tmp_path / "po_schedule.yaml"
    schedule_cfg.write_text(
        yaml.safe_dump(
            {
                "plan0_anchor_message_date": "2026-02-25",
                "reorder_cycle_days": 10,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "PO_SCHEDULE_PATH", schedule_cfg)

    all_pos, _ = dashboard.generate_multi_po_data(num_pos=3)
    assert all_pos["PLAN-0"]["po_message_date"] == "2026-02-25"
    assert all_pos["PLAN-1"]["po_message_date"] == "2026-03-07"
    assert all_pos["PLAN-2"]["po_message_date"] == "2026-03-17"
