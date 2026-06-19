from __future__ import annotations

import json
from pathlib import Path

from scripts.report_green_path_remaining_blockers import build_remaining_blockers_report


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_remaining_blockers_classifies_owner_time_and_cash(tmp_path: Path) -> None:
    acceptance = _write_json(
        tmp_path / "acceptance.json",
        {
            "status_counts": {"GREEN": 50, "ARMED": 16, "PARTIAL": 2, "RED": 3},
            "hard_green": 47,
            "hard_total": 61,
            "advisory_green_or_waived": 3,
            "advisory_total": 10,
            "acceptance_blockers": ["post_eod_acceptance_window", "missing owner signoff artifact"],
            "hard_gate_blockers": [
                "G-SCHED-02=PARTIAL (scheduler)",
                "G-ALERT-02=ARMED (alerting)",
                "G-PRICE-03=RED (pricing)",
                "G-RET-02=ARMED (returns)",
            ],
            "advisory_decisions_required": ["G-MET-04=ARMED (metrics)"],
            "owner_signoff_present": False,
        },
    )
    queue = _write_json(
        tmp_path / "queue.json",
        {
            "dispatch_ready_count": 0,
            "dispatch_state": "BLOCKED_WAITING_INPUT",
            "waiting_actions": ["OA-RET02: WAITING_REAL_FACT", "OA-TIMEWINDOWS: WAITING_TIME"],
        },
    )
    eod = tmp_path / "eod.txt"
    eod.write_text(
        "\n".join(
            [
                "base_floor_kzt: 2489833.23",
                "base_min_cash_kzt: 3800484.17",
                "conservative_floor_kzt: 4234749.84",
                "conservative_min_cash_kzt: 3668632.39",
                "status: FAIL",
                "reason: min_cash below threshold",
            ]
        ),
        encoding="utf-8",
    )
    daily_ops = _write_json(tmp_path / "daily_ops.json", {"ok": True, "scope": "daily-ops", "loaded_count": 0})
    heartbeat = _write_json(tmp_path / "heartbeat.json", {"status": "FAIL", "errors": ["paused heartbeat missing"]})

    report = build_remaining_blockers_report(
        acceptance_report=acceptance,
        owner_queue_report=queue,
        eod_transcript=eod,
        daily_ops_verify=daily_ops,
        scheduler_heartbeat_report=heartbeat,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "ARMED"
    assert report["status"] == "BLOCKED_WAITING_OWNER_FACTS_TIME_OR_POLICY"
    assert report["category_counts"]["cash_floor_policy"] == 1
    assert report["category_counts"]["elapsed_evidence"] == 1
    assert report["category_counts"]["owner_strategy_decision"] == 1
    assert report["category_counts"]["real_owner_fact_required"] == 2
    assert report["cashflow_po_preflight"]["conservative_min_cash_kzt"] == 3668632.39
    assert report["owner_queue"]["dispatch_ready_count"] == 0
    assert report["production_db_written"] is False
    assert Path(report["json_path"]).exists()
    assert Path(report["md_path"]).exists()


def test_remaining_blockers_can_be_ready_when_no_waits(tmp_path: Path) -> None:
    acceptance = _write_json(
        tmp_path / "acceptance.json",
        {
            "status_counts": {"GREEN": 71},
            "acceptance_blockers": [],
            "hard_gate_blockers": [],
            "advisory_decisions_required": [],
            "owner_signoff_present": True,
        },
    )
    queue = _write_json(tmp_path / "queue.json", {"dispatch_ready_count": 0, "waiting_actions": []})
    daily_ops = _write_json(tmp_path / "daily_ops.json", {"ok": True})
    heartbeat = _write_json(tmp_path / "heartbeat.json", {"status": "PASS", "errors": []})
    eod = tmp_path / "eod.txt"
    eod.write_text("status: PASS\n", encoding="utf-8")

    report = build_remaining_blockers_report(
        acceptance_report=acceptance,
        owner_queue_report=queue,
        eod_transcript=eod,
        daily_ops_verify=daily_ops,
        scheduler_heartbeat_report=heartbeat,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "GREEN"
    assert report["status"] == "READY"
