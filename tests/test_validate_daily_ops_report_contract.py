from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_daily_ops_report import validate_daily_ops_report


def test_validate_daily_ops_report_accepts_red_report_with_consistent_fields(tmp_path: Path) -> None:
    summary_json = tmp_path / "daily_ops_summary.json"
    summary_json.write_text("{}", encoding="utf-8")
    report = tmp_path / "daily_ops_report.json"
    report.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-09T00:00:00Z",
                "as_of": "2026-03-09",
                "status": "RED",
                "ok": False,
                "exit_code": 1,
                "profile": "catch-up",
                "steps_total": 4,
                "steps_failed": 2,
                "failed_step_names": ["shipment_preflight", "waybill_status_UNIVERSAL"],
                "stores_total": 2,
                "stores_red": 1,
                "stores_green": 1,
                "red_store_codes": ["UNIVERSAL"],
                "store_results": {
                    "UNIVERSAL": {"ok": False, "rc": 1},
                    "ACMEWEAR": {"ok": True, "rc": 0},
                },
                "shipping_backlog": {"present": False},
                "summary_json": str(summary_json),
            }
        ),
        encoding="utf-8",
    )

    result = validate_daily_ops_report(report, strict=True)
    assert result["ok"] is True


def test_validate_daily_ops_report_fails_when_red_store_codes_disagree(tmp_path: Path) -> None:
    summary_json = tmp_path / "daily_ops_summary.json"
    summary_json.write_text("{}", encoding="utf-8")
    report = tmp_path / "daily_ops_report.json"
    report.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-09T00:00:00Z",
                "as_of": "2026-03-09",
                "status": "RED",
                "ok": False,
                "exit_code": 1,
                "profile": "catch-up",
                "steps_total": 1,
                "steps_failed": 1,
                "failed_step_names": ["waybill_status_UNIVERSAL"],
                "stores_total": 2,
                "stores_red": 1,
                "stores_green": 1,
                "red_store_codes": ["ACMEWEAR"],
                "store_results": {
                    "UNIVERSAL": {"ok": False, "rc": 1},
                    "ACMEWEAR": {"ok": True, "rc": 0},
                },
                "shipping_backlog": {"present": False},
                "summary_json": str(summary_json),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="red_store_codes mismatch"):
        validate_daily_ops_report(report, strict=True)
