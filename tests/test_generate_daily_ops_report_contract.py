from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_daily_ops_report import generate_daily_ops_report


def test_generate_daily_ops_report_emits_red_store_codes_for_live_red_summary(tmp_path: Path) -> None:
    summary = {
        "generated_at": "2026-03-09T00:00:00Z",
        "as_of": "2026-03-09",
        "ok": False,
        "exit_code": 1,
        "profile": "catch-up",
        "steps": [
            {"step": "shipment_preflight", "ok": False, "rc": 1, "summary": "validate_params failed"},
            {"step": "waybill_status_UNIVERSAL", "ok": False, "rc": 1, "summary": "stopline"},
            {"step": "waybill_status_ACMEWEAR", "ok": True, "rc": 0, "summary": "ok"},
        ],
        "store_results": {
            "UNIVERSAL": {"ok": False, "rc": 1, "summary": "stopline"},
            "ACMEWEAR": {"ok": True, "rc": 0, "summary": "ok"},
        },
        "shipping_backlog_latest": {"present": False},
    }
    summary_path = tmp_path / "daily_ops_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    out_dir = tmp_path / "exports" / "daily" / "2026-03-09"
    result = generate_daily_ops_report(summary_json=summary_path, output_dir=out_dir)
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))

    assert payload["status"] == "RED"
    assert payload["stores_red"] == 1
    assert payload["red_store_codes"] == ["UNIVERSAL"]
    assert payload["failed_step_names"] == ["shipment_preflight", "waybill_status_UNIVERSAL"]
