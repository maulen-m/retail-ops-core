from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_owner_truth_exceptions import generate_owner_truth_exceptions


def _write_daily_report(path: Path, *, as_of: str, ok: bool, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T18:00:00Z",
                "as_of": as_of,
                "status": status,
                "ok": ok,
                "steps_total": 5,
                "steps_failed": 0 if ok else 1,
                "stores_total": 5,
                "stores_red": 0 if ok else 1,
                "stores_green": 5 if ok else 4,
                "profile": "catch-up",
                "store_results": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_generate_owner_truth_exceptions_green_payload(tmp_path: Path) -> None:
    report_path = tmp_path / "exports" / "daily" / "2026-03-08" / "daily_ops_report.json"
    _write_daily_report(report_path, as_of="2026-03-08", ok=True, status="GREEN")

    result = generate_owner_truth_exceptions(
        as_of="2026-03-08",
        daily_report_json=report_path,
        output_dir=tmp_path / "exports" / "exceptions" / "2026-03-08",
        strict=True,
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "GREEN"
    assert payload["ok"] is True
    assert payload["exceptions"] == []
    assert payload["critical_count"] == 0


def test_generate_owner_truth_exceptions_red_payload_is_fail_closed(tmp_path: Path) -> None:
    report_path = tmp_path / "exports" / "daily" / "2026-03-08" / "daily_ops_report.json"
    _write_daily_report(report_path, as_of="2026-03-08", ok=False, status="RED")

    result = generate_owner_truth_exceptions(
        as_of="2026-03-08",
        daily_report_json=report_path,
        output_dir=tmp_path / "exports" / "exceptions" / "2026-03-08",
        strict=True,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 1
    payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "RED"
    assert payload["ok"] is False
    assert payload["critical_count"] == 1
    assert len(payload["exceptions"]) == 1
    row = payload["exceptions"][0]
    assert row["step"] == "daily_ops_report"
    assert row["domain"] == "runtime"
    assert row["severity"] == "critical"
    assert row["owner"] == "ops-codex"
    assert row["evidence_paths"] == [str(report_path)]
