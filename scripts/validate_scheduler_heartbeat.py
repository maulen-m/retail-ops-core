#!/usr/bin/env python3
"""Validate scheduler contract + runtime heartbeat for import/waybill/report jobs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import plistlib
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"
DEFAULT_IMPORT_PLIST = PROJECT_ROOT / "config" / "com.example.kaspi-import.plist"
DEFAULT_WAYBILL_PLIST = PROJECT_ROOT / "config" / "com.example.kaspi-waybill-deadline.plist"
DEFAULT_REPORT_PLIST = PROJECT_ROOT / "config" / "com.example.kaspi-daily-ops-report.plist"
DEFAULT_IMPORT_LOG = PROJECT_ROOT / "runtime_logs" / "kaspi_import_stdout.log"
DEFAULT_WAYBILL_LOG = PROJECT_ROOT / "runtime_logs" / "kaspi_waybill_deadline_stdout.log"
DEFAULT_REPORT_LOG = PROJECT_ROOT / "runtime_logs" / "kaspi_daily_ops_report_stdout.log"
DEFAULT_CONTRACT_DOC = PROJECT_ROOT / "docs" / "ops" / "KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md"
DEFAULT_DAILY_SOP = PROJECT_ROOT / "docs" / "DAILY_SOP.md"
DEFAULT_WAYBILL_ARCHIVE_ROOT = PROJECT_ROOT / "excel_ui" / "Archive"
TIME_RE = re.compile(r"Time:\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})")


def _read_plist(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"missing plist: {path}")
    return plistlib.loads(path.read_bytes())


def _parse_import_schedule(plist_payload: dict[str, Any]) -> list[tuple[int, int]]:
    rows = plist_payload.get("StartCalendarInterval") or []
    if not isinstance(rows, list):
        return []
    result: list[tuple[int, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hour = int(row.get("Hour", -1))
        minute = int(row.get("Minute", -1))
        if hour >= 0 and minute >= 0:
            result.append((hour, minute))
    return sorted(result)


def _parse_single_schedule(plist_payload: dict[str, Any]) -> tuple[int, int] | None:
    row = plist_payload.get("StartCalendarInterval") or {}
    if not isinstance(row, dict):
        return None
    hour = int(row.get("Hour", -1))
    minute = int(row.get("Minute", -1))
    if hour < 0 or minute < 0:
        return None
    return (hour, minute)


def _load_day_times(log_path: Path, as_of: str) -> list[tuple[int, int, int]]:
    if not log_path.exists():
        return []
    content = log_path.read_text(encoding="utf-8", errors="replace")
    times: list[tuple[int, int, int]] = []
    for match in TIME_RE.finditer(content):
        day = match.group(1)
        if day != as_of:
            continue
        times.append((int(match.group(2)), int(match.group(3)), int(match.group(4))))
    return times


def _closest_delta_minutes(expected: tuple[int, int], observed: list[tuple[int, int, int]]) -> float | None:
    if not observed:
        return None
    exp_minutes = expected[0] * 60 + expected[1]
    best: float | None = None
    for hh, mm, _ss in observed:
        obs_minutes = hh * 60 + mm
        delta = abs(obs_minutes - exp_minutes)
        if best is None or delta < best:
            best = float(delta)
    return best


def _doc_contains_times(path: Path, expected: list[str]) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return all(token in text for token in expected)


def _latest_archive_input_dir(archive_root: Path, as_of: str) -> Path | None:
    if not archive_root.exists():
        return None
    candidates = sorted([p for p in archive_root.glob(f"input_{as_of}_*") if p.is_dir()])
    for candidate in reversed(candidates):
        if (candidate / "archive_manifest.json").exists():
            return candidate
    return None


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Scheduler Heartbeat",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- tolerance_minutes: `{report['tolerance_minutes']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_scheduler_heartbeat(
    *,
    as_of: str,
    output_root: Path,
    import_plist: Path,
    waybill_plist: Path,
    report_plist: Path,
    import_log: Path,
    waybill_log: Path,
    report_log: Path,
    contract_doc: Path,
    daily_sop_doc: Path,
    waybill_archive_root: Path = DEFAULT_WAYBILL_ARCHIVE_ROOT,
    tolerance_minutes: int,
    require_report_job: bool,
    strict: bool,
    now_dt: datetime | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    import_schedule_expected = [(11, 0), (16, 3)]
    waybill_schedule_expected = (18, 30)
    report_schedule_expected = (19, 10)

    import_payload = _read_plist(import_plist)
    waybill_payload = _read_plist(waybill_plist)
    report_payload = _read_plist(report_plist)

    import_schedule_actual = _parse_import_schedule(import_payload)
    waybill_schedule_actual = _parse_single_schedule(waybill_payload)
    report_schedule_actual = _parse_single_schedule(report_payload)

    checks.append(
        {
            "check": "import_plist_schedule_contract",
            "ok": import_schedule_actual == import_schedule_expected,
            "details": f"actual={import_schedule_actual} expected={import_schedule_expected}",
        }
    )
    if import_schedule_actual != import_schedule_expected:
        errors.append(f"import plist schedule drift: {import_schedule_actual} vs {import_schedule_expected}")

    checks.append(
        {
            "check": "waybill_plist_schedule_contract",
            "ok": waybill_schedule_actual == waybill_schedule_expected,
            "details": f"actual={waybill_schedule_actual} expected={waybill_schedule_expected}",
        }
    )
    if waybill_schedule_actual != waybill_schedule_expected:
        errors.append(
            f"waybill plist schedule drift: {waybill_schedule_actual} vs {waybill_schedule_expected}"
        )

    checks.append(
        {
            "check": "daily_ops_report_plist_schedule_contract",
            "ok": report_schedule_actual == report_schedule_expected,
            "details": f"actual={report_schedule_actual} expected={report_schedule_expected}",
        }
    )
    if report_schedule_actual != report_schedule_expected:
        errors.append(
            f"daily ops report plist schedule drift: {report_schedule_actual} vs {report_schedule_expected}"
        )

    schedule_tokens = ["11:00", "16:03", "18:30", "19:10"]
    for path, check_name in (
        (contract_doc, "contract_doc_schedule_tokens"),
        (daily_sop_doc, "daily_sop_schedule_tokens"),
    ):
        ok = _doc_contains_times(path, schedule_tokens)
        checks.append(
            {
                "check": check_name,
                "ok": ok,
                "details": str(path),
            }
        )
        if not ok:
            errors.append(f"schedule tokens missing in doc: {path}")

    import_times = _load_day_times(import_log, as_of)
    waybill_times = _load_day_times(waybill_log, as_of)
    report_times = _load_day_times(report_log, as_of)
    as_of_date = date.fromisoformat(as_of)
    current_dt = now_dt or datetime.now()
    same_day = as_of_date == current_dt.date()
    current_minutes = current_dt.hour * 60 + current_dt.minute

    def _slot_due(expected: tuple[int, int]) -> bool:
        if not same_day:
            return True
        expected_minutes = expected[0] * 60 + expected[1]
        return expected_minutes <= (current_minutes + int(tolerance_minutes))

    for expected in import_schedule_expected:
        if not _slot_due(expected):
            checks.append(
                {
                    "check": f"import_heartbeat_{expected[0]:02d}:{expected[1]:02d}",
                    "ok": True,
                    "details": f"not_due_yet now={current_dt.strftime('%H:%M')}",
                }
            )
            continue
        delta = _closest_delta_minutes(expected, import_times)
        ok = delta is not None and delta <= float(tolerance_minutes)
        checks.append(
            {
                "check": f"import_heartbeat_{expected[0]:02d}:{expected[1]:02d}",
                "ok": ok,
                "details": f"delta_minutes={delta}",
            }
        )
        if not ok:
            errors.append(
                f"import heartbeat missing near {expected[0]:02d}:{expected[1]:02d} for as_of={as_of}"
            )

    if not _slot_due(waybill_schedule_expected):
        waybill_delta = None
        waybill_ok = True
        waybill_details = f"not_due_yet now={current_dt.strftime('%H:%M')}"
    else:
        waybill_delta = _closest_delta_minutes(waybill_schedule_expected, waybill_times)
        archive_fallback_dir = _latest_archive_input_dir(waybill_archive_root.resolve(), as_of)
        if waybill_delta is None and archive_fallback_dir is not None:
            waybill_ok = True
            waybill_details = f"archive_fallback={archive_fallback_dir}"
        else:
            waybill_ok = waybill_delta is not None and waybill_delta <= float(tolerance_minutes)
            waybill_details = f"delta_minutes={waybill_delta}"
    checks.append(
        {
            "check": "waybill_heartbeat_18:30",
            "ok": waybill_ok,
            "details": waybill_details,
        }
    )
    if not waybill_ok:
        errors.append(f"waybill heartbeat missing near 18:30 for as_of={as_of}")

    if not _slot_due(report_schedule_expected):
        report_delta = None
        report_ok = True
        report_details = f"not_due_yet now={current_dt.strftime('%H:%M')}"
    else:
        report_delta = _closest_delta_minutes(report_schedule_expected, report_times)
        report_ok = report_delta is not None and report_delta <= float(tolerance_minutes)
        report_details = f"delta_minutes={report_delta}"
    if require_report_job:
        checks.append(
            {
                "check": "daily_ops_report_heartbeat_19:10",
                "ok": report_ok,
                "details": report_details,
            }
        )
        if not report_ok:
            errors.append(f"daily-ops-report heartbeat missing near 19:10 for as_of={as_of}")
    else:
        checks.append(
            {
                "check": "daily_ops_report_heartbeat_19:10_optional",
                "ok": True,
                "details": f"optional; observed_delta={report_delta}",
            }
        )

    ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "tolerance_minutes": int(tolerance_minutes),
        "require_report_job": bool(require_report_job),
        "checks": checks,
        "errors": errors,
        "logs": {
            "import_log": str(import_log.resolve()),
            "waybill_log": str(waybill_log.resolve()),
            "report_log": str(report_log.resolve()),
            "waybill_archive_root": str(waybill_archive_root.resolve()),
        },
        "schedules": {
            "import_actual": import_schedule_actual,
            "waybill_actual": waybill_schedule_actual,
            "report_actual": report_schedule_actual,
        },
        "heartbeat_counts": {
            "import_times": len(import_times),
            "waybill_times": len(waybill_times),
            "report_times": len(report_times),
        },
    }
    json_path = out_dir / "scheduler_heartbeat.json"
    md_path = out_dir / "scheduler_heartbeat.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("scheduler heartbeat validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate scheduler contract + heartbeat")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--import-plist", type=Path, default=DEFAULT_IMPORT_PLIST)
    parser.add_argument("--waybill-plist", type=Path, default=DEFAULT_WAYBILL_PLIST)
    parser.add_argument("--report-plist", type=Path, default=DEFAULT_REPORT_PLIST)
    parser.add_argument("--import-log", type=Path, default=DEFAULT_IMPORT_LOG)
    parser.add_argument("--waybill-log", type=Path, default=DEFAULT_WAYBILL_LOG)
    parser.add_argument("--report-log", type=Path, default=DEFAULT_REPORT_LOG)
    parser.add_argument("--waybill-archive-root", type=Path, default=DEFAULT_WAYBILL_ARCHIVE_ROOT)
    parser.add_argument("--contract-doc", type=Path, default=DEFAULT_CONTRACT_DOC)
    parser.add_argument("--daily-sop-doc", type=Path, default=DEFAULT_DAILY_SOP)
    parser.add_argument("--tolerance-minutes", type=int, default=20)
    parser.add_argument("--require-report-job", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_scheduler_heartbeat(
        as_of=str(args.as_of),
        output_root=args.output_root,
        import_plist=args.import_plist,
        waybill_plist=args.waybill_plist,
        report_plist=args.report_plist,
        import_log=args.import_log,
        waybill_log=args.waybill_log,
        report_log=args.report_log,
        waybill_archive_root=args.waybill_archive_root,
        contract_doc=args.contract_doc,
        daily_sop_doc=args.daily_sop_doc,
        tolerance_minutes=int(args.tolerance_minutes),
        require_report_job=bool(args.require_report_job),
        strict=bool(args.strict),
    )
    print(f"scheduler_heartbeat_json={report['json_path']}")
    print(f"scheduler_heartbeat_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
