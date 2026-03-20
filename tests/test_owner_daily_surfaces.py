from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_cash_risk_daily import build_cash_risk_daily
from scripts.build_owner_profit_daily import build_owner_profit_daily
from scripts.build_po_sku_daily import build_po_sku_daily


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_owner_profit_daily_derives_numeric_profit_from_locked_rows(tmp_path: Path) -> None:
    owner_truth_summary = tmp_path / "owner_truth_summary.json"
    system_health = tmp_path / "system_health.json"
    review_dir = tmp_path / "north_star_owner_review" / "2026-03-09"
    publication_readiness = review_dir / "publication_readiness.json"
    monthly_csv = review_dir / "monthly_totals_review.csv"

    _write_json(owner_truth_summary, {"status": "PASS", "ok": True})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(publication_readiness, {"status": "PASS", "profit_locked": False})
    review_dir.mkdir(parents=True, exist_ok=True)
    monthly_csv.write_text(
        "\n".join(
            [
                "sale_month,orders,units,net_rev_kzt,cogs_kzt,ads_kzt,profit_after_ads_kzt,decision_grade,statusdate_coverage_pct,profit_locked,opex_kzt,profit_after_ads_and_opex_kzt,provisional",
                "2026-01,10,10,1000,400,100,,False,103.49,True,50,,True",
                "2026-02,12,12,1200,500,200,,False,129.31,True,75,,True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_owner_profit_daily(
        as_of="2026-03-09",
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        review_dir=review_dir,
        output_root=tmp_path / "owner",
        validation_root=tmp_path / "validation",
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN"
    assert payload["semantics_mode"] == "PROVISIONAL_DERIVED_FROM_LOCKED_MONTHLY_REVIEW"
    assert payload["semantics_contract"] == "docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md"
    assert payload["production_acceptable"] is True
    assert payload["decision_scope"] == "OWNER_DAILY_MONITORING_ONLY"
    assert payload["rows"][0]["profit_after_ads_kzt"] == 500.0
    assert payload["rows"][0]["profit_after_ads_and_opex_kzt"] == 450.0
    assert payload["derived_profit_rows"] == 2
    trust_report = json.loads((tmp_path / "validation" / "2026-03-09" / "trust_report.json").read_text())
    assert trust_report["status"] == "PASS"
    assert trust_report["semantics_mode"] == "PROVISIONAL_DERIVED_FROM_LOCKED_MONTHLY_REVIEW"
    assert trust_report["production_acceptable"] is True
    assert trust_report["decision_scope"] == "OWNER_DAILY_MONITORING_ONLY"


def test_build_cash_risk_daily_uses_cashfloor_and_po_summary(tmp_path: Path) -> None:
    owner_truth_summary = tmp_path / "owner_truth_summary.json"
    system_health = tmp_path / "system_health.json"
    cashfloor_gate = tmp_path / "cashfloor_gate.json"
    po_dashboard = tmp_path / "po_dashboard_data.json"

    _write_json(owner_truth_summary, {"status": "PASS", "ok": True})
    _write_json(system_health, {"status": "GREEN"})
    _write_json(
        cashfloor_gate,
        {
            "status": "GREEN",
            "ok": True,
            "base_min_cash_kzt": 21043902.89,
            "base_min_cash_date": "2026-03-31",
            "conservative_min_cash_kzt": 39812065.85,
            "conservative_min_cash_date": "2026-03-31",
            "opex_monthly_kzt": 2663333.24,
        },
    )
    _write_json(
        po_dashboard,
        {
            "summary": {
                "total_po_cogs_kzt": 14563611.25,
                "total_po_base_cost_kzt": 10957719.15,
                "total_po_dlv_kzt": 3605890.41,
            },
            "real_pos": [
                {"po_id": "PO-4.0", "supplier_code": "SHR", "units_total": 100, "total_cost_cny": 1200.0},
                {"po_id": "PO-8.0", "supplier_code": "ARC", "units_total": 220, "total_cost_cny": 4200.0},
            ],
        },
    )

    payload = build_cash_risk_daily(
        as_of="2026-03-09",
        owner_truth_summary_path=owner_truth_summary,
        system_health_path=system_health,
        cashfloor_gate_path=cashfloor_gate,
        po_dashboard_path=po_dashboard,
        output_root=tmp_path / "owner",
        validation_root=tmp_path / "validation",
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_GREEN_LIVE_CHAIN"
    assert payload["base_min_cash_kzt"] == 21043902.89
    assert payload["po_total_cogs_kzt"] == 14563611.25
    assert payload["real_pos_count"] == 2
    assert payload["days_to_base_min_cash"] == 22
    assert payload["days_to_conservative_min_cash"] == 22
    assert payload["largest_po_commitment"]["po_id"] == "PO-8.0"
    assert payload["largest_po_commitment"]["supplier_code"] == "ARC"
    assert payload["largest_po_commitment"]["total_cost_cny"] == 4200.0
    assert payload["cash_risk_drivers"]
    assert payload["base_buffer_opex_months"] > 7.0
    assert payload["po_burden_pct_of_base_min_cash"] > 60.0


def test_build_po_sku_daily_extracts_top_real_pos_exposure(tmp_path: Path) -> None:
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
                "total_skus": 24,
                "total_units": 4610,
                "total_po_cogs_kzt": 14563611.25,
                "priority_skus": 0,
                "low_roic_skus": 1,
                "no_order_needed": 2,
            },
            "real_pos": [
                {"po_id": "PO-1", "supplier_code": "SHR", "units_total": 100, "total_cost_cny": 1200.0},
                {"po_id": "PO-2", "supplier_code": "SHR", "units_total": 500, "total_cost_cny": 2200.0},
                {"po_id": "PO-3", "supplier_code": "OTHER", "units_total": 50, "total_cost_cny": 300.0},
            ],
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
                        },
                        {
                            "sku_key": "SKU-KILL",
                            "sku_name": "Kill",
                            "po_qty_total": 50,
                            "deficit_total": 50,
                            "stock": 0,
                            "monthly_profit": -100.0,
                            "roic_pct": -20.0,
                            "roic_below_threshold": True,
                            "po_cogs_kzt": 120000.0,
                            "oos_type": "EXTENDED",
                            "notes": "ROIC -20% < 15%",
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
        max_rows=2,
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT"
    assert payload["summary"]["total_skus"] == 24
    assert [row["po_id"] for row in payload["top_real_pos"]] == ["PO-2", "PO-1"]
    assert payload["summary"]["low_roic_skus"] == 1
    assert payload["summary"]["no_order_needed"] == 2
    assert payload["planning_snapshot"]["base_stock_date"] == "2026-02-09"
    assert payload["planning_snapshot"]["cutoff_date"] == "2026-03-08"
    assert payload["planning_snapshot"]["freshness"] == "STALE_VS_CUTOFF"
    assert payload["action_buckets"]["reorder_now"][0]["sku_key"] == "SKU-REORDER"
    assert payload["action_buckets"]["freeze_or_kill_review"][0]["sku_key"] == "SKU-KILL"
    assert payload["action_buckets"]["no_order_needed"][0]["sku_key"] == "SKU-NOORDER"
    assert payload["action_buckets"]["tied_up_capital"][0]["sku_key"] == "SKU-REORDER"
    with (tmp_path / "owner" / "2026-03-09" / "po_sku_daily.md").open(encoding="utf-8") as handle:
        text = handle.read()
    assert "PO / SKU Daily" in text
    assert "Planning Snapshot" in text
    assert "Reorder Now" in text
    assert "Freeze / Kill Review" in text
