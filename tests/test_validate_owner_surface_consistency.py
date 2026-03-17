from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_owner_surface_consistency import build_owner_surface_consistency_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_owner_surface_consistency_rejects_nonnegative_unknown_largest_outflow(tmp_path: Path) -> None:
    owner_dir = tmp_path / "owner" / "2026-03-09"
    _write_json(owner_dir / "owner_profit_daily.json", {"trust_banner": "PASS_PROVISIONAL", "decision_scope": "OWNER_DAILY_MONITORING_ONLY"})
    _write_json(owner_dir / "cash_risk_daily.json", {"trust_banner": "PASS_GREEN_LIVE_CHAIN"})
    _write_json(
        owner_dir / "cashflow_calendar_daily.json",
        {
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "critical_days": [{"date": "2026-03-10", "primary_driver": "PAYOUTS", "cash_close": 100.0}],
            "largest_outflow_days": [{"date": "2026-03-11", "cash_flow_kzt": 0.0, "primary_driver": "UNKNOWN"}],
        },
    )
    _write_json(
        owner_dir / "po_sku_daily.json",
        {
            "trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT",
            "planning_snapshot": {"freshness": "STALE_VS_CUTOFF"},
        },
    )
    _write_json(
        owner_dir / "owner_daily_brief.json",
        {
            "headline": "Latest monitored month 2026-02 shows 1 KZT. PO planning snapshot is stale by 31 days versus cutoff.",
            "owner_actions": ["Prepare for PAYOUTS pressure on 2026-03-10."],
            "sections": {
                "profit": {"trust_banner": "PASS_PROVISIONAL", "decision_scope": "OWNER_DAILY_MONITORING_ONLY"},
                "cash_risk": {"trust_banner": "PASS_GREEN_LIVE_CHAIN"},
                "cashflow_calendar": {"trust_banner": "PASS_GREEN_LIVE_CHAIN"},
                "po_sku": {"trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT"},
            },
        },
    )

    report = build_owner_surface_consistency_report(
        as_of="2026-03-09",
        owner_profit_path=owner_dir / "owner_profit_daily.json",
        cash_risk_path=owner_dir / "cash_risk_daily.json",
        cashflow_calendar_path=owner_dir / "cashflow_calendar_daily.json",
        po_sku_path=owner_dir / "po_sku_daily.json",
        owner_daily_brief_path=owner_dir / "owner_daily_brief.json",
    )

    assert report["status"] == "FAIL"
    codes = {item["code"]: item["ok"] for item in report["checks"]}
    assert codes["LARGEST_OUTFLOW_NEGATIVE_ONLY"] is False
    assert codes["LARGEST_OUTFLOW_DRIVER_RESOLVED"] is False


def test_owner_surface_consistency_passes_when_surfaces_align(tmp_path: Path) -> None:
    owner_dir = tmp_path / "owner" / "2026-03-09"
    _write_json(owner_dir / "owner_profit_daily.json", {"trust_banner": "PASS_PROVISIONAL", "decision_scope": "OWNER_DAILY_MONITORING_ONLY"})
    _write_json(owner_dir / "cash_risk_daily.json", {"trust_banner": "PASS_GREEN_LIVE_CHAIN"})
    _write_json(
        owner_dir / "cashflow_calendar_daily.json",
        {
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "critical_days": [{"date": "2026-03-10", "primary_driver": "PAYOUTS", "cash_close": 100.0}],
            "largest_outflow_days": [{"date": "2026-03-11", "cash_flow_kzt": -50.0, "primary_driver": "EXPENSES"}],
        },
    )
    _write_json(
        owner_dir / "po_sku_daily.json",
        {
            "trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT",
            "planning_snapshot": {"freshness": "STALE_VS_CUTOFF"},
        },
    )
    _write_json(
        owner_dir / "owner_daily_brief.json",
        {
            "headline": "Latest monitored month 2026-02 shows 1 KZT. PO planning snapshot is stale by 31 days versus cutoff.",
            "owner_actions": ["Prepare for PAYOUTS pressure on 2026-03-10."],
            "sections": {
                "profit": {"trust_banner": "PASS_PROVISIONAL", "decision_scope": "OWNER_DAILY_MONITORING_ONLY"},
                "cash_risk": {"trust_banner": "PASS_GREEN_LIVE_CHAIN"},
                "cashflow_calendar": {"trust_banner": "PASS_GREEN_LIVE_CHAIN"},
                "po_sku": {"trust_banner": "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT"},
            },
        },
    )

    report = build_owner_surface_consistency_report(
        as_of="2026-03-09",
        owner_profit_path=owner_dir / "owner_profit_daily.json",
        cash_risk_path=owner_dir / "cash_risk_daily.json",
        cashflow_calendar_path=owner_dir / "cashflow_calendar_daily.json",
        po_sku_path=owner_dir / "po_sku_daily.json",
        owner_daily_brief_path=owner_dir / "owner_daily_brief.json",
    )

    assert report["status"] == "PASS"
