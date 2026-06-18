from __future__ import annotations

import json
from pathlib import Path
import csv

from scripts.report_g_acc01_final_acceptance import build_final_acceptance_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_config(tmp_path: Path, *, signoff: Path) -> Path:
    config = tmp_path / "config.json"
    _write_json(
        config,
        {
            "contract_id": "FINAL_ACCEPTANCE_GATE_V1",
            "gate_id": "G-ACC-01",
            "gate_matrix_path": str(tmp_path / "green_gates.csv"),
            "dashboard_path": str(tmp_path / "progress-data.js"),
            "scoreboard_path": str(tmp_path / "scoreboard.csv"),
            "deferred_queue_path": str(tmp_path / "DEFERRED_QUEUE.md"),
            "owner_signoff_path": str(signoff),
            "owner_signoff_marker": "G-ACC-01 OWNER SIGNOFF",
            "post_eod_cutoff_local_time": "21:10",
            "allowed_advisory_statuses": ["GREEN", "WAIVED"],
        },
    )
    return config


def _write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "gate_id",
        "domain",
        "criterion",
        "gate_type",
        "verify_cmd",
        "expected",
        "freshness_sla",
        "current_state",
        "inef_refs",
        "od_refs",
        "depends_on",
        "phase",
        "workstream",
        "blocking",
        "owner_waivable",
        "rollback_ref",
        "evidence_ref",
    ]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(column, "") for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_dashboard(path: Path, states: dict[str, str]) -> None:
    payload = {
        "updated": "2026-06-18T21:20:00+05:00",
        "status": "EXECUTING",
        "current_phase": 5,
        "current_take": 3,
        "gates": [{"id": gate_id, "status": status} for gate_id, status in states.items()],
    }
    path.write_text("window.GP = " + json.dumps(payload, indent=2, sort_keys=True) + ";\n", encoding="utf-8")


def _write_scoreboard(path: Path, states: dict[str, str]) -> None:
    rows = ["gate_id,state,evidence,dated"]
    for gate_id, state in states.items():
        rows.append(f"{gate_id},{state},fixture,20260618")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_deferred_queue(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# DEFERRED_QUEUE",
                "",
                "| item | lane | kzt_exposure | age_days | fallback_applied | resurfaces_at / unblock |",
                "|---|---|---|---|---|---|",
                "| item-a | WS | 0 | 0 | fallback | acceptance |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_red_when_hard_gate_is_not_green(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-A", "domain": "test", "criterion": "must pass", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(tmp_path / "progress-data.js", {"G-A": "ARMED", "G-ACC-01": "PENDING"})
    _write_scoreboard(tmp_path / "scoreboard.csv", {"G-A": "GREEN", "G-ACC-01": "PENDING"})
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert "G-A=ARMED (test)" in report["hard_gate_blockers"]
    assert any("owner signoff" in blocker for blocker in report["acceptance_blockers"])


def test_green_when_all_acceptance_requirements_hold(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ADV", "domain": "metric", "criterion": "may waive", "phase": "4", "workstream": "WS", "blocking": "ADVISORY", "owner_waivable": "yes"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ADV": "WAIVED", "G-ACC-01": "PENDING"})
    _write_scoreboard(tmp_path / "scoreboard.csv", {"G-HARD": "GREEN", "G-ADV": "WAIVED", "G-ACC-01": "PENDING"})
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["hard_gate_blockers"] == []
    assert report["advisory_decisions_required"] == []
    assert report["owner_signoff_present"] is True


def test_dashboard_state_overrides_scoreboard_state(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "RED", "G-ACC-01": "PENDING"})
    _write_scoreboard(tmp_path / "scoreboard.csv", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    with Path(report["artifacts"]["scored_matrix_csv"]).open("r", encoding="utf-8", newline="") as handle:
        rows = {row["gate_id"]: row for row in csv.DictReader(handle)}
    assert rows["G-HARD"]["measured_value"] == "RED"
    assert rows["G-HARD"]["status_source"] == "dashboard"
    assert rows["G-HARD"]["scored_state"] == "BLOCKED"
