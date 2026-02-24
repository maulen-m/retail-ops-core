from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_daily_ops_report import generate_daily_ops_report
from scripts.validate_daily_ops_report import validate_daily_ops_report


def test_daily_ops_report_generator_and_validator_contract(tmp_path: Path) -> None:
    summary = {
        "generated_at": "2026-02-25T00:00:00Z",
        "as_of": "2026-02-25",
        "ok": True,
        "exit_code": 0,
        "profile": "today-fast",
        "steps": [
            {"step": "waybill_status_UNIVERSAL", "ok": True, "rc": 0, "summary": "ok"},
            {"step": "waybill_status_ACMEWEAR", "ok": True, "rc": 0, "summary": "ok"},
        ],
        "store_results": {
            "UNIVERSAL": {"ok": True, "rc": 0},
            "ACMEWEAR": {"ok": True, "rc": 0},
        },
    }
    summary_path = tmp_path / "daily_ops_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    out_dir = tmp_path / "exports" / "daily" / "2026-02-25"
    report = generate_daily_ops_report(summary_json=summary_path, output_dir=out_dir)

    assert Path(report["json_path"]).exists()
    assert Path(report["md_path"]).exists()

    payload = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert payload["as_of"] == "2026-02-25"
    assert payload["status"] == "GREEN"
    assert payload["stores_total"] == 2
    assert payload["stores_red"] == 0

    validation = validate_daily_ops_report(Path(report["json_path"]), strict=True)
    assert validation["ok"] is True


def test_daily_ops_report_validator_fails_closed_on_malformed_payload(tmp_path: Path) -> None:
    bad = tmp_path / "daily_ops_report.json"
    bad.write_text(json.dumps({"status": "GREEN"}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing required field"):
        validate_daily_ops_report(bad, strict=True)
