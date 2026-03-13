from __future__ import annotations

import json
from pathlib import Path

from scripts.build_cashflow_calendar_daily import build_cashflow_calendar_daily


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_cashflow_calendar_daily_surfaces_low_cash_dates_and_drivers(tmp_path: Path) -> None:
    owner_truth_summary = tmp_path / "daily" / "2026-03-09" / "owner_truth_summary.json"
    system_health = tmp_path / "diagnostics" / "2026-03-09" / "system_health.json"
    cashflow_scorecard = tmp_path / "daily" / "2026-03-09" / "cashflow_scorecard.json"
    cashfloor_gate = tmp_path / "daily" / "2026-03-09" / "cashfloor_gate.json"

    _write_json(owner_truth_summary, {"status": "PASS", "ok": True})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(cashflow_scorecard, {"status": "GREEN", "summary": "PASS: 30 days validated"})
    _write_json(
        cashfloor_gate,
        {
            "status": "GREEN",
            "ok": True,
            "base_floor_kzt": 1000.0,
            "base_min_cash_kzt": 900.0,
            "base_min_cash_date": "2026-03-12",
            "conservative_floor_kzt": 1500.0,
            "conservative_min_cash_kzt": 1400.0,
            "conservative_min_cash_date": "2026-03-12",
            "horizon_days": 30,
        },
    )

    sample_rows = [
        {
            "date": "2026-03-09",
            "cash_close": 1800.0,
            "cash_flow_kzt": -50.0,
            "po_payments_kzt": 0.0,
            "expenses_kzt": 40.0,
            "refunds_kzt": 0.0,
            "payouts_received_kzt": 0.0,
            "cogs_kzt": 15.0,
        },
        {
            "date": "2026-03-10",
            "cash_close": 1300.0,
            "cash_flow_kzt": -500.0,
            "po_payments_kzt": 350.0,
            "expenses_kzt": 50.0,
            "refunds_kzt": 0.0,
            "payouts_received_kzt": 0.0,
            "cogs_kzt": 20.0,
        },
        {
            "date": "2026-03-12",
            "cash_close": 900.0,
            "cash_flow_kzt": -400.0,
            "po_payments_kzt": 0.0,
            "expenses_kzt": 300.0,
            "refunds_kzt": 70.0,
            "payouts_received_kzt": 0.0,
            "cogs_kzt": 10.0,
        },
    ]

    payload = build_cashflow_calendar_daily(
        as_of="2026-03-09",
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        cashflow_scorecard_path=cashflow_scorecard,
        cashfloor_gate_path=cashfloor_gate,
        db_path=tmp_path / "db.sqlite",
        output_root=tmp_path / "owner",
        validation_root=tmp_path / "validation",
        horizon_days=14,
        daily_rows=sample_rows,
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_GREEN_LIVE_CHAIN"
    assert payload["calendar_window"]["start_date"] == "2026-03-09"
    assert payload["calendar_window"]["end_date"] == "2026-03-12"
    assert payload["critical_days"][0]["date"] == "2026-03-12"
    assert payload["critical_days"][0]["primary_driver"] == "EXPENSES"
    assert payload["largest_outflow_days"][0]["date"] == "2026-03-10"
    assert payload["largest_outflow_days"][0]["primary_driver"] == "PO_PAYMENTS"
    assert payload["base_floor_breach_dates"] == ["2026-03-12"]

    md_text = (tmp_path / "owner" / "2026-03-09" / "cashflow_calendar_daily.md").read_text(encoding="utf-8")
    assert "Cashflow Calendar Daily" in md_text
    assert "Critical Days" in md_text
    assert "Largest Outflow Days" in md_text

    trust_report = json.loads((tmp_path / "validation" / "2026-03-09" / "trust_report.json").read_text())
    assert trust_report["status"] == "PASS"
    assert trust_report["trust_banner"] == "PASS_GREEN_LIVE_CHAIN"
