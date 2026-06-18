#!/usr/bin/env python3
"""Validate the green-path owner action queue."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "owner_action_queue.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "owner_action_queue"


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _resolve_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _check(ok: bool, check_id: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": check_id, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _approval_text(action: dict[str, Any]) -> str:
    parts = []
    for key, value in action.items():
        if key.startswith("approval_phrase") and value:
            parts.append(str(value))
    return "\n".join(parts)


def _artifact_exists(raw: str) -> tuple[bool, str]:
    path = _resolve_path(raw)
    return path.exists(), str(path)


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Owner Action Queue Report",
        "",
        f"Gate: {report['gate']}",
        f"Dispatch state: {report['dispatch_state']}",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- action_count: {report['action_count']}",
        f"- waiting_count: {report['waiting_count']}",
        f"- dispatch_ready_count: {report['dispatch_ready_count']}",
        f"- invalid_count: {len(report['blockers'])}",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {item}" for item in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Waiting Actions", ""])
    if report["waiting_actions"]:
        lines.extend(f"- {item}" for item in report["waiting_actions"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_owner_action_queue_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    waiting_actions: list[str] = []
    ready_actions: list[str] = []

    config_path = config_path.expanduser().resolve()
    config = _load_json(config_path) if config_path.exists() else {}
    checks.append(_check(bool(config), "config_present", str(config_path)))
    checks.append(
        _check(
            config.get("contract_id") == "OWNER_ACTION_QUEUE_V1",
            "config_identity",
            f"contract={config.get('contract_id')}",
        )
    )

    queue_json_path = _resolve_path(config.get("queue_json_path"))
    queue_csv_path = _resolve_path(config.get("queue_csv_path"))
    checks.append(_check(queue_json_path.exists(), "queue_json_present", str(queue_json_path)))
    checks.append(_check(queue_csv_path.exists(), "queue_csv_present", str(queue_csv_path)))

    queue_payload = _load_json(queue_json_path) if queue_json_path.exists() else {}
    csv_rows = _load_csv(queue_csv_path) if queue_csv_path.exists() else []
    actions = queue_payload.get("actions") if isinstance(queue_payload.get("actions"), list) else []
    action_by_id = {str(action.get("action_id") or ""): action for action in actions}
    csv_ids = {str(row.get("action_id") or "") for row in csv_rows if row.get("action_id")}
    json_ids = {action_id for action_id in action_by_id if action_id}
    id_match = bool(json_ids) and json_ids == csv_ids
    checks.append(
        _check(
            id_match,
            "json_csv_action_ids_match",
            f"json={sorted(json_ids)} csv={sorted(csv_ids)}",
        )
    )

    allowed_statuses = {str(value) for value in config.get("allowed_statuses") or []}
    waiting_statuses = {str(value) for value in config.get("waiting_statuses") or []}
    ready_statuses = {str(value) for value in config.get("dispatch_ready_statuses") or []}
    required_fields = [str(value) for value in config.get("required_action_fields") or []]
    forbidden_phrase = str(config.get("approval_forbidden_phrase") or "").casefold()
    status_counts: dict[str, int] = {}

    for action in actions:
        action_id = str(action.get("action_id") or "")
        status = str(action.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1
        missing = [field for field in required_fields if not action.get(field)]
        if missing:
            blockers.append(f"{action_id}: missing fields {','.join(missing)}")
        if status not in allowed_statuses:
            blockers.append(f"{action_id}: disallowed status {status}")
        if status in waiting_statuses:
            waiting_actions.append(f"{action_id}: {status}")
        if status in ready_statuses:
            ready_actions.append(f"{action_id}: {status}")
        artifact = str(action.get("artifact") or "")
        if artifact:
            exists, resolved = _artifact_exists(artifact)
            if not exists:
                blockers.append(f"{action_id}: artifact missing {resolved}")
        if str(action.get("kind") or "") == "approval":
            text = _approval_text(action).casefold()
            if forbidden_phrase and forbidden_phrase not in text:
                blockers.append(f"{action_id}: approval phrase lacks forbidden-surface language")
        if not _as_list(action.get("gate_ids")):
            blockers.append(f"{action_id}: gate_ids empty")

    for row in checks:
        if not row["ok"]:
            blockers.append(f"{row['check']}: {row['details']}")

    gate = "RED" if blockers else ("ARMED" if waiting_actions else "GREEN")
    dispatch_state = "BLOCKED_WAITING_INPUT" if waiting_actions else "READY_OR_COMPLETE"
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "gate_id": "OWNER-ACTION-QUEUE",
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "dispatch_state": dispatch_state,
        "generated_at": _now_almaty(),
        "config_path": str(config_path),
        "queue_json_path": str(queue_json_path),
        "queue_csv_path": str(queue_csv_path),
        "action_count": len(actions),
        "csv_action_count": len(csv_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "waiting_count": len(waiting_actions),
        "dispatch_ready_count": len(ready_actions),
        "waiting_actions": waiting_actions,
        "ready_actions": ready_actions,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "owner_action_queue_report.json"
    md_path = output_root / "owner_action_queue_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_owner_action_queue_report(config_path=args.config, output_root=args.output_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Dispatch state: {report['dispatch_state']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
