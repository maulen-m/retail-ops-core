#!/usr/bin/env python3
"""Validate that help/inspection commands do not write generated data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_HELP_COMMANDS = [
    {
        "id": "generate_po_dashboard_data_help",
        "command": [sys.executable, "scripts/generate_po_dashboard_data.py", "--help"],
        "monitored_paths": [
            "exports/po_dashboard_data.json",
            "exports/demand_diagnostics.csv",
            "exports/stock_rebuild_diagnostics.csv",
            "exports/po_supplier_export",
            "exports/po_supplier_summary",
        ],
        "required_stdout": "usage:",
        "forbidden_stdout": "Generated:",
    }
]


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_path(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_file():
        stat = path.stat()
        return {
            "kind": "file",
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "sha256": _digest_file(path),
        }
    rows = []
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = child.relative_to(path).as_posix()
        rows.append(
            {
                "path": rel,
                "size": child.stat().st_size,
                "sha256": _digest_file(child),
            }
        )
    stat = path.stat()
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "kind": "dir",
        "mtime_ns": stat.st_mtime_ns,
        "file_count": len(rows),
        "sha256": digest,
    }


def _snapshot(paths: list[str]) -> dict[str, dict[str, Any] | None]:
    return {path: _snapshot_path(PROJECT_ROOT / path) for path in paths}


def validate_help_commands(*, strict: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    checked: list[str] = []
    details: list[dict[str, Any]] = []

    for spec in DEFAULT_HELP_COMMANDS:
        command_id = spec["id"]
        monitored_paths = list(spec["monitored_paths"])
        before = _snapshot(monitored_paths)
        completed = subprocess.run(
            list(spec["command"]),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        after = _snapshot(monitored_paths)
        checked.append(command_id)

        if completed.returncode != 0:
            errors.append(f"{command_id} exited {completed.returncode}")
        required_stdout = str(spec.get("required_stdout") or "")
        if required_stdout and required_stdout not in completed.stdout:
            errors.append(f"{command_id} stdout missing required text: {required_stdout}")
        forbidden_stdout = str(spec.get("forbidden_stdout") or "")
        if forbidden_stdout and forbidden_stdout in completed.stdout:
            errors.append(f"{command_id} stdout contains forbidden text: {forbidden_stdout}")
        if after != before:
            changed = [path for path in monitored_paths if before.get(path) != after.get(path)]
            errors.append(f"{command_id} modified monitored paths: {', '.join(changed)}")

        details.append(
            {
                "id": command_id,
                "returncode": completed.returncode,
                "monitored_paths": monitored_paths,
                "stdout_preview": completed.stdout[:500],
                "stderr_preview": completed.stderr[:500],
                "changed": [path for path in monitored_paths if before.get(path) != after.get(path)],
            }
        )

    return {
        "ok": not errors,
        "strict": strict,
        "checked_count": len(checked),
        "checked": checked,
        "errors": errors,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that help commands do not write data")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate_help_commands(strict=args.strict)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["ok"]:
        print("NO_HELP_COMMAND_WRITES PASS")
        print(f"checked_count={report['checked_count']}")
    else:
        print("NO_HELP_COMMAND_WRITES FAIL")
        for err in report["errors"]:
            print(f"- {err}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

