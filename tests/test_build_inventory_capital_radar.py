from __future__ import annotations

import json
from pathlib import Path

from scripts.build_inventory_capital_radar import build_inventory_capital_radar


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_inventory_capital_radar_reuses_po_surface_without_new_math(tmp_path: Path) -> None:
    as_of = "2026-03-09"
    owner_truth_summary = tmp_path / "exports" / "daily" / as_of / "owner_truth_summary.json"
    system_health = tmp_path / "exports" / "diagnostics" / as_of / "system_health.json"
    po_sku = tmp_path / "exports" / "owner" / as_of / "po_sku_daily.json"
    owner_profit = tmp_path / "exports" / "owner" / as_of / "owner_profit_daily.json"

    _write_json(owner_truth_summary, {"status": "PASS"})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(
        po_sku,
        {
            "status": "PASS",
            "trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT",
            "planning_snapshot": {
                "base_stock_date": "2026-02-09",
                "cutoff_date": "2026-03-12",
                "freshness": "STALE_VS_CUTOFF",
                "staleness_days_vs_cutoff": 31,
            },
            "summary": {"total_skus": 24, "total_units": 4595, "total_po_cogs_kzt": 14509600.75},
            "action_buckets": {
                "reorder_now": [{"sku_key": "SKU-A", "po_cogs_kzt": 1000.0, "po_qty_total": 10}],
                "freeze_or_kill_review": [{"sku_key": "SKU-B", "po_cogs_kzt": 500.0, "roic_pct": -10.0}],
                "no_order_needed": [{"sku_key": "SKU-C", "stock": 300, "notes": "NO_ORDER_NEEDED"}],
                "tied_up_capital": [{"sku_key": "SKU-A", "po_cogs_kzt": 1000.0, "po_qty_total": 10}],
            },
            "top_real_pos": [{"po_id": "PO-1", "supplier_code": "SHR", "units_total": 200, "total_cost_cny": 2000.0}],
        },
    )
    _write_json(
        owner_profit,
        {
            "status": "PASS",
            "decision_scope": "OWNER_DAILY_MONITORING_ONLY",
            "rows": [{"sale_month": "2026-02", "provisional": True, "source_profit_locked": True}],
        },
    )

    payload = build_inventory_capital_radar(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        po_sku_daily_path=po_sku,
        owner_profit_daily_path=owner_profit,
        output_root=tmp_path / "exports" / "owner",
    )

    assert payload["status"] == "PASS"
    assert payload["planning_snapshot"]["freshness"] == "STALE_VS_CUTOFF"
    assert payload["action_buckets"]["reorder_now"][0]["sku_key"] == "SKU-A"
    assert payload["profit_scope"]["decision_scope"] == "OWNER_DAILY_MONITORING_ONLY"

    md_text = (tmp_path / "exports" / "owner" / as_of / "inventory_capital_radar.md").read_text(
        encoding="utf-8"
    )
    assert "Inventory Capital Radar" in md_text
    assert "Freeze / Kill Review" in md_text
