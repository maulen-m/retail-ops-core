from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_incident_telemetry import build_incident_telemetry_report


REQUIRED_COLUMNS = [
    "incident_id",
    "occurred_at",
    "incident_class",
    "source_surface",
    "severity",
    "resolution_status",
    "minutes_spent",
    "cost_rate_kzt_per_hour",
    "cost_basis_mark",
    "cost_kzt",
    "owner_decision_id",
    "gate_id",
    "evidence_ref",
    "operator_notes",
]


def _write_config(path: Path, *, log_path: Path, started_at: str) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "OPS_INCIDENT_TELEMETRY_V1",
                "gate_id": "G-OPS-01",
                "owner_decision_id": "OD-030",
                "inefficiency_id": "INEF-17",
                "telemetry_started_at": started_at,
                "log_path": str(log_path),
                "placeholder_rate_kzt_per_hour": 5000,
                "cost_basis_mark": "ASSUMED",
                "minimum_collection_days_before_labor_ranking": 30,
                "labor_ranking_allowed_before_maturity": False,
                "required_columns": REQUIRED_COLUMNS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_owner_decisions(path: Path) -> None:
    path.write_text(
        """
decisions:
  - id: OD-030
    title: operator_labor_valuation
    answer: RECOMMENDED
    params: { placeholder_rate_kzt_per_hour: 5000, marked: ASSUMED, telemetry: mandatory_now, revisit: acceptance_with_30d_data }
""".lstrip(),
        encoding="utf-8",
    )


def _write_log(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "incident_id": "INC-20260618-113900-daily-shipping",
        "occurred_at": "2026-06-18T11:39:00+05:00",
        "incident_class": "daily_shipping_automation",
        "source_surface": "google_ops_board_waybill_telegram",
        "severity": "medium",
        "resolution_status": "resolved",
        "minutes_spent": "18",
        "cost_rate_kzt_per_hour": "5000",
        "cost_basis_mark": "ASSUMED",
        "cost_kzt": "1500.00",
        "owner_decision_id": "OD-030",
        "gate_id": "G-OPS-01",
        "evidence_ref": "exports/validation/example/closeout.md",
        "operator_notes": "non_pii_summary",
    }
    row.update(overrides)
    return row


def test_report_armed_with_empty_schema_log(tmp_path: Path) -> None:
    log_path = tmp_path / "ops_incident_telemetry.csv"
    config_path = tmp_path / "ops_incident_telemetry.json"
    decisions_path = tmp_path / "decisions.yaml"
    _write_log(log_path, [])
    _write_config(config_path, log_path=log_path, started_at="2026-06-18T11:39:00+05:00")
    _write_owner_decisions(decisions_path)

    report = build_incident_telemetry_report(
        as_of="2026-06-18",
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "ARMED"
    assert report["ok"] is True
    assert report["first_real_incident_required"] is True
    assert report["labor_ranking_allowed"] is False


def test_report_green_after_30d_with_valid_cost_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "ops_incident_telemetry.csv"
    config_path = tmp_path / "ops_incident_telemetry.json"
    decisions_path = tmp_path / "decisions.yaml"
    _write_log(log_path, [_row()])
    _write_config(config_path, log_path=log_path, started_at="2026-06-01T00:00:00+05:00")
    _write_owner_decisions(decisions_path)

    report = build_incident_telemetry_report(
        as_of="2026-06-30",
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "GREEN"
    assert report["labor_ranking_allowed"] is True
    assert report["row_count_trailing_30d"] == 1


def test_report_red_when_cost_line_does_not_match_minutes(tmp_path: Path) -> None:
    log_path = tmp_path / "ops_incident_telemetry.csv"
    config_path = tmp_path / "ops_incident_telemetry.json"
    decisions_path = tmp_path / "decisions.yaml"
    _write_log(log_path, [_row(cost_kzt="999.00")])
    _write_config(config_path, log_path=log_path, started_at="2026-06-18T11:39:00+05:00")
    _write_owner_decisions(decisions_path)

    report = build_incident_telemetry_report(
        as_of="2026-06-18",
        config_path=config_path,
        owner_decisions_path=decisions_path,
        output_root=tmp_path / "out",
    )

    assert report["gate"] == "RED"
    assert report["ok"] is False
    assert "cost_kzt must equal 1500.00" in report["row_errors"][0]["errors"]
