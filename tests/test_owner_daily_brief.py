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
            "trust_banner": "PASS_GREEN_LIVE_CHAIN",
            "base_min_cash_kzt": 210.0,
            "conservative_min_cash_kzt": 398.0,
            "po_total_cogs_kzt": 145.0,
            "real_pos_count": 2,
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
        },
    )

    payload = build_owner_daily_brief(
        as_of="2026-03-09",
        owner_profit_path=owner_root / "owner_profit_daily.json",
        cash_risk_path=owner_root / "cash_risk_daily.json",
        po_sku_path=owner_root / "po_sku_daily.json",
        output_root=tmp_path / "owner",
        validation_root=validation_root,
    )

    assert payload["status"] == "PASS"
    assert payload["trust_banner"] == "PASS_OWNER_DAILY_BRIEF_READY"
    assert payload["sections"]["profit"]["production_acceptable"] is True
    assert payload["sections"]["cash_risk"]["real_pos_count"] == 2
    assert payload["sections"]["po_sku"]["top_real_pos"][0]["po_id"] == "PO-2"

    md_text = (tmp_path / "owner" / "2026-03-09" / "owner_daily_brief.md").read_text(encoding="utf-8")
    assert "Owner Daily Brief" in md_text
    assert "Profit" in md_text
    assert "Cash Risk" in md_text
    assert "PO / SKU" in md_text

    trust_report = json.loads((validation_root / "2026-03-09" / "trust_report.json").read_text(encoding="utf-8"))
    assert trust_report["status"] == "PASS"
    assert trust_report["trust_banner"] == "PASS_OWNER_DAILY_BRIEF_READY"

