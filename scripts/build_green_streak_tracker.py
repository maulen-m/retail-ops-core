#!/usr/bin/env python3
"""Build deterministic hard-gates green streak artifact."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_as_of_date import resolve_as_of_date

DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"
DEFAULT_VALIDATION_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "health" / "streak"


def _find_gate_transcript(validation_root: Path, day_iso: str) -> str | None:
    pattern = f"board_*_{day_iso}"
    for candidate in sorted(validation_root.glob(pattern)):
        transcript = candidate / "full_gates_green_final.md"
        if transcript.exists():
            return str(transcript)
    return None


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Green Streak Tracker",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- streak_days: `{payload['streak_days']}`",
        f"- target_days: `{payload['target_days']}`",
    ]
    if payload.get("history"):
        lines.extend(["", "## History"])
        for row in payload["history"]:
            lines.append(
                f"- `{row['date']}` status={row['status']} gate_transcript={row.get('gate_transcript') or 'MISSING'}"
            )
    if payload.get("errors"):
        lines.extend(["", "## Errors"])
        for err in payload["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def build_green_streak_tracker(
    *,
    as_of: str,
    daily_root: Path = DEFAULT_DAILY_ROOT,
    validation_root: Path = DEFAULT_VALIDATION_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    target_days: int = 14,
    strict: bool = False,
) -> dict[str, Any]:
    as_of_date = date.fromisoformat(as_of)
    streak_days = 0
    history: list[dict[str, Any]] = []
    errors: list[str] = []

    cursor = as_of_date
    while True:
        day_iso = cursor.isoformat()
        report_path = Path(daily_root) / day_iso / "daily_ops_report.json"
        if not report_path.exists():
            break
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        status = str(payload.get("status") or "RED").upper()
        gate_transcript = _find_gate_transcript(Path(validation_root), day_iso)
        row = {
            "date": day_iso,
            "status": status,
            "ok": bool(payload.get("ok", False)),
            "gate_transcript": gate_transcript,
        }
        history.append(row)
        if status != "GREEN" or not bool(payload.get("ok", False)):
            break
        if gate_transcript is None:
            errors.append(f"{day_iso}: missing full_gates_green_final.md transcript link")
            break
        streak_days += 1
        cursor = cursor - timedelta(days=1)

    if not history:
        errors.append(f"no daily_ops_report.json found for as_of={as_of}")

    ok = len(errors) == 0
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "GREEN" if ok else "RED",
        "ok": ok,
        "streak_days": streak_days,
        "target_days": int(target_days),
        "target_reached": streak_days >= int(target_days),
        "history": history,
        "errors": errors,
    }

    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "green_streak.json"
    md_path = out_dir / "green_streak.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(result), encoding="utf-8")

    return {
        "ok": ok,
        "exit_code": 0 if (ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": result,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build hard-gates green streak artifact")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--daily-root", type=Path, default=None)
    parser.add_argument("--validation-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--target-days", type=int, default=14)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    daily_root = args.daily_root or (args.project_root / "exports" / "daily")
    validation_root = args.validation_root or (args.project_root / "exports" / "validation")
    output_root = args.output_root or (args.project_root / "exports" / "health" / "streak")
    resolution = resolve_as_of_date(
        project_root=args.project_root,
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=daily_root,
    )
    report = build_green_streak_tracker(
        as_of=resolution.as_of,
        daily_root=daily_root,
        validation_root=validation_root,
        output_root=output_root,
        target_days=args.target_days,
        strict=bool(args.strict),
    )
    print(f"as_of_source={resolution.source}")
    print(f"green_streak_json={report['json_path']}")
    print(f"green_streak_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
