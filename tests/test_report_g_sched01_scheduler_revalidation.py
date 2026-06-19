from __future__ import annotations

import json
from pathlib import Path

from scripts.report_g_sched01_scheduler_revalidation import build_report


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _heartbeat(*, ok: bool) -> dict:
    return {
        "as_of": "2026-06-19",
        "status": "PASS" if ok else "FAIL",
        "errors": [] if ok else ["import heartbeat missing near 11:00"],
        "checks": [
            {"check": "import_plist_schedule_contract", "ok": True},
            {"check": "installed_import_plist_program_arguments_contract", "ok": True},
            {"check": "daily_sop_schedule_tokens", "ok": True},
        ],
    }


def test_scheduler_revalidation_retains_partial_while_paused(tmp_path: Path) -> None:
    status = _write_json(
        tmp_path / "status.json",
        {
            "labels": [
                {
                    "label": "com.example.kaspi-import-v2",
                    "loaded": False,
                    "plist_exists": True,
                    "last_exit_code": "",
                    "state": "not_loaded",
                },
                {
                    "label": "com.example.single-truth-preflight",
                    "loaded": True,
                    "plist_exists": True,
                    "last_exit_code": "1",
                    "state": "not running",
                    "purpose": "single-truth preflight validator",
                },
            ]
        },
    )
    heartbeat = _write_json(tmp_path / "heartbeat.json", _heartbeat(ok=False))

    report = build_report(
        status_report=status,
        heartbeat_report=heartbeat,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "ARMED"
    assert report["g_sched01_state"] == "PARTIAL_RETAINED"
    assert report["scheduler_contract_clean"] is True
    assert "daily_ops_intentionally_paused:1" in report["blockers"]
    assert "loaded_nonzero_last_exit:1" in report["blockers"]
    assert report["no_write_surfaces"]["launchagent_changed"] is False
    assert Path(report["json_path"]).exists()


def test_scheduler_revalidation_green_when_contract_and_runtime_are_clean(tmp_path: Path) -> None:
    status = _write_json(
        tmp_path / "status.json",
        {
            "labels": [
                {
                    "label": "com.example.kaspi-import-v2",
                    "loaded": True,
                    "plist_exists": True,
                    "last_exit_code": "0",
                    "state": "not running",
                }
            ]
        },
    )
    heartbeat = _write_json(tmp_path / "heartbeat.json", _heartbeat(ok=True))

    report = build_report(
        status_report=status,
        heartbeat_report=heartbeat,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "GREEN"
    assert report["g_sched01_state"] == "GREEN"
    assert report["blockers"] == []
