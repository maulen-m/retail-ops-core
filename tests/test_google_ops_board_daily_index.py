from __future__ import annotations

import json
from pathlib import Path

from scripts.google_ops_board_daily_index import build_daily_index, write_daily_index


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_daily_index_summarizes_closeout_attempts_and_delivery_state(tmp_path: Path) -> None:
    workflow_root = tmp_path / "workflow_runs"
    target = "2026-04-22"
    failed = workflow_root / target / "run-red"
    green = workflow_root / target / "run-green"
    _write_json(
        failed / "closeout_report.json",
        {
            "ok": False,
            "failure_stage": "prewindow_health",
            "run_id": "run-red",
            "started_at": "2026-04-22T17:00:00+05:00",
        },
    )
    _write_json(
        green / "closeout_report.json",
        {
            "ok": True,
            "run_id": "run-green",
            "steps": [
                {"name": "delivery_send", "duration_sec": 12.5, "ok": True},
            ],
        },
    )
    _write_json(
        green / "delivery_send_report.json",
        {"ok": True, "delivery_channel": "telegram"},
    )
    index = build_daily_index(
        target_date=target,
        workflow_root=workflow_root,
        health_root=tmp_path / "health",
        source_snapshot_root=tmp_path / "source_snapshots",
        output_root=tmp_path / "daily_index",
    )

    assert index["target_date"] == target
    assert index["closeout"]["attempt_count"] == 2
    assert index["closeout"]["failure_counts_by_stage"] == {"prewindow_health": 1}
    assert index["closeout"]["latest_success_run_id"] == "run-green"
    assert index["closeout"]["stage_durations_sec"]["delivery_send"] == 12.5
    assert index["delivery"]["channel"] == "telegram"
    assert index["delivery"]["report_path"].endswith("delivery_send_report.json")


def test_write_daily_index_persists_compact_summary(tmp_path: Path) -> None:
    workflow_root = tmp_path / "workflow_runs"
    _write_json(
        workflow_root / "2026-04-22" / "run-red" / "closeout_report.json",
        {"ok": False, "failure_stage": "readiness", "run_id": "run-red"},
    )

    path = write_daily_index(
        target_date="2026-04-22",
        workflow_root=workflow_root,
        health_root=tmp_path / "health",
        source_snapshot_root=tmp_path / "source_snapshots",
        output_root=tmp_path / "daily_index",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["closeout"]["attempt_count"] == 1
    assert payload["closeout"]["failure_counts_by_stage"] == {"readiness": 1}
