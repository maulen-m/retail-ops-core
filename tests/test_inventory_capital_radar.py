from __future__ import annotations

import json
from pathlib import Path

from scripts.build_po_sku_daily import build_po_sku_daily


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_po_sku_daily_surfaces_inventory_capital_actions(tmp_path: Path) -> None:
    owner_truth_summary = tmp_path / "owner_truth_summary.json"
    system_health = tmp_path / "system_health.json"
    po_dashboard = tmp_path / "po_dashboard_data.json"

    _write_json(owner_truth_summary, {"status": "PASS", "ok": True})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(
        po_dashboard,
        {
            "base_stock_date": "2026-02-09",
            "cutoff_date": "2026-03-08",
            "summary": {
                "total_skus": 5,
                "total_units": 600,
                "total_po_cogs_kzt": 1000000.0,
                "priority_skus": 1,
                "low_roic_skus": 2,
                "no_order_needed": 1,
            },
            "real_pos": [
                {"po_id": "PO-1", "supplier_code": "SHR", "units_total": 200, "total_cost_cny": 2000.0},
            ],
            "pos": {
                "PLAN-0": {
                    "sku_level": [
                        {
                            "sku_key": "SKU-REORDER",
                            "sku_name": "Reorder",
                            "po_qty_total": 100,
                            "deficit_total": 80,
                            "stock": 20,
                            "monthly_profit": 1200.0,
                            "roic_pct": 55.0,
                            "roic_below_threshold": False,
                            "po_cogs_kzt": 500000.0,
                            "oos_type": "PARTIAL",
                            "notes": "NET_PRICE_PUBLISHED_TRUTH",
                        },
                        {
                            "sku_key": "SKU-FREEZE",
                            "sku_name": "Freeze",
                            "po_qty_total": 60,
                            "deficit_total": 60,
                            "stock": 0,
                            "monthly_profit": -90.0,
                            "roic_pct": -12.0,
                            "roic_below_threshold": True,
                            "po_cogs_kzt": 250000.0,
                            "oos_type": "EXTENDED",
                            "notes": "LOW_ROIC",
                        },
                        {
                            "sku_key": "SKU-NOORDER",
                            "sku_name": "No Order",
                            "po_qty_total": 0,
                            "deficit_total": 0,
                            "stock": 300,
                            "monthly_profit": 300.0,
                            "roic_pct": 80.0,
                            "roic_below_threshold": False,
                            "po_cogs_kzt": 0.0,
                            "oos_type": "NONE",
                            "notes": "NO_ORDER_NEEDED",
                        },
                    ]
                }
            },
        },
    )

    payload = build_po_sku_daily(
        as_of="2026-03-09",
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        po_dashboard_path=po_dashboard,
        output_root=tmp_path / "owner",
        validation_root=tmp_path / "validation",
        max_rows=5,
    )

    assert payload["status"] == "PASS"
    assert payload["planning_snapshot"]["freshness"] == "STALE_VS_CUTOFF"
    assert payload["action_buckets"]["reorder_now"][0]["sku_key"] == "SKU-REORDER"
    assert payload["action_buckets"]["freeze_or_kill_review"][0]["sku_key"] == "SKU-FREEZE"
    assert payload["action_buckets"]["tied_up_capital"][0]["sku_key"] == "SKU-REORDER"

    md_text = (tmp_path / "owner" / "2026-03-09" / "po_sku_daily.md").read_text(encoding="utf-8")
    assert "Planning Snapshot" in md_text
    assert "Tied Up Capital" in md_text
