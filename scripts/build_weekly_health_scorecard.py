#!/usr/bin/env python3
"""Build weekly health scorecard from daily reports and diagnostics."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"
DEFAULT_DIAGNOSTICS_ROOT = PROJECT_ROOT / "exports" / "diagnostics"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "health"


def _week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Weekly Health Scorecard",
        "",
        f"- week: `{payload['week']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- generated_at: `{payload['generated_at']}`",
        f"- days_evaluated: `{payload['days_evaluated']}`",
        f"- green_days: `{payload['green_days']}`",
        f"- red_days: `{payload['red_days']}`",
        f"- daily_green_rate_pct: `{payload['daily_green_rate_pct']}`",
        f"- avg_steps_failed: `{payload['avg_steps_failed']}`",
        f"- avg_stores_red: `{payload['avg_stores_red']}`",
        f"- green_streak_days: `{payload['green_streak_days']}`",
        f"- green_streak_target_days: `{payload['green_streak_target_days']}`",
        f"- green_streak_status: `{payload['green_streak_status']}`",
        "",
        "## Days",
    ]
    for row in payload.get("days", []):
        lines.append(
            f"- `{row['date']}`: daily={row['daily_status']} doctor={row['doctor_status']} "
            f"stores_red={row['stores_red']} steps_failed={row['steps_failed']}"
        )
    if payload.get("errors"):
        lines.extend(["", "## Errors"])
        for err in payload["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def build_weekly_health_scorecard(
    *,
    as_of: str,
    daily_root: Path = DEFAULT_DAILY_ROOT,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    strict: bool = False,
) -> dict[str, Any]:
    as_of_date = date.fromisoformat(as_of)
    week = _week_key(as_of_date)

    day_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for child in sorted(Path(daily_root).glob("*/daily_ops_report.json")):
        day_iso = child.parent.name
        try:
            day_date = date.fromisoformat(day_iso)
        except ValueError:
            continue
        if _week_key(day_date) != week:
            continue

        daily_payload = json.loads(child.read_text(encoding="utf-8"))
        diag_path = Path(diagnostics_root) / day_iso / "system_health.json"
        if not diag_path.exists():
            errors.append(f"missing system_health.json for {day_iso}: {diag_path}")
            doctor_payload = {"status": "RED", "ok": False}
        else:
            doctor_payload = json.loads(diag_path.read_text(encoding="utf-8"))

        day_rows.append(
            {
                "date": day_iso,
                "daily_status": str(daily_payload.get("status", "RED")),
                "doctor_status": str(doctor_payload.get("status", "RED")),
                "stores_red": int(daily_payload.get("stores_red", 0)),
                "steps_failed": int(daily_payload.get("steps_failed", 0)),
                "daily_ok": bool(daily_payload.get("ok", False)),
                "doctor_ok": bool(doctor_payload.get("ok", False)),
            }
        )

    if not day_rows:
        errors.append(f"no daily reports found for week {week} under {daily_root}")

    days_evaluated = len(day_rows)
    green_days = sum(1 for row in day_rows if row["daily_ok"] and row["doctor_ok"])
    red_days = days_evaluated - green_days
    avg_steps_failed = round(sum(row["steps_failed"] for row in day_rows) / days_evaluated, 3) if day_rows else 0.0
    avg_stores_red = round(sum(row["stores_red"] for row in day_rows) / days_evaluated, 3) if day_rows else 0.0
    green_rate = round((green_days / days_evaluated) * 100.0, 2) if day_rows else 0.0
    streak_target_days = 14
    streak_days = 0
    for row in sorted(day_rows, key=lambda item: item["date"], reverse=True):
        if row["daily_ok"] and row["doctor_ok"]:
            streak_days += 1
            continue
        break

    ok = (len(errors) == 0)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "week": week,
        "days_evaluated": days_evaluated,
        "green_days": green_days,
        "red_days": red_days,
        "daily_green_rate_pct": green_rate,
        "avg_steps_failed": avg_steps_failed,
        "avg_stores_red": avg_stores_red,
        "green_streak_days": streak_days,
        "green_streak_target_days": streak_target_days,
        "green_streak_status": "GREEN" if streak_days >= streak_target_days else "RED",
        "days": day_rows,
        "ok": ok,
        "errors": errors,
    }

    out_dir = Path(output_root) / "weekly" / week
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "weekly_health_scorecard.json"
    md_path = out_dir / "weekly_health_scorecard.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": ok,
        "week": week,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
        "exit_code": 0 if (ok or not strict) else 1,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build weekly health scorecard")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--daily-root", type=Path, default=DEFAULT_DAILY_ROOT)
    parser.add_argument("--diagnostics-root", type=Path, default=DEFAULT_DIAGNOSTICS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_weekly_health_scorecard(
        as_of=args.as_of,
        daily_root=args.daily_root,
        diagnostics_root=args.diagnostics_root,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"weekly_health_json={report['json_path']}")
    print(f"weekly_health_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
