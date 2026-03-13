from __future__ import annotations

import json
from pathlib import Path

from scripts.run_owner_review_cycle import run_owner_review_cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_run_owner_review_cycle_refreshes_surfaces_brief_and_scorecard(tmp_path: Path) -> None:
    owner_truth_summary = tmp_path / "daily" / "2026-03-09" / "owner_truth_summary.json"
    system_health = tmp_path / "diagnostics" / "2026-03-09" / "system_health.json"
    cashfloor_gate = tmp_path / "validation" / "cashfloor" / "cashfloor_gate_report.json"
    po_dashboard = tmp_path / "exports" / "po_dashboard_data.json"
    review_dir = tmp_path / "review" / "2026-03-09"
    db_path = tmp_path / "db.sqlite"

    _write_json(owner_truth_summary, {"status": "PASS", "ok": True})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(
        cashfloor_gate,
        {
            "status": "GREEN",
            "ok": True,
            "base_min_cash_kzt": 210.0,
            "base_min_cash_date": "2026-03-31",
            "conservative_min_cash_kzt": 398.0,
            "conservative_min_cash_date": "2026-03-31",
            "opex_monthly_kzt": 26.0,
        },
    )
    _write_json(
        po_dashboard,
        {
            "summary": {
                "total_po_cogs_kzt": 145.0,
                "total_po_base_cost_kzt": 110.0,
                "total_po_dlv_kzt": 35.0,
                "total_skus": 24,
                "total_units": 4610,
                "priority_skus": 0,
                "low_roic_skus": 1,
                "no_order_needed": 1,
            },
            "real_pos": [{"po_id": "PO-2", "supplier_code": "SHR", "units_total": 500, "total_cost_cny": 2200.0}],
            "pos": {
                "PLAN-0": {
                    "sku_level": [
                        {
                            "sku_key": "SKU-REORDER",
                            "sku_name": "Reorder",
                            "po_qty_total": 120,
                            "deficit_total": 100,
                            "stock": 10,
                            "monthly_profit": 1000.0,
                            "roic_pct": 50.0,
                            "roic_below_threshold": False,
                            "po_cogs_kzt": 400000.0,
                            "oos_type": "PARTIAL",
                            "notes": "NET_PRICE_PUBLISHED_TRUTH",
                        }
                    ]
                }
            },
        },
    )
    _write_json(review_dir / "publication_readiness.json", {"status": "PASS"})
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "monthly_totals_review.csv").write_text(
        "\n".join(
            [
                "sale_month,orders,units,net_rev_kzt,cogs_kzt,ads_kzt,profit_after_ads_kzt,decision_grade,statusdate_coverage_pct,profit_locked,opex_kzt,profit_after_ads_and_opex_kzt,provisional",
                "2026-02,10,10,1000,400,100,,False,100.0,True,50,,True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_scorecard_builder(*, project_root: Path, as_of: str, output_root: Path, strict: bool) -> dict:
        day_dir = output_root / as_of
        day_dir.mkdir(parents=True, exist_ok=True)
        payload = {"domain": "cashflow", "status": "GREEN", "summary": "ok"}
        (day_dir / "cashflow_scorecard.json").write_text(json.dumps(payload), encoding="utf-8")
        (day_dir / "cashflow_scorecard.md").write_text("# cashflow scorecard\n", encoding="utf-8")
        return {"ok": True, "exit_code": 0, "scorecards": {"cashflow": payload}, "output_dir": str(day_dir)}

    def fake_cashflow_calendar_builder(**_: object) -> dict:
        owner_dir = tmp_path / "owner" / "2026-03-09"
        owner_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "as_of": "2026-03-09",
            "status": "PASS",
            "ok": True,
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "calendar_window": {"start_date": "2026-03-09", "end_date": "2026-03-31", "days": 23},
            "critical_days": [{"date": "2026-03-31", "cash_close": 210.0, "cash_flow_kzt": -120.0, "primary_driver": "PO_PAYMENTS"}],
            "largest_outflow_days": [{"date": "2026-03-20", "cash_flow_kzt": -200.0, "primary_driver": "EXPENSES"}],
            "base_floor_breach_dates": [],
        }
        (owner_dir / "cashflow_calendar_daily.json").write_text(json.dumps(payload), encoding="utf-8")
        (owner_dir / "cashflow_calendar_daily.md").write_text("# Cashflow Calendar Daily\n", encoding="utf-8")
        validation_dir = tmp_path / "validation" / "cashflow_calendar_daily" / "2026-03-09"
        validation_dir.mkdir(parents=True, exist_ok=True)
        (validation_dir / "trust_report.json").write_text(json.dumps({"status": "PASS", "trust_banner": "PASS_GREEN_LIVE_CHAIN"}), encoding="utf-8")
        return payload

    report = run_owner_review_cycle(
        as_of="2026-03-09",
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        review_dir=review_dir,
        cashfloor_gate_path=cashfloor_gate,
        db_path=db_path,
        po_dashboard_path=po_dashboard,
        owner_output_root=tmp_path / "owner",
        owner_profit_validation_root=tmp_path / "validation" / "owner_profit_daily",
        cash_risk_validation_root=tmp_path / "validation" / "cash_risk_daily",
        cashflow_calendar_validation_root=tmp_path / "validation" / "cashflow_calendar_daily",
        po_sku_validation_root=tmp_path / "validation" / "po_sku_daily",
        owner_daily_brief_validation_root=tmp_path / "validation" / "owner_daily_brief",
        scorecard_output_root=tmp_path / "daily",
        scorecard_report_path=tmp_path / "reports" / "scorecard_refresh_report.md",
        scorecard_builder=fake_scorecard_builder,
        cashflow_calendar_builder=fake_cashflow_calendar_builder,
    )

    assert report["status"] == "PASS"
    assert report["scorecards"]["status"] == "PASS"
    assert (tmp_path / "owner" / "2026-03-09" / "owner_profit_daily.json").exists()
    assert (tmp_path / "owner" / "2026-03-09" / "cash_risk_daily.json").exists()
    assert (tmp_path / "owner" / "2026-03-09" / "cashflow_calendar_daily.json").exists()
    assert (tmp_path / "owner" / "2026-03-09" / "po_sku_daily.json").exists()
    assert (tmp_path / "owner" / "2026-03-09" / "owner_daily_brief.json").exists()
    scorecard_text = (tmp_path / "reports" / "scorecard_refresh_report.md").read_text(encoding="utf-8")
    assert "cashflow_scorecard.json" in scorecard_text
    assert "cashflow_calendar_daily_status" in scorecard_text
    assert "owner_daily_brief_status" in scorecard_text
    assert "owner_profit_status" in scorecard_text
