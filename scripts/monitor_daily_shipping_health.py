#!/usr/bin/env python3
"""Monitor the canonical daily-shipping runtime without mutating business state."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "daily_shipping_runtime.json"
ALERT_ENABLE_ENV = "ENABLE_DAILY_SHIPPING_HEALTH_ALERTS"


def _expand_path(value: str, manifest: Mapping[str, Any]) -> Path:
    project_root = str(manifest.get("project_root") or PROJECT_ROOT)
    runtime_home = str(manifest.get("runtime_home") or Path.home())
    return Path(
        str(value)
        .replace("${PROJECT_ROOT}", project_root)
        .replace("${HOME}", runtime_home)
    ).expanduser()


def _local_now(now: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _latest_due_slot(
    times: list[str], *, now: datetime, grace_minutes: int
) -> tuple[datetime | None, bool]:
    candidates: list[datetime] = []
    for value in times:
        try:
            hour_text, minute_text = str(value).split(":", 1)
            slot = now.replace(
                hour=int(hour_text),
                minute=int(minute_text),
                second=0,
                microsecond=0,
            )
        except (TypeError, ValueError):
            continue
        if now >= slot + timedelta(minutes=int(grace_minutes)):
            candidates.append(slot)
    if not candidates:
        return None, True
    return max(candidates), False


def _latest_mtime(
    paths: list[Path], log_mtimes: Mapping[str, float | None]
) -> float | None:
    values = [
        float(value)
        for path in paths
        if (value := log_mtimes.get(str(path))) is not None
    ]
    return max(values) if values else None


def evaluate_daily_shipping_health(
    manifest: Mapping[str, Any],
    *,
    now: datetime,
    scheduler_states: Mapping[str, Mapping[str, Any]],
    log_mtimes: Mapping[str, float | None],
    disk_free_percent: float,
    recovery_receipt: Mapping[str, Any] | None,
    api_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate already-collected runtime facts against the canonical manifest."""

    timezone_name = str(manifest.get("timezone") or "Asia/Almaty")
    now_local = _local_now(now, timezone_name)
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    calendar_log_checks = 0
    calendar_not_due = 0

    for scheduler in manifest.get("schedulers") or []:
        label = str(scheduler.get("label") or "")
        state = dict(scheduler_states.get(label) or {})
        loaded = state.get("loaded") is True
        checks.append(
            {
                "check": f"scheduler_loaded:{label}",
                "status": "PASS" if loaded else "FAIL",
                "details": {"last_exit_status": state.get("last_exit_status")},
            }
        )
        if not loaded:
            errors.append(f"scheduler not loaded: {label}")
            continue

        health = dict(scheduler.get("health") or {})
        mode = str(health.get("mode") or "")
        stdout = _expand_path(str(scheduler.get("stdout") or ""), manifest)
        stderr = _expand_path(str(scheduler.get("stderr") or ""), manifest)
        latest_mtime = _latest_mtime([stdout, stderr], log_mtimes)

        if mode == "loaded":
            checks.append(
                {
                    "check": f"scheduler_heartbeat:{label}",
                    "status": "PASS",
                    "details": {"mode": mode},
                }
            )
            continue

        if mode == "loaded_exit_zero":
            last_exit = state.get("last_exit_status")
            clean_exit = last_exit == 0
            checks.append(
                {
                    "check": f"scheduler_heartbeat:{label}",
                    "status": "PASS" if clean_exit else "FAIL",
                    "details": {"mode": mode, "last_exit_status": last_exit},
                }
            )
            if not clean_exit:
                errors.append(f"scheduler last exit is not zero: {label}")
            continue

        if mode == "running":
            running = state.get("running") is True
            checks.append(
                {
                    "check": f"scheduler_heartbeat:{label}",
                    "status": "PASS" if running else "FAIL",
                    "details": {"mode": mode, "running": running},
                }
            )
            if not running:
                errors.append(f"required resident scheduler is not running: {label}")
            continue

        if mode == "interval_log":
            max_age = int(health.get("max_age_seconds") or 0)
            age = (
                None
                if latest_mtime is None
                else max(0.0, now_local.timestamp() - latest_mtime)
            )
            fresh = age is not None and age <= max_age
            checks.append(
                {
                    "check": f"scheduler_heartbeat:{label}",
                    "status": "PASS" if fresh else "FAIL",
                    "details": {
                        "mode": mode,
                        "age_seconds": age,
                        "max_age_seconds": max_age,
                    },
                }
            )
            if not fresh:
                errors.append(
                    f"interval scheduler heartbeat is stale or missing: {label}"
                )
            continue

        if mode == "calendar_log":
            calendar_log_checks += 1
            schedule = dict(scheduler.get("schedule") or {})
            grace = int(health.get("grace_minutes") or 0)
            due_slot, not_due = _latest_due_slot(
                list(schedule.get("times") or []),
                now=now_local,
                grace_minutes=grace,
            )
            if not_due:
                calendar_not_due += 1
                checks.append(
                    {
                        "check": f"scheduler_heartbeat:{label}",
                        "status": "NOT_DUE",
                        "details": {"mode": mode, "grace_minutes": grace},
                    }
                )
                continue
            assert due_slot is not None
            fresh = latest_mtime is not None and latest_mtime >= (
                due_slot.timestamp() - 60
            )
            checks.append(
                {
                    "check": f"scheduler_heartbeat:{label}",
                    "status": "PASS" if fresh else "FAIL",
                    "details": {
                        "mode": mode,
                        "due_slot": due_slot.isoformat(),
                        "latest_log_mtime": latest_mtime,
                    },
                }
            )
            if not fresh:
                errors.append(f"due heartbeat is missing for scheduler: {label}")
            continue

        checks.append(
            {
                "check": f"scheduler_heartbeat:{label}",
                "status": "FAIL",
                "details": {"mode": mode},
            }
        )
        errors.append(
            f"unknown scheduler health mode for {label}: {mode or '<missing>'}"
        )

    disk_floor = float(
        manifest.get("recovery", {}).get("minimum_disk_free_percent") or 0
    )
    disk_ok = float(disk_free_percent) >= disk_floor
    checks.append(
        {
            "check": "disk_free_floor",
            "status": "PASS" if disk_ok else "FAIL",
            "details": {
                "actual_percent": round(float(disk_free_percent), 3),
                "minimum_percent": disk_floor,
            },
        }
    )
    if not disk_ok:
        errors.append(
            f"disk free percent below floor: {float(disk_free_percent):.3f} < {disk_floor:.3f}"
        )

    recovery = dict(manifest.get("recovery", {}).get("automation") or {})
    recovery_state = str(recovery.get("activation_state") or "")
    if not recovery_state.startswith("active_"):
        checks.append(
            {
                "check": "recovery_freshness",
                "status": "NOT_ACTIVE",
                "details": {"activation_state": recovery_state},
            }
        )
    else:
        max_age = int(
            manifest.get("observability", {})
            .get("health_monitor", {})
            .get("recovery_max_age_seconds")
            or 0
        )
        receipt_error = str((recovery_receipt or {}).get("_error") or "")
        completed = _parse_timestamp((recovery_receipt or {}).get("completed_at_utc"))
        receipt_green = (recovery_receipt or {}).get("gate") == "GREEN"
        receipt_redacted = (recovery_receipt or {}).get(
            "credential_values_read"
        ) is False
        age = None
        if completed is not None:
            age = max(
                0.0,
                now_local.astimezone(timezone.utc).timestamp() - completed.timestamp(),
            )
        fresh = (
            not receipt_error
            and receipt_green
            and receipt_redacted
            and age is not None
            and age <= max_age
        )
        checks.append(
            {
                "check": "recovery_freshness",
                "status": "PASS" if fresh else "FAIL",
                "details": {"age_seconds": age, "max_age_seconds": max_age},
            }
        )
        if not fresh:
            if receipt_error:
                errors.append("recovery success receipt is unreadable")
            elif completed is None or not receipt_green or not receipt_redacted:
                errors.append("recovery success receipt is missing or invalid")
            else:
                errors.append("recovery success receipt is stale")

    api_total = int(api_ledger.get("total") or 0)
    api_parse_errors = int(api_ledger.get("parse_errors") or 0)
    budget = dict(manifest.get("observability", {}).get("kaspi_api_daily_budget") or {})
    warning_calls = int(budget.get("warning_calls") or 0)
    hard_calls = int(budget.get("hard_alert_calls") or 0)
    api_status = "PASS"
    if api_parse_errors:
        api_status = "FAIL"
        errors.append(f"API ledger contains malformed rows: {api_parse_errors}")
    elif api_total >= hard_calls:
        api_status = "FAIL"
        errors.append(f"Kaspi API hard budget reached: {api_total} >= {hard_calls}")
    elif api_total >= warning_calls:
        api_status = "WARN"
        warnings.append(
            f"Kaspi API warning budget reached: {api_total} >= {warning_calls}"
        )
    checks.append(
        {
            "check": "kaspi_api_daily_budget",
            "status": api_status,
            "details": {
                "total": api_total,
                "warning_calls": warning_calls,
                "hard_alert_calls": hard_calls,
                "parse_errors": api_parse_errors,
            },
        }
    )

    if errors:
        gate = "RED"
    elif warnings:
        gate = "YELLOW_API_BUDGET"
    elif calendar_log_checks and calendar_not_due == calendar_log_checks:
        gate = "YELLOW_NOT_DUE"
    else:
        gate = "GREEN"

    return {
        "schema_version": 1,
        "generated_at_utc": now_local.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "as_of": now_local.date().isoformat(),
        "timezone": timezone_name,
        "gate": gate,
        "ok": not errors,
        "scheduler_count": len(list(manifest.get("schedulers") or [])),
        "disk_free_percent": round(float(disk_free_percent), 3),
        "api_call_count": api_total,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "credential_values_read": False,
    }


def collect_scheduler_states(
    manifest: Mapping[str, Any],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    uid = os.getuid()
    for scheduler in manifest.get("schedulers") or []:
        label = str(scheduler.get("label") or "")
        completed = runner(
            ["/bin/launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        last_exit_match = re.search(r"last exit code\s*=\s*(-?\d+)", output)
        states[label] = {
            "loaded": completed.returncode == 0,
            "running": bool(re.search(r"\bstate\s*=\s*running\b", output)),
            "last_exit_status": (
                int(last_exit_match.group(1)) if last_exit_match is not None else None
            ),
        }
    return states


def collect_log_mtimes(manifest: Mapping[str, Any]) -> dict[str, float | None]:
    mtimes: dict[str, float | None] = {}
    for scheduler in manifest.get("schedulers") or []:
        for key in ("stdout", "stderr"):
            path = _expand_path(str(scheduler.get(key) or ""), manifest)
            try:
                mtimes[str(path)] = path.stat().st_mtime
            except FileNotFoundError:
                mtimes[str(path)] = None
    return mtimes


def collect_api_ledger(manifest: Mapping[str, Any], *, as_of: str) -> dict[str, Any]:
    path = _expand_path(
        f"${{PROJECT_ROOT}}/runtime/api_ledger/kaspi_api_{as_of}.jsonl",
        manifest,
    )
    total = 0
    parse_errors = 0
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw_line.strip():
                continue
            total += 1
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(row, dict):
                parse_errors += 1
    return {"path": str(path), "total": total, "parse_errors": parse_errors}


def collect_recovery_receipt(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    automation = dict(manifest.get("recovery", {}).get("automation") or {})
    if not str(automation.get("activation_state") or "").startswith("active_"):
        return None
    path = _expand_path(
        f"{automation.get('state_root', '')}/latest_success.json", manifest
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"_error": "unreadable"}
    return payload if isinstance(payload, dict) else {"_error": "not_object"}


def collect_disk_free_percent(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return (float(usage.free) / float(usage.total)) * 100.0 if usage.total else 0.0


def persist_health_report(
    report: Mapping[str, Any], *, path: Path, project_root: Path
) -> Path:
    target = Path(path).expanduser().resolve()
    repo = Path(project_root).expanduser().resolve()
    if target == repo or target.is_relative_to(repo):
        raise ValueError("health report path must be outside the repo")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    temporary = target.with_name(f".{target.name}.tmp")
    payload = (
        json.dumps(dict(report), ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, target)
    os.chmod(target, 0o600)
    return target


def should_send_failure_alert(
    state: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    now_ts: float,
    repeat_seconds: int,
) -> bool:
    if report.get("gate") != "RED":
        return False
    if state.get("last_gate") != "RED":
        return True
    last_alert = state.get("last_alert_ts")
    if not isinstance(last_alert, (int, float)):
        return True
    return float(now_ts) - float(last_alert) >= int(repeat_seconds)


def _load_local_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _send_alert_best_effort(report: Mapping[str, Any]) -> bool:
    try:
        from core.alerts.error_alerts import send_run_failure_alert

        summary = "; ".join(str(item) for item in list(report.get("errors") or [])[:4])
        return bool(
            send_run_failure_alert(
                error_message=f"DAILY_SHIPPING_HEALTH RED: {summary}",
                script_name="monitor_daily_shipping_health",
                context=(
                    f"as_of={report.get('as_of')} scheduler_count={report.get('scheduler_count')}"
                ),
            )
        )
    except Exception as exc:  # pragma: no cover - provider failure is best effort
        print(f"daily-shipping health alert failed: {exc}", file=sys.stderr)
        return False


def run_health_monitor(
    manifest: Mapping[str, Any],
    *,
    output_path: Path,
    send_alert: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now: datetime | None = None,
) -> dict[str, Any]:
    timezone_name = str(manifest.get("timezone") or "Asia/Almaty")
    now_local = _local_now(now or datetime.now(ZoneInfo(timezone_name)), timezone_name)
    runtime_home = Path(str(manifest.get("runtime_home") or Path.home())).expanduser()
    report = evaluate_daily_shipping_health(
        manifest,
        now=now_local,
        scheduler_states=collect_scheduler_states(manifest, runner=runner),
        log_mtimes=collect_log_mtimes(manifest),
        disk_free_percent=collect_disk_free_percent(runtime_home),
        recovery_receipt=collect_recovery_receipt(manifest),
        api_ledger=collect_api_ledger(manifest, as_of=now_local.date().isoformat()),
    )
    project_root = Path(str(manifest.get("project_root") or PROJECT_ROOT))
    monitor = dict(manifest.get("observability", {}).get("health_monitor") or {})
    state_path = output_path.parent / "alert_state.json"
    alert_state = _load_local_state(state_path)
    alert_sent = False
    alert_enabled = send_alert and os.environ.get(ALERT_ENABLE_ENV) == "1"
    if alert_enabled and should_send_failure_alert(
        alert_state,
        report,
        now_ts=now_local.timestamp(),
        repeat_seconds=int(monitor.get("repeat_alert_seconds") or 0),
    ):
        alert_sent = _send_alert_best_effort(report)
        if alert_sent:
            alert_state["last_alert_ts"] = now_local.timestamp()
    alert_state["last_gate"] = report["gate"]
    alert_state["last_checked_ts"] = now_local.timestamp()
    report["alert"] = {
        "requested": bool(send_alert),
        "enabled": bool(alert_enabled),
        "sent": bool(alert_sent),
    }
    persist_health_report(alert_state, path=state_path, project_root=project_root)
    persist_health_report(report, path=output_path, project_root=project_root)
    return report


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("daily shipping manifest must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Monitor canonical daily-shipping health"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--send-alert", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = _load_manifest(args.manifest)
        monitor = dict(manifest.get("observability", {}).get("health_monitor") or {})
        state_root = _expand_path(str(monitor.get("state_root") or ""), manifest)
        output_path = args.json_out or (state_root / "latest.json")
        report = run_health_monitor(
            manifest,
            output_path=output_path,
            send_alert=bool(args.send_alert),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schema_version": 1,
            "gate": "RED",
            "ok": False,
            "errors": [str(exc)],
            "warnings": [],
            "credential_values_read": False,
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}", file=sys.stderr)
        for error in report.get("errors") or []:
            print(f"ERROR: {error}", file=sys.stderr)
        for warning in report.get("warnings") or []:
            print(f"WARN: {warning}", file=sys.stderr)
    return 1 if args.strict and report.get("gate") == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
