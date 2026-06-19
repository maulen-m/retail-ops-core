#!/usr/bin/env python3
"""Publish the G-ALERT-02 zero skipped-alert elapsed-window report."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "alert_zero_skip_window.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_alert02_zero_skip_window"


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(value: str | None) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_date_token(raw: str) -> date | None:
    text = raw.strip()
    try:
        if re.fullmatch(r"\d{8}", text):
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_time_token(raw: str) -> str:
    text = raw.strip()
    if re.fullmatch(r"\d{6}", text):
        return f"{text[:2]}:{text[2:4]}:{text[4:6]}"
    match = re.search(r"_(\d{6})$", text)
    if match:
        value = match.group(1)
        return f"{value[:2]}:{value[2:4]}:{value[4:6]}"
    return ""


def _date_window(start: date, days: int) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(days)]


def _post_cutoff_ok(as_of_dt: datetime, cutoff_text: str) -> tuple[bool, str]:
    hour_text, minute_text = str(cutoff_text or "21:10").split(":", 1)
    cutoff = time(hour=int(hour_text), minute=int(minute_text), tzinfo=ALMATY_TZ)
    current = as_of_dt.timetz().replace(microsecond=0)
    return current >= cutoff, f"as_of_time={current.isoformat()} cutoff={cutoff.isoformat()}"


def _line_has_skip(line: str, patterns: list[str]) -> bool:
    lower = line.lower()
    return any(pattern.lower() in lower for pattern in patterns)


def _scan_job_log(
    *,
    job: dict[str, Any],
    window: list[date],
    skipped_patterns: list[str],
) -> dict[str, Any]:
    log_path = _resolve_path(job["log_path"])
    expected_dates = {item.isoformat() for item in window}
    records: dict[str, dict[str, Any]] = {
        item: {
            "run_date": item,
            "evidence_count": 0,
            "scheduled_time_samples": [],
            "skipped_alert_count": 0,
        }
        for item in sorted(expected_dates)
    }
    blockers: list[str] = []
    skipped_outside_window = 0
    unassigned_skipped_alert_count = 0

    if not log_path.exists():
        return {
            "job_id": str(job.get("job_id") or ""),
            "log_path": str(log_path),
            "log_exists": False,
            "records": list(records.values()),
            "missing_dates": sorted(expected_dates),
            "skipped_alert_total": 0,
            "skipped_outside_window": 0,
            "unassigned_skipped_alert_count": 0,
            "blockers": [f"log_missing:{job.get('job_id')}:{log_path}"],
        }

    patterns = [re.compile(str(pattern)) for pattern in job.get("date_patterns") or []]
    pending_skipped = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _line_has_skip(line, skipped_patterns):
            pending_skipped += 1
            continue
        matched_date: date | None = None
        matched_time = ""
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            matched_date = _parse_date_token(match.group("date"))
            if "time" in match.groupdict() and match.group("time"):
                matched_time = _parse_time_token(match.group("time"))
            break
        if matched_date is None:
            continue
        date_key = matched_date.isoformat()
        if date_key in records:
            row = records[date_key]
            row["evidence_count"] += 1
            if matched_time and matched_time not in row["scheduled_time_samples"]:
                row["scheduled_time_samples"].append(matched_time)
            row["skipped_alert_count"] += pending_skipped
        else:
            skipped_outside_window += pending_skipped
        pending_skipped = 0
    unassigned_skipped_alert_count += pending_skipped

    missing_dates = [key for key, row in records.items() if int(row["evidence_count"]) <= 0]
    skipped_alert_total = sum(int(row["skipped_alert_count"]) for row in records.values())
    if missing_dates:
        blockers.extend(f"scheduled_evidence_missing:{job.get('job_id')}:{item}" for item in missing_dates)
    if skipped_alert_total:
        blockers.append(f"skipped_alert_regression:{job.get('job_id')}:{skipped_alert_total}")
    if unassigned_skipped_alert_count:
        blockers.append(f"unassigned_skipped_alert_lines:{job.get('job_id')}:{unassigned_skipped_alert_count}")

    return {
        "job_id": str(job.get("job_id") or ""),
        "log_path": str(log_path),
        "log_exists": True,
        "records": list(records.values()),
        "missing_dates": missing_dates,
        "skipped_alert_total": skipped_alert_total,
        "skipped_outside_window": skipped_outside_window,
        "unassigned_skipped_alert_count": unassigned_skipped_alert_count,
        "blockers": blockers,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-ALERT-02 Zero-Skip Window Report",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        f"Window: {report['window_start']} -> {report['window_end']}",
        "",
        "## Summary",
        "",
        f"- post_cutoff_ok: `{report['post_cutoff_ok']}` ({report['post_cutoff_details']})",
        f"- skipped_alert_total: `{report['skipped_alert_total']}`",
        f"- missing_evidence_count: `{report['missing_evidence_count']}`",
        "",
        "## Jobs",
        "",
    ]
    for job in report["jobs"]:
        lines.append(
            f"- `{job['job_id']}`: missing={len(job['missing_dates'])}, "
            f"skipped={job['skipped_alert_total']}, log_exists={job['log_exists']}"
        )
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "No Telegram send, LaunchAgent change, DB write, workbook write, Google Sheet edit, marketplace write, or external write was performed."])
    return "\n".join(lines) + "\n"


def build_zero_skip_window_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    as_of_dt = _parse_as_of(as_of)
    start = date.fromisoformat(str(config["repair_start_date"]))
    required_days = int(config.get("required_days", 7))
    window = _date_window(start, required_days)
    skipped_patterns = [str(item) for item in config.get("skipped_alert_patterns") or ["Telegram alert skipped"]]
    post_cutoff_ok, post_cutoff_details = _post_cutoff_ok(
        as_of_dt,
        str(config.get("post_eod_cutoff_local_time") or "21:10"),
    )

    job_reports = [
        _scan_job_log(job=job, window=window, skipped_patterns=skipped_patterns)
        for job in config.get("jobs") or []
    ]
    blockers: list[str] = []
    for job_report in job_reports:
        blockers.extend(str(item) for item in job_report["blockers"])
    if not post_cutoff_ok:
        blockers.append(f"post_eod_cutoff_not_met:{post_cutoff_details}")

    skipped_alert_total = sum(int(job["skipped_alert_total"]) for job in job_reports)
    missing_evidence_count = sum(len(job["missing_dates"]) for job in job_reports)
    red_blockers = [
        blocker
        for blocker in blockers
        if blocker.startswith("skipped_alert_regression:")
        or blocker.startswith("unassigned_skipped_alert_lines:")
        or blocker.startswith("log_missing:")
    ]
    if red_blockers:
        gate = "RED"
    elif blockers:
        gate = "ARMED"
    else:
        gate = "GREEN"

    output_root = output_root.expanduser().resolve()
    run_id = _now_almaty().replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")
    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "contract_id": config.get("contract_id"),
        "gate_id": config.get("gate_id", "G-ALERT-02"),
        "gate": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": _now_almaty(),
        "as_of": as_of_dt.replace(microsecond=0).isoformat(),
        "window_start": window[0].isoformat(),
        "window_end": window[-1].isoformat(),
        "required_days": required_days,
        "post_cutoff_ok": post_cutoff_ok,
        "post_cutoff_details": post_cutoff_details,
        "jobs": job_reports,
        "skipped_alert_total": skipped_alert_total,
        "missing_evidence_count": missing_evidence_count,
        "blockers": blockers,
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
        "telegram_send_performed": False,
        "launchagent_changed": False,
    }
    json_path = out_dir / "zero_skip_window_report.json"
    md_path = out_dir / "zero_skip_window_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_zero_skip_window_report(
        config_path=args.config,
        output_root=args.output_root,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
