#!/usr/bin/env python3
"""Run daily autopilot chain and emit exception queue artifacts."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_daily_ops_timings import build_daily_ops_timings
from scripts.build_domain_scorecards import build_domain_scorecards
from scripts.build_green_streak_tracker import build_green_streak_tracker
from scripts.build_weekly_health_scorecard import build_weekly_health_scorecard
from scripts.generate_daily_ops_report import generate_daily_ops_report
from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops
from scripts.system_doctor import run_system_doctor
from scripts.translate_transfer_ledger_to_cashflow import translate_transfer_ledger_to_cashflow
from scripts.validate_cashfloor import validate_cashfloor
from scripts.validate_daily_ops_report import validate_daily_ops_report

def _render_exceptions_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Daily Autopilot Exceptions",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- exceptions_count: `{len(payload['exceptions'])}`",
        "",
    ]
    if payload["exceptions"]:
        lines.append("## Exceptions")
        for row in payload["exceptions"]:
            lines.append(f"- `{row['step']}` rc={row['rc']} reason={row['reason']}")
    else:
        lines.append("No exceptions.")
    return "\n".join(lines) + "\n"


def run_daily_autopilot(
    *,
    project_root: Path,
    as_of: str,
    profile: str = "catch-up",
    strict: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    validation_root = root / "exports" / "validation" / "board_v10_runtime"
    daily_root = root / "exports" / "daily"
    perf_root = root / "exports" / "perf"
    health_root = root / "exports" / "health"
    exceptions_root = root / "exports" / "exceptions" / as_of
    diagnostics_root = root / "exports" / "diagnostics" / as_of
    exceptions_root.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    def record(step: str, ok: bool, rc: int, reason: str = "", meta: dict[str, Any] | None = None) -> None:
        row = {
            "step": step,
            "ok": bool(ok),
            "rc": int(rc),
            "reason": reason,
        }
        if meta:
            row["meta"] = meta
        steps.append(row)
        if not ok:
            exceptions.append({"step": step, "rc": int(rc), "reason": reason})

    try:
        daily_ops = run_kaspi_daily_ops(
            project_root=root,
            as_of=as_of,
            output_root=validation_root,
            allow_store_failures=set(),
            profile=profile,
            dry_run=True,
        )
        record(
            "run_kaspi_daily_ops",
            bool(daily_ops.get("ok", False)),
            int(daily_ops.get("exit_code", 1)),
            "daily ops summary failed" if not daily_ops.get("ok", False) else "",
            {"summary_json": daily_ops.get("summary_json")},
        )
    except Exception as exc:  # pragma: no cover - defensive
        record("run_kaspi_daily_ops", False, 1, f"exception: {exc}")
        daily_ops = {"summary_json": str(validation_root / as_of / "daily_ops_summary.json")}

    try:
        daily_report = generate_daily_ops_report(
            summary_json=Path(daily_ops["summary_json"]),
            output_dir=daily_root / as_of,
        )
        record("generate_daily_ops_report", True, 0, "", daily_report)
    except Exception as exc:
        record("generate_daily_ops_report", False, 1, f"exception: {exc}")
        daily_report = {"json_path": str(daily_root / as_of / "daily_ops_report.json")}

    try:
        report_validation = validate_daily_ops_report(Path(daily_report["json_path"]), strict=True)
        record("validate_daily_ops_report", bool(report_validation.get("ok", False)), 0 if report_validation.get("ok", False) else 1, "; ".join(report_validation.get("errors", [])))
    except Exception as exc:
        record("validate_daily_ops_report", False, 1, f"exception: {exc}")

    try:
        scorecards = build_domain_scorecards(
            project_root=root,
            as_of=as_of,
            output_root=daily_root,
            strict=True,
        )
        record("build_domain_scorecards", bool(scorecards.get("ok", False)), int(scorecards.get("exit_code", 1)))
    except Exception as exc:
        record("build_domain_scorecards", False, 1, f"exception: {exc}")

    try:
        cashfloor = validate_cashfloor(
            db_path=root / "db" / "app.db",
            as_of=as_of,
            output_root=daily_root,
            strict=True,
        )
        record("validate_cashfloor", bool(cashfloor.get("ok", False)), int(cashfloor.get("exit_code", 1)))
    except Exception as exc:
        record("validate_cashfloor", False, 1, f"exception: {exc}")

    try:
        translation = translate_transfer_ledger_to_cashflow(
            db_path=root / "db" / "app.db",
            as_of=as_of,
            output_root=daily_root,
            apply=False,
            strict=True,
        )
        record("translate_transfer_ledger_to_cashflow", bool(translation.get("ok", False)), int(translation.get("exit_code", 1)))
    except Exception as exc:
        record("translate_transfer_ledger_to_cashflow", False, 1, f"exception: {exc}")

    try:
        timings = build_daily_ops_timings(
            project_root=root,
            as_of=as_of,
            output_root=perf_root,
            profile="today-fast",
            strict=True,
        )
        record("build_daily_ops_timings", bool(timings.get("ok", False)), int(timings.get("exit_code", 1)))
    except Exception as exc:
        record("build_daily_ops_timings", False, 1, f"exception: {exc}")

    try:
        weekly = build_weekly_health_scorecard(
            as_of=as_of,
            daily_root=daily_root,
            diagnostics_root=root / "exports" / "diagnostics",
            output_root=health_root,
            strict=True,
        )
        record("build_weekly_health_scorecard", bool(weekly.get("ok", False)), int(weekly.get("exit_code", 1)))
    except Exception as exc:
        record("build_weekly_health_scorecard", False, 1, f"exception: {exc}")

    try:
        streak = build_green_streak_tracker(
            as_of=as_of,
            daily_root=daily_root,
            validation_root=root / "exports" / "validation",
            output_root=health_root / "streak",
            strict=True,
        )
        record("build_green_streak_tracker", bool(streak.get("ok", False)), int(streak.get("exit_code", 1)))
    except Exception as exc:
        record("build_green_streak_tracker", False, 1, f"exception: {exc}")

    try:
        doctor = run_system_doctor(
            project_root=root,
            as_of=as_of,
            output_dir=diagnostics_root,
            strict=True,
            entry_point="all",
        )
        record("system_doctor", bool(doctor.get("ok", False)), int(doctor.get("exit_code", 1)))
    except Exception as exc:
        record("system_doctor", False, 1, f"exception: {exc}")

    ok = len(exceptions) == 0
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "GREEN" if ok else "RED",
        "ok": ok,
        "steps": steps,
        "exceptions": exceptions,
    }

    exceptions_json = exceptions_root / "exceptions.json"
    exceptions_md = exceptions_root / "exceptions.md"
    exceptions_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    exceptions_md.write_text(_render_exceptions_md(payload), encoding="utf-8")

    return {
        "ok": ok,
        "exit_code": 0 if (ok or not strict) else 1,
        "exceptions_json": str(exceptions_json),
        "exceptions_md": str(exceptions_md),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run daily autopilot chain")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--profile", choices=["today-fast", "catch-up"], default="catch-up")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_daily_autopilot(
        project_root=args.project_root,
        as_of=args.as_of,
        profile=args.profile,
        strict=bool(args.strict),
    )
    print(f"exceptions_json={report['exceptions_json']}")
    print(f"exceptions_md={report['exceptions_md']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
