from __future__ import annotations

import json
from pathlib import Path
import csv

from scripts.report_g_acc01_final_acceptance import (
    build_final_acceptance_report as _build_final_acceptance_report,
)


def build_final_acceptance_report(**kwargs):
    kwargs.setdefault("evaluation_time", kwargs.get("as_of"))
    return _build_final_acceptance_report(**kwargs)


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
            "max_dashboard_age_hours": 24,
            "max_scoreboard_age_hours": 24,
            "max_operational_as_of_age_hours": 24,
            "allowed_dashboard_statuses": ["READY_FOR_ACCEPTANCE", "COMPLETE"],
            "dashboard_is_authority": True,
            "require_scoreboard_matrix_coverage": True,
            "require_dashboard_scoreboard_agreement": True,
            "require_green_gate_evidence": True,
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
        values = []
        for column in columns:
            if column == "freshness_sla":
                values.append(row.get(column, "1d"))
            else:
                values.append(row.get(column, ""))
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_dashboard(
    path: Path,
    states: dict[str, str],
    *,
    updated: str = "2026-06-18T21:20:00+05:00",
    status: str = "READY_FOR_ACCEPTANCE",
) -> None:
    payload = {
        "updated": updated,
        "status": status,
        "current_phase": 5,
        "current_take": 3,
        "gates": [{"id": gate_id, "status": status} for gate_id, status in states.items()],
    }
    path.write_text("window.GP = " + json.dumps(payload, indent=2, sort_keys=True) + ";\n", encoding="utf-8")


def _write_scoreboard(
    path: Path,
    states: dict[str, str],
    *,
    dated: str | dict[str, str] = "20260618",
    evidence: str | dict[str, str] = "fixture",
) -> None:
    rows = ["gate_id,state,evidence,dated"]
    for gate_id, state in states.items():
        row_evidence = evidence.get(gate_id, "") if isinstance(evidence, dict) else evidence
        row_dated = dated.get(gate_id, "") if isinstance(dated, dict) else dated
        rows.append(f"{gate_id},{state},{row_evidence},{row_dated}")
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


def test_red_when_dashboard_source_is_stale(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-18T21:20:00+05:00",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260620_2110",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-20T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["source_freshness"]["dashboard"]["ok"] is False
    assert report["source_freshness"]["scoreboard"]["ok"] is True
    assert report["status_counts_current"] is False
    assert report["status_counts_label"] == "STALE_OR_UNRECONCILED_INPUT_REPLAY"
    assert any("dashboard_source_freshness" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_scoreboard_source_is_stale(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-20 21:20 +05",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_212000",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-20T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["source_freshness"]["dashboard"]["ok"] is True
    assert report["source_freshness"]["scoreboard"]["ok"] is False
    assert any("scoreboard_source_freshness" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_source_timestamp_is_future_or_invalid(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-20T21:20:01+05:00",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="not-a-timestamp",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-20T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["source_freshness"]["dashboard"]["error"] == "timestamp is in the future"
    assert report["source_freshness"]["scoreboard"]["error"] == "timestamp is missing or invalid"


def test_source_freshness_exact_boundary_passes(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-18T21:20:00+05:00",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_212000",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-19T21:20:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["source_freshness_ok"] is True
    assert report["status_counts_current"] is True
    assert report["status_counts_label"] == "CURRENT_RECONCILED_INPUTS"
    assert report["source_freshness"]["dashboard"]["age_hours"] == 24.0
    assert report["source_freshness"]["scoreboard"]["age_hours"] == 24.0


def test_red_when_scoreboard_does_not_cover_matrix(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-A", "domain": "test", "criterion": "a", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-B", "domain": "test", "criterion": "b", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-A": "GREEN", "G-B": "GREEN", "G-ACC-01": "PENDING"},
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-A": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_2120",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["scoreboard_missing_gate_ids"] == ["G-B"]
    assert any("scoreboard_matrix_coverage" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_dashboard_and_scoreboard_disagree(tmp_path: Path) -> None:
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
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "RED", "G-ACC-01": "PENDING"},
        dated="20260618_2120",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["dashboard_scoreboard_disagreements"] == [
        {"dashboard": "GREEN", "gate_id": "G-HARD", "scoreboard": "RED"}
    ]
    assert any("dashboard_scoreboard_agreement" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_dashboard_is_still_executing(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        status="EXECUTING",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_2120",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("dashboard_terminal_status" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_green_gate_lacks_scoreboard_evidence(tmp_path: Path) -> None:
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
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_2120",
        evidence="",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["green_gates_missing_evidence"] == ["G-HARD"]
    assert any("green_gate_evidence_complete" in blocker for blocker in report["acceptance_blockers"])


def test_red_when_green_gate_evidence_exceeds_its_freshness_sla(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "freshness_sla": "1d", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "freshness_sla": "1d", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-20T21:20:00+05:00",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated={"G-HARD": "20260618_2120", "G-ACC-01": "20260620_2120"},
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-20T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["green_gate_freshness_failures"] == [
        {
            "age_hours": 48.0,
            "dated": "20260618_2120",
            "error": "evidence exceeds freshness_sla",
            "freshness_sla": "1d",
            "gate_id": "G-HARD",
            "max_age_hours": 24.0,
        }
    ]
    assert any("green_gate_freshness_sla" in blocker for blocker in report["acceptance_blockers"])


def test_fresh_extra_final_scoreboard_row_cannot_mask_stale_gate_evidence(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "freshness_sla": "1d", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "freshness_sla": "1d", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        updated="2026-06-20T21:20:00+05:00",
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING", "G-EXTRA": "GREEN"},
        dated={
            "G-HARD": "20260618_2120",
            "G-ACC-01": "20260620_2110",
            "G-EXTRA": "20260620_2120",
        },
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-20T21:20:00+05:00",
    )

    assert report["source_freshness"]["scoreboard"]["ok"] is True
    assert report["gate"] == "RED"
    assert [row["gate_id"] for row in report["provenance"]["green_gate_freshness_failures"]] == ["G-HARD"]


def test_invalid_source_states_cannot_normalize_into_agreement(tmp_path: Path) -> None:
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
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ACC-01": "BOGUS"},
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "ALSO-BOGUS"},
        dated="20260618_2120",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["invalid_dashboard_states"] == [
        {"gate_id": "G-ACC-01", "raw_state": "BOGUS"}
    ]
    assert report["provenance"]["invalid_scoreboard_states"] == [
        {"gate_id": "G-ACC-01", "raw_state": "ALSO-BOGUS"}
    ]
    assert any("source_gate_states_valid" in blocker for blocker in report["acceptance_blockers"])


def test_historical_replay_cannot_issue_operational_green(tmp_path: Path) -> None:
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
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated="20260618_2120",
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = _build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
        evaluation_time="2026-06-20T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["evaluation_mode"] == "HISTORICAL_REPLAY"
    assert report["status_counts_current"] is False
    assert report["status_counts_label"] == "HISTORICAL_REPLAY_RECONCILED_INPUTS"
    assert any("operational_as_of_window" in blocker for blocker in report["acceptance_blockers"])


def test_na_freshness_still_rejects_future_evidence(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "freshness_sla": "n/a", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "freshness_sla": "n/a", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING"},
        dated={"G-HARD": "20990101", "G-ACC-01": "20260618_2120"},
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["green_gate_freshness_failures"][0]["error"] == (
        "evidence timestamp is in the future"
    )


def test_advisory_waiver_requires_current_evidence(tmp_path: Path) -> None:
    signoff = tmp_path / "OWNER_ACCEPTANCE_SIGNOFF.md"
    signoff.write_text("G-ACC-01 OWNER SIGNOFF\n", encoding="utf-8")
    config = _write_config(tmp_path, signoff=signoff)
    _write_matrix(
        tmp_path / "green_gates.csv",
        [
            {"gate_id": "G-HARD", "domain": "test", "criterion": "must pass", "freshness_sla": "1d", "phase": "1", "workstream": "WS", "blocking": "HARD"},
            {"gate_id": "G-ADV", "domain": "test", "criterion": "may waive", "freshness_sla": "1d", "phase": "4", "workstream": "WS", "blocking": "ADVISORY"},
            {"gate_id": "G-ACC-01", "domain": "acceptance", "criterion": "accept", "freshness_sla": "1d", "phase": "5", "workstream": "WS", "blocking": "HARD"},
        ],
    )
    _write_dashboard(
        tmp_path / "progress-data.js",
        {"G-HARD": "GREEN", "G-ADV": "WAIVED", "G-ACC-01": "PENDING"},
    )
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ADV": "WAIVED", "G-ACC-01": "PENDING"},
        dated={"G-HARD": "20260618_2120", "G-ADV": "20200618_2120", "G-ACC-01": "20260618_2120"},
        evidence={"G-HARD": "fixture", "G-ADV": "", "G-ACC-01": "fixture"},
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["provenance"]["green_gates_missing_evidence"] == ["G-ADV"]
    assert [row["gate_id"] for row in report["provenance"]["green_gate_freshness_failures"]] == ["G-ADV"]


def test_malformed_final_scoreboard_timestamp_fails_closed(tmp_path: Path) -> None:
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
    _write_dashboard(tmp_path / "progress-data.js", {"G-HARD": "GREEN", "G-ACC-01": "PENDING"})
    _write_scoreboard(
        tmp_path / "scoreboard.csv",
        {"G-HARD": "GREEN", "G-ACC-01": "PENDING", "G-EXTRA": "GREEN"},
        dated={"G-HARD": "20260618_2120", "G-ACC-01": "20260618_2120", "G-EXTRA": "malformed"},
    )
    _write_deferred_queue(tmp_path / "DEFERRED_QUEUE.md")

    report = build_final_acceptance_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T21:20:00+05:00",
    )

    assert report["gate"] == "RED"
    assert report["source_freshness"]["scoreboard"]["error"] == "timestamp is missing or invalid"
    assert any("scoreboard_source_freshness" in blocker for blocker in report["acceptance_blockers"])
