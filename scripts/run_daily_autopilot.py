#!/usr/bin/env python3
"""Run daily autopilot chain and emit exception queue artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from scripts.resolve_as_of_date import resolve_as_of_date
from scripts.system_doctor import run_system_doctor
from scripts.translate_transfer_ledger_to_cashflow import translate_transfer_ledger_to_cashflow
from scripts.validate_cashfloor import validate_cashfloor
from scripts.validate_daily_ops_report import validate_daily_ops_report

EXCEPTION_POLICY: dict[str, dict[str, str]] = {
    "run_kaspi_daily_ops": {
        "domain": "execution",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Inspect daily ops summary and rerun run_kaspi_daily_ops with strict profile.",
    },
    "generate_daily_ops_report": {
        "domain": "governance",
        "severity": "high",
        "owner": "ops-codex",
        "recommended_action": "Regenerate daily_ops_report and validate schema before publication.",
    },
    "validate_daily_ops_report": {
        "domain": "governance",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Fix report schema violations and rerun strict report validator.",
    },
    "build_domain_scorecards": {
        "domain": "domain",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Resolve failing domain scorecards before decisions or publish.",
    },
    "validate_cashfloor": {
        "domain": "cashflow",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Fix cashfloor breach and rerun strict cashfloor validator.",
    },
    "translate_transfer_ledger_to_cashflow": {
        "domain": "cashflow",
        "severity": "high",
        "owner": "ops-codex",
        "recommended_action": "Repair transfer-ledger translation errors and rerun strict translation.",
    },
    "build_daily_ops_timings": {
        "domain": "execution",
        "severity": "high",
        "owner": "ops-codex",
        "recommended_action": "Investigate timing/parity failures and rerun timing benchmark.",
    },
    "build_weekly_health_scorecard": {
        "domain": "governance",
        "severity": "medium",
        "owner": "ops-codex",
        "recommended_action": "Repair weekly health scorecard inputs and rebuild artifacts.",
    },
    "build_green_streak_tracker": {
        "domain": "governance",
        "severity": "high",
        "owner": "ops-codex",
        "recommended_action": "Restore missing day reports/gate transcripts and rerun streak tracker.",
    },
    "system_doctor": {
        "domain": "diagnostics",
        "severity": "critical",
        "owner": "ops-codex",
        "recommended_action": "Fix blocked layer checks and rerun system_doctor --strict.",
    },
}


def _exception_meta(step: str) -> dict[str, str]:
    base = {
        "domain": "operations",
        "severity": "high",
        "owner": "ops-codex",
        "recommended_action": "Inspect step failure and rerun strict gates.",
    }
    base.update(EXCEPTION_POLICY.get(step, {}))
    return base


def _collect_evidence_paths(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    paths: list[str] = []
    for value in meta.values():
        if isinstance(value, str) and ("/" in value or value.endswith(".json") or value.endswith(".md")):
            paths.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and ("/" in item or item.endswith(".json") or item.endswith(".md")):
                    paths.append(item)
    deduped: list[str] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def _build_exception_row(
    *,
    index: int,
    step: str,
    rc: int,
    reason: str,
    meta: dict[str, Any] | None,
    fallback_evidence: str,
) -> dict[str, Any]:
    policy = _exception_meta(step)
    evidence_paths = _collect_evidence_paths(meta)
    if not evidence_paths:
        evidence_paths = [fallback_evidence]
    return {
        "id": f"{step}:{int(rc)}:{index}",
        "step": step,
        "domain": policy["domain"],
        "severity": policy["severity"],
        "owner": policy["owner"],
        "recommended_action": policy["recommended_action"],
        "evidence_paths": evidence_paths,
        "rc": int(rc),
        "reason": str(reason or "unknown failure"),
    }


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
            lines.append(
                f"- `{row['id']}` `{row['step']}` severity={row['severity']} owner={row['owner']} "
                f"rc={row['rc']} reason={row['reason']}"
            )
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
            exceptions.append(
                _build_exception_row(
                    index=len(exceptions) + 1,
                    step=step,
                    rc=int(rc),
                    reason=reason,
                    meta=meta,
                    fallback_evidence=str(root / "exports" / "validation" / "board_v10_runtime" / as_of / "daily_ops_summary.md"),
                )
            )

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
        "schema_version": "v1",
        "steps": steps,
        "exceptions": exceptions,
        "critical_count": sum(1 for row in exceptions if str(row.get("severity", "")).lower() == "critical"),
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
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--profile", choices=["today-fast", "catch-up"], default="catch-up")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    resolution = resolve_as_of_date(
        project_root=args.project_root,
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.project_root / "exports" / "daily",
    )
    report = run_daily_autopilot(
        project_root=args.project_root,
        as_of=resolution.as_of,
        profile=args.profile,
        strict=bool(args.strict),
    )
    print(f"as_of_source={resolution.source}")
    print(f"exceptions_json={report['exceptions_json']}")
    print(f"exceptions_md={report['exceptions_md']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
