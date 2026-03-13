from __future__ import annotations

import json
from pathlib import Path

from scripts.build_owner_daily_brief import build_owner_daily_brief


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_owner_daily_brief_combines_three_owner_surfaces(tmp_path: Path) -> None:
    owner_root = tmp_path / "owner" / "2026-03-09"
    validation_root = tmp_path / "validation"

    _write_json(
        owner_root / "owner_profit_daily.json",
        {
            "as_of": "2026-03-09",
            "status": "PASS",
            "trust_banner": "PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN",
            "production_acceptable": True,
            "decision_scope": "OWNER_DAILY_MONITORING_ONLY",
            "rows": [
                {
                    "sale_month": "2026-02",
                    "net_rev_kzt": 100.0,
                    "cogs_kzt": 40.0,
                    "ads_kzt": 10.0,
                    "opex_kzt": 5.0,
                    "profit_after_ads_kzt": 50.0,
                    "profit_after_ads_and_opex_kzt": 45.0,
                }
            ],
        },
    )
    _write_json(
        owner_root / "cash_risk_daily.json",
        {
            "as_of": "2026-03-09",
            "status": "PASS",
                "trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT",
            "base_min_cash_kzt": 210.0,
            "base_min_cash_date": "2026-03-31",
            "conservative_min_cash_kzt": 398.0,
            "conservative_min_cash_date": "2026-03-31",
            "po_total_cogs_kzt": 145.0,
            "real_pos_count": 2,
            "days_to_base_min_cash": 22,
            "cash_risk_drivers": ["PO burden high vs monthly opex"],
        },
    )
    _write_json(
        owner_root / "cashflow_calendar_daily.json",
        {
            "as_of": "2026-03-09",
            "status": "PASS",
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "calendar_window": {"start_date": "2026-03-09", "end_date": "2026-03-31", "days": 23},
            "critical_days": [
                {
                    "date": "2026-03-31",
                    "cash_close": 210.0,
                    "cash_flow_kzt": -120.0,
                    "primary_driver": "PO_PAYMENTS",
                }
            ],
            "largest_outflow_days": [
                {
                    "date": "2026-03-20",
                    "cash_flow_kzt": -200.0,
                    "primary_driver": "EXPENSES",
                }
            ],
            "base_floor_breach_dates": [],
        },
    )
    _write_json(
        owner_root / "po_sku_daily.json",
        {
            "as_of": "2026-03-09",
            "status": "PASS",
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "summary": {"total_skus": 24, "total_units": 4610, "total_po_cogs_kzt": 145.0},
            "top_real_pos": [{"po_id": "PO-2", "supplier_code": "SHR", "units_total": 500, "total_cost_cny": 2200.0}],
            "planning_snapshot": {
                "base_stock_date": "2026-02-09",
                "cutoff_date": "2026-03-08",
                "freshness": "STALE_VS_CUTOFF",
                "staleness_days_vs_cutoff": 27,
            },
            "action_buckets": {
                "reorder_now": [{"sku_key": "SKU-REORDER", "sku_name": "Reorder", "po_cogs_kzt": 400.0}],
                "freeze_or_kill_review": [{"sku_key": "SKU-KILL", "sku_name": "Kill", "po_cogs_kzt": 120.0}],
                "no_order_needed": [{"sku_key": "SKU-NOORDER", "sku_name": "No Order", "stock": 300}],
                "tied_up_capital": [{"sku_key": "SKU-REORDER", "sku_name": "Reorder", "po_cogs_kzt": 400.0}],
            },
            "capital_radar": {
                "largest_tied_up_sku": {"sku_key": "SKU-REORDER", "po_cogs_kzt": 400.0},
                "reorder_now_cogs_kzt": 400.0,
                "freeze_or_kill_cogs_kzt": 120.0,
                "tied_up_capital_top5_kzt": 520.0,
                "planning_snapshot_freshness": "STALE_VS_CUTOFF",
            },
        },
    )

    payload = build_owner_daily_brief(
        as_of="2026-03-09",
        owner_profit_path=owner_root / "owner_profit_daily.json",
        cash_risk_path=owner_root / "cash_risk_daily.json",
        cashflow_calendar_path=owner_root / "cashflow_calendar_daily.json",
        po_sku_path=owner_root / "po_sku_daily.json",
        output_root=tmp_path / "owner",
        validation_root=validation_root,
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_OWNER_DAILY_BRIEF_READY"
    assert payload["sections"]["profit"]["production_acceptable"] is True
    assert payload["sections"]["cash_risk"]["real_pos_count"] == 2
    assert payload["sections"]["cashflow_calendar"]["critical_days"][0]["date"] == "2026-03-31"
    assert payload["sections"]["po_sku"]["top_real_pos"][0]["po_id"] == "PO-2"
    assert payload["headline"]
    assert payload["owner_actions"]
    assert payload["sections"]["po_sku"]["planning_snapshot"]["freshness"] == "STALE_VS_CUTOFF"
    assert payload["sections"]["po_sku"]["action_buckets"]["freeze_or_kill_review"][0]["sku_key"] == "SKU-KILL"

    md_text = (tmp_path / "owner" / "2026-03-09" / "owner_daily_brief.md").read_text(encoding="utf-8")
    assert "Owner Daily Brief" in md_text
    assert "What Matters Now" in md_text
    assert "Profit" in md_text
    assert "Cash Risk" in md_text
    assert "Cashflow Calendar" in md_text
    assert "PO / SKU" in md_text
    assert "Owner Actions" in md_text

    trust_report = json.loads((validation_root / "2026-03-09" / "trust_report.json").read_text(encoding="utf-8"))
    assert trust_report["status"] == "PASS"
    assert trust_report["trust_banner"] == "PASS_OWNER_DAILY_BRIEF_READY"
