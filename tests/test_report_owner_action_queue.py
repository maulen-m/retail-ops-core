from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_owner_action_queue import build_owner_action_queue_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["action_id", "gate_ids", "kind", "required_from_owner", "surface", "artifact", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_config(tmp_path: Path, *, queue_json: Path, queue_csv: Path) -> Path:
    config = tmp_path / "config.json"
    _write_json(
        config,
        {
            "contract_id": "OWNER_ACTION_QUEUE_V1",
            "queue_json_path": str(queue_json),
            "queue_csv_path": str(queue_csv),
            "allowed_statuses": ["WAITING_OWNER", "APPROVED"],
            "waiting_statuses": ["WAITING_OWNER"],
            "dispatch_ready_statuses": ["APPROVED"],
            "required_action_fields": ["action_id", "gate_ids", "kind", "status", "surface", "artifact"],
            "approval_forbidden_phrase": "does not authorize",
        },
    )
    return config


def _action(action_id: str, artifact: Path, *, status: str = "WAITING_OWNER") -> dict:
    return {
        "action_id": action_id,
        "gate_ids": ["G-X"],
        "kind": "approval",
        "status": status,
        "surface": "test",
        "artifact": str(artifact),
        "approval_phrase": "I approve the test. It does not authorize other writes.",
    }


def test_valid_waiting_queue_is_armed(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("ok\n", encoding="utf-8")
    queue_json = tmp_path / "queue.json"
    queue_csv = tmp_path / "queue.csv"
    _write_json(queue_json, {"actions": [_action("OA-1", artifact)]})
    _write_csv(
        queue_csv,
        [
            {
                "action_id": "OA-1",
                "gate_ids": "G-X",
                "kind": "approval",
                "required_from_owner": "approve",
                "surface": "test",
                "artifact": str(artifact),
                "status": "WAITING_OWNER",
            }
        ],
    )
    config = _write_config(tmp_path, queue_json=queue_json, queue_csv=queue_csv)

    report = build_owner_action_queue_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "ARMED"
    assert report["dispatch_state"] == "BLOCKED_WAITING_INPUT"
    assert report["waiting_count"] == 1
    assert report["blockers"] == []


def test_missing_artifact_is_red(tmp_path: Path) -> None:
    artifact = tmp_path / "missing.txt"
    queue_json = tmp_path / "queue.json"
    queue_csv = tmp_path / "queue.csv"
    _write_json(queue_json, {"actions": [_action("OA-1", artifact)]})
    _write_csv(
        queue_csv,
        [
            {
                "action_id": "OA-1",
                "gate_ids": "G-X",
                "kind": "approval",
                "required_from_owner": "approve",
                "surface": "test",
                "artifact": str(artifact),
                "status": "WAITING_OWNER",
            }
        ],
    )
    config = _write_config(tmp_path, queue_json=queue_json, queue_csv=queue_csv)

    report = build_owner_action_queue_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "RED"
    assert any("artifact missing" in blocker for blocker in report["blockers"])


def test_json_csv_id_mismatch_is_red(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("ok\n", encoding="utf-8")
    queue_json = tmp_path / "queue.json"
    queue_csv = tmp_path / "queue.csv"
    _write_json(queue_json, {"actions": [_action("OA-1", artifact)]})
    _write_csv(
        queue_csv,
        [
            {
                "action_id": "OA-2",
                "gate_ids": "G-X",
                "kind": "approval",
                "required_from_owner": "approve",
                "surface": "test",
                "artifact": str(artifact),
                "status": "WAITING_OWNER",
            }
        ],
    )
    config = _write_config(tmp_path, queue_json=queue_json, queue_csv=queue_csv)

    report = build_owner_action_queue_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "RED"
    assert any("json_csv_action_ids_match" in blocker for blocker in report["blockers"])
