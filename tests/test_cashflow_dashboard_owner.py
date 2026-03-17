from __future__ import annotations

import json
from pathlib import Path

from scripts.build_cashflow_dashboard_owner import build_cashflow_dashboard_owner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_cashflow_dashboard_owner_reuses_existing_cash_surfaces(tmp_path: Path) -> None:
    as_of = "2026-03-09"
    owner_truth_summary = tmp_path / "exports" / "daily" / as_of / "owner_truth_summary.json"
    system_health = tmp_path / "exports" / "diagnostics" / as_of / "system_health.json"
    cash_risk = tmp_path / "exports" / "owner" / as_of / "cash_risk_daily.json"
    cashflow_calendar = tmp_path / "exports" / "owner" / as_of / "cashflow_calendar_daily.json"
    owner_profit = tmp_path / "exports" / "owner" / as_of / "owner_profit_daily.json"

    _write_json(owner_truth_summary, {"status": "PASS"})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(
        cash_risk,
        {
            "status": "PASS",
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "base_min_cash_kzt": 1000.0,
            "base_min_cash_date": "2026-03-31",
            "days_to_base_min_cash": 22,
            "po_burden_pct_of_base_min_cash": 55.0,
            "largest_po_commitment": {"po_id": "PO-1", "supplier_code": "SHR", "total_cost_cny": 1234.0},
            "cash_risk_drivers": ["Driver A"],
        },
    )
    _write_json(
        cashflow_calendar,
        {
            "status": "PASS",
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "calendar_window": {"start_date": as_of, "end_date": "2026-04-07", "days": 30},
            "critical_days": [
                {"date": as_of, "cash_close": 500.0, "primary_driver": "PAYOUTS"},
                {"date": "2026-03-10", "cash_close": 450.0, "primary_driver": "UNKNOWN"},
            ],
            "largest_outflow_days": [
                {"date": "2026-03-20", "cash_flow_kzt": -100.0, "primary_driver": "EXPENSES"}
            ],
            "base_floor_breach_dates": ["2026-03-31"],
            "conservative_floor_breach_dates": ["2026-03-31"],
        },
    )
    _write_json(
        owner_profit,
        {
            "status": "PASS",
            "trust_banner": "PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN",
            "decision_scope": "OWNER_DAILY_MONITORING_ONLY",
            "rows": [
                {
                    "sale_month": "2026-02",
                    "net_rev_kzt": 1000.0,
                    "cogs_kzt": 400.0,
                    "ads_kzt": 100.0,
                    "opex_kzt": 50.0,
                    "profit_after_ads_kzt": 500.0,
                    "profit_after_ads_and_opex_kzt": 450.0,
                    "provisional": True,
                }
            ],
        },
    )

    payload = build_cashflow_dashboard_owner(
        as_of=as_of,
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        cash_risk_path=cash_risk,
        cashflow_calendar_path=cashflow_calendar,
        owner_profit_path=owner_profit,
        output_root=tmp_path / "exports" / "owner",
    )

    assert payload["status"] == "PASS"
    assert payload["decision_scope"] == "OWNER_DAILY_MONITORING_ONLY"
    assert payload["cash_position"]["base_min_cash_kzt"] == 1000.0
    assert payload["calendar_focus"]["largest_outflow_days"][0]["cash_flow_kzt"] == -100.0
    assert payload["profit_focus"]["latest_month"]["sale_month"] == "2026-02"

    md_text = (tmp_path / "exports" / "owner" / as_of / "cashflow_dashboard_owner.md").read_text(
        encoding="utf-8"
    )
    assert "Cashflow Owner Dashboard" in md_text
    assert "Largest Outflow Days" in md_text
