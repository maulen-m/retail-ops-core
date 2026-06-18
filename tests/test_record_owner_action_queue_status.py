from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.record_owner_action_queue_status import record_owner_action_status


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["action_id", "gate_ids", "kind", "required_from_owner", "surface", "artifact", "status"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "action_id": "OA-1",
                "gate_ids": "G-X",
                "kind": "approval",
                "required_from_owner": "approve",
                "surface": "test",
                "artifact": "artifact.txt",
                "status": "WAITING_OWNER",
            }
        )


def _write_config(tmp_path: Path) -> tuple[Path, Path, Path]:
    queue_json = tmp_path / "queue.json"
    queue_csv = tmp_path / "queue.csv"
    config = tmp_path / "config.json"
    _write_json(
        queue_json,
        {
            "actions": [
                {
                    "action_id": "OA-1",
                    "gate_ids": ["G-X"],
                    "kind": "approval",
                    "status": "WAITING_OWNER",
                    "surface": "test",
                    "artifact": "artifact.txt",
                    "approval_phrase": "does not authorize other writes",
                }
            ]
        },
    )
    _write_csv(queue_csv)
    _write_json(
        config,
        {
            "queue_json_path": str(queue_json),
            "queue_csv_path": str(queue_csv),
            "allowed_statuses": ["WAITING_OWNER", "APPROVED"],
        },
    )
    return config, queue_json, queue_csv


def test_dry_run_does_not_mutate_queue(tmp_path: Path) -> None:
    config, queue_json, queue_csv = _write_config(tmp_path)
    before_json = queue_json.read_text(encoding="utf-8")
    before_csv = queue_csv.read_text(encoding="utf-8")

    report = record_owner_action_status(
        config_path=config,
        action_id="OA-1",
        status="APPROVED",
        note="dry run",
        apply=False,
    )

    assert report["apply"] is False
    assert report["old_status"] == "WAITING_OWNER"
    assert queue_json.read_text(encoding="utf-8") == before_json
    assert queue_csv.read_text(encoding="utf-8") == before_csv


def test_apply_updates_json_and_csv_with_backups(tmp_path: Path) -> None:
    config, queue_json, queue_csv = _write_config(tmp_path)
    evidence = tmp_path / "approval.md"
    evidence.write_text("approval\n", encoding="utf-8")

    report = record_owner_action_status(
        config_path=config,
        action_id="OA-1",
        status="APPROVED",
        decision_artifact=str(evidence),
        note="approved",
        apply=True,
    )

    payload = json.loads(queue_json.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(queue_csv.open("r", encoding="utf-8")))
    assert report["apply"] is True
    assert Path(report["json_backup"]).exists()
    assert Path(report["csv_backup"]).exists()
    assert payload["actions"][0]["status"] == "APPROVED"
    assert payload["actions"][0]["decision_artifact"] == str(evidence)
    assert rows[0]["status"] == "APPROVED"
    assert rows[0]["decision_artifact"] == str(evidence)


def test_apply_requires_existing_decision_artifact(tmp_path: Path) -> None:
    config, _queue_json, _queue_csv = _write_config(tmp_path)

    with pytest.raises(FileNotFoundError):
        record_owner_action_status(
            config_path=config,
            action_id="OA-1",
            status="APPROVED",
            decision_artifact=str(tmp_path / "missing.md"),
            apply=True,
        )
