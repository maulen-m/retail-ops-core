#!/usr/bin/env python3
"""Record an owner-action queue status update.

Default: dry-run. Apply mutates only the configured owner-action queue JSON/CSV
and writes timestamped backups next to those files.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "owner_action_queue.json"


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _resolve_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _backup(path: Path) -> str:
    backup = path.with_name(f"{path.name}.bak_{_stamp()}")
    shutil.copy2(path, backup)
    return str(backup)


def record_owner_action_status(
    *,
    config_path: Path = DEFAULT_CONFIG,
    action_id: str,
    status: str,
    decision_artifact: str = "",
    note: str = "",
    apply: bool = False,
) -> dict[str, Any]:
    config = _load_json(config_path)
    queue_json_path = _resolve_path(config.get("queue_json_path"))
    queue_csv_path = _resolve_path(config.get("queue_csv_path"))
    allowed_statuses = {str(value) for value in config.get("allowed_statuses") or []}
    if status not in allowed_statuses:
        raise ValueError(f"status {status!r} is not allowed by {config_path}")
    if decision_artifact:
        decision_path = _resolve_path(decision_artifact)
        if not decision_path.exists():
            raise FileNotFoundError(f"decision artifact does not exist: {decision_path}")

    payload = _load_json(queue_json_path)
    rows, fieldnames = _load_csv(queue_csv_path)
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("queue JSON has no actions list")
    matching_actions = [action for action in actions if str(action.get("action_id") or "") == action_id]
    matching_rows = [row for row in rows if str(row.get("action_id") or "") == action_id]
    if len(matching_actions) != 1:
        raise ValueError(f"expected exactly one JSON action for {action_id}, found {len(matching_actions)}")
    if len(matching_rows) != 1:
        raise ValueError(f"expected exactly one CSV row for {action_id}, found {len(matching_rows)}")

    updated_at = _now_almaty()
    old_status = str(matching_actions[0].get("status") or "")
    new_fields = {
        "status": status,
        "decision_artifact": decision_artifact,
        "updated_at": updated_at,
        "note": note,
    }
    matching_actions[0].update({key: value for key, value in new_fields.items() if value})
    for key in ("decision_artifact", "updated_at", "note"):
        if key not in fieldnames:
            fieldnames.append(key)
    matching_rows[0].update(new_fields)

    report: dict[str, Any] = {
        "action_id": action_id,
        "old_status": old_status,
        "new_status": status,
        "decision_artifact": decision_artifact,
        "note": note,
        "updated_at": updated_at,
        "apply": bool(apply),
        "queue_json_path": str(queue_json_path),
        "queue_csv_path": str(queue_csv_path),
        "json_backup": "",
        "csv_backup": "",
        "production_db_written": False,
        "external_writes_performed": False,
    }
    if apply:
        report["json_backup"] = _backup(queue_json_path)
        report["csv_backup"] = _backup(queue_csv_path)
        queue_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_csv(queue_csv_path, rows, fieldnames)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--decision-artifact", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    report = record_owner_action_status(
        config_path=args.config,
        action_id=args.action_id,
        status=args.status,
        decision_artifact=args.decision_artifact,
        note=args.note,
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
