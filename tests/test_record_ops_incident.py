from __future__ import annotations

import json
import subprocess
from pathlib import Path


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


def _write_config(path: Path, log_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "contract_id": "OPS_INCIDENT_TELEMETRY_V1",
                "gate_id": "G-OPS-01",
                "owner_decision_id": "OD-030",
                "log_path": str(log_path),
                "placeholder_rate_kzt_per_hour": 5000,
                "cost_basis_mark": "ASSUMED",
                "required_columns": REQUIRED_COLUMNS,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_record_ops_incident_is_dry_run_by_default_and_applies_explicitly(tmp_path: Path) -> None:
    log_path = tmp_path / "ops_incident_telemetry.csv"
    config_path = tmp_path / "config.json"
    _write_config(config_path, log_path)
    base_cmd = [
        "python3",
        "scripts/record_ops_incident.py",
        "--config",
        str(config_path),
        "--incident-id",
        "INC-TEST-001",
        "--occurred-at",
        "2026-06-18T11:39:00+05:00",
        "--incident-class",
        "daily_shipping_automation",
        "--source-surface",
        "google_ops_board_waybill_telegram",
        "--minutes-spent",
        "12",
        "--evidence-ref",
        "exports/validation/example/closeout.md",
        "--operator-notes",
        "non_pii_summary",
    ]

    dry_run = subprocess.run(base_cmd, check=True, capture_output=True, text=True)
    dry_payload = json.loads(dry_run.stdout)
    assert dry_payload["ok"] is True
    assert dry_payload["write_applied"] is False
    assert not log_path.exists()
    assert dry_payload["row"]["cost_kzt"] == "1000.00"

    applied = subprocess.run([*base_cmd, "--apply"], check=True, capture_output=True, text=True)
    apply_payload = json.loads(applied.stdout)
    assert apply_payload["write_applied"] is True
    assert "INC-TEST-001" in log_path.read_text(encoding="utf-8")
