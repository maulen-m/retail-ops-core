#!/usr/bin/env python3
"""Generate and validate the canonical daily-shipping runtime surfaces.

Credential values are intentionally opaque. Installed-plist checks report only
field names and structural drift, never environment values.
"""

from __future__ import annotations

import argparse
import ast
import json
import plistlib
import stat
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "daily_shipping_runtime.json"


class DailyShippingRuntimeError(RuntimeError):
    """Expected contract or generation failure."""


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DailyShippingRuntimeError(f"missing daily shipping manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DailyShippingRuntimeError(f"invalid daily shipping manifest: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DailyShippingRuntimeError("daily shipping manifest must be a JSON object")
    return payload


def _expand(value: Any, *, project_root: Path, runtime_home: Path) -> Any:
    if isinstance(value, str):
        return value.replace("${PROJECT_ROOT}", str(project_root)).replace(
            "${HOME}", str(runtime_home)
        )
    if isinstance(value, list):
        return [
            _expand(item, project_root=project_root, runtime_home=runtime_home)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _expand(item, project_root=project_root, runtime_home=runtime_home)
            for key, item in value.items()
        }
    return value


def _runtime_home(manifest: dict[str, Any]) -> Path:
    return Path(str(manifest.get("runtime_home") or Path.home())).expanduser()


def _calendar_item(value: str) -> dict[str, int]:
    hour_text, minute_text = str(value).split(":", 1)
    hour, minute = int(hour_text), int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise DailyShippingRuntimeError(f"invalid launchd calendar time: {value}")
    return {"Hour": hour, "Minute": minute}


def build_plist_payload(
    manifest: dict[str, Any],
    scheduler: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    defaults = manifest.get("defaults") or {}
    schedule = scheduler.get("schedule") or {}
    env = {"PATH": str(defaults.get("path_env") or "")}
    env.update(scheduler.get("environment_variables") or {})
    payload: dict[str, Any] = {
        "Label": str(scheduler["label"]),
        "WorkingDirectory": str(defaults.get("working_directory") or "${PROJECT_ROOT}"),
        "ProgramArguments": list(scheduler.get("program_arguments") or []),
        "RunAtLoad": bool(defaults.get("run_at_load", False)),
        "KeepAlive": bool(defaults.get("keep_alive", False)),
        "EnvironmentVariables": env,
        "StandardOutPath": str(scheduler["stdout"]),
        "StandardErrorPath": str(scheduler["stderr"]),
    }
    if schedule.get("type") == "interval":
        payload["StartInterval"] = int(schedule["seconds"])
    elif schedule.get("type") == "calendar":
        items = [_calendar_item(value) for value in schedule.get("times") or []]
        if not items:
            raise DailyShippingRuntimeError(f"calendar scheduler has no times: {scheduler['label']}")
        payload["StartCalendarInterval"] = items[0] if len(items) == 1 else items
    elif schedule.get("type") == "manual":
        pass
    else:
        raise DailyShippingRuntimeError(f"unknown schedule type for {scheduler['label']}")
    runtime_root = Path(str(manifest.get("project_root") or project_root)).expanduser()
    return _expand(
        payload,
        project_root=runtime_root,
        runtime_home=_runtime_home(manifest),
    )


def build_recovery_plist_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    automation = manifest.get("recovery", {}).get("automation") or {}
    runtime_root = Path(str(manifest.get("project_root") or PROJECT_ROOT)).expanduser()
    state_root = str(automation.get("state_root") or "")
    payload = {
        "Label": str(automation["label"]),
        "ProgramArguments": [
            "${PROJECT_ROOT}/.venv/bin/python",
            "${PROJECT_ROOT}/scripts/manage_daily_shipping_recovery.py",
            "backup",
            "--apply",
            "--json-out",
            f"{state_root}/latest_attempt.json",
        ],
        "WorkingDirectory": "${PROJECT_ROOT}",
        "EnvironmentVariables": {
            "ENABLE_SHIPPING_RECOVERY_BACKUP": "1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "StartInterval": int(automation["interval_seconds"]),
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_recovery_stdout.log",
        "StandardErrorPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_recovery_stderr.log",
    }
    return _expand(
        payload,
        project_root=runtime_root,
        runtime_home=_runtime_home(manifest),
    )


def build_recovery_retention_plist_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    automation = manifest.get("recovery", {}).get("automation") or {}
    runtime_root = Path(str(manifest.get("project_root") or PROJECT_ROOT)).expanduser()
    state_root = str(automation.get("state_root") or "")
    schedule = automation.get("retention_schedule") or {}
    payload = {
        "Label": str(automation["retention_label"]),
        "ProgramArguments": [
            "${PROJECT_ROOT}/.venv/bin/python",
            "${PROJECT_ROOT}/scripts/manage_daily_shipping_recovery.py",
            "retention",
            "--apply",
            "--json-out",
            f"{state_root}/latest_retention_attempt.json",
        ],
        "WorkingDirectory": "${PROJECT_ROOT}",
        "EnvironmentVariables": {
            "ENABLE_SHIPPING_RECOVERY_RETENTION": "1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "StartCalendarInterval": {
            "Hour": int(schedule["hour"]),
            "Minute": int(schedule["minute"]),
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_recovery_retention_stdout.log",
        "StandardErrorPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_recovery_retention_stderr.log",
    }
    return _expand(
        payload,
        project_root=runtime_root,
        runtime_home=_runtime_home(manifest),
    )


def build_log_maintenance_plist_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    maintenance = manifest.get("observability", {}).get("log_maintenance") or {}
    runtime_root = Path(str(manifest.get("project_root") or PROJECT_ROOT)).expanduser()
    schedule = maintenance.get("schedule") or {}
    payload = {
        "Label": str(maintenance["label"]),
        "ProgramArguments": [
            "${PROJECT_ROOT}/.venv/bin/python",
            "${PROJECT_ROOT}/scripts/rotate_daily_shipping_logs.py",
            "--apply",
            "--json",
        ],
        "WorkingDirectory": "${PROJECT_ROOT}",
        "EnvironmentVariables": {
            "ENABLE_DAILY_SHIPPING_LOG_MAINTENANCE": "1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "StartCalendarInterval": {
            "Hour": int(schedule["hour"]),
            "Minute": int(schedule["minute"]),
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_log_maintenance_stdout.log",
        "StandardErrorPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_log_maintenance_stderr.log",
    }
    return _expand(
        payload,
        project_root=runtime_root,
        runtime_home=_runtime_home(manifest),
    )


def build_health_monitor_plist_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    monitor = manifest.get("observability", {}).get("health_monitor") or {}
    runtime_root = Path(str(manifest.get("project_root") or PROJECT_ROOT)).expanduser()
    payload = {
        "Label": str(monitor["label"]),
        "ProgramArguments": [
            "${PROJECT_ROOT}/.venv/bin/python",
            "${PROJECT_ROOT}/scripts/monitor_daily_shipping_health.py",
            "--strict",
            "--send-alert",
            "--json",
        ],
        "WorkingDirectory": "${PROJECT_ROOT}",
        "EnvironmentVariables": {
            "ENABLE_DAILY_SHIPPING_HEALTH_ALERTS": "1",
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        "StartInterval": int(monitor["interval_seconds"]),
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_health_stdout.log",
        "StandardErrorPath": "${PROJECT_ROOT}/runtime_logs/daily_shipping_health_stderr.log",
    }
    return _expand(
        payload,
        project_root=runtime_root,
        runtime_home=_runtime_home(manifest),
    )


def _schedule_text(schedule: dict[str, Any]) -> str:
    if schedule.get("type") == "interval":
        return f"every {int(schedule['seconds'])} seconds"
    if schedule.get("type") == "manual":
        return "manual only"
    return ", ".join(str(value) for value in schedule.get("times") or [])


def render_runtime_markdown(manifest: dict[str, Any]) -> str:
    roster = manifest["store_roster"]
    watch = manifest["watch"]
    recovery = manifest["recovery"]
    lines = [
        "# Daily Shipping Runtime",
        "",
        "> Generated from `config/daily_shipping_runtime.json`. Do not edit this file by hand.",
        "",
        f"- Timezone: `{manifest['timezone']}`",
        f"- Employee-ready deadline: `{manifest['employee_ready_by_local']} Asia/Almaty`",
        f"- Active stores: `{', '.join(roster['active'])}`",
        f"- Archived stores: `{', '.join(roster['archived'])}`",
        f"- READY watch: `{watch['start_local']} to {watch['end_local']}`, every `{watch['poll_interval_seconds']}` seconds",
        f"- Stable READY debounce: `{watch['ready_debounce_seconds']}` seconds",
        f"- Auto-probable fallback: `{watch['auto_probable_local']}`",
        "- Completion proof: checkpoint + exact manifest + confirmed Telegram ledger",
        "- Retry rule: resume only the failed or incomplete stage",
        "- Writer rule: exactly one host owns this cluster",
        f"- Recovery targets: RPO `{recovery['rpo_minutes']}` minutes, RTO `{recovery['rto_minutes']}` minutes",
        f"- Recovery automation: `{recovery['automation']['activation_state']}`, every `{recovery['automation']['interval_seconds']}` seconds",
        "- Recovery retention: "
        f"`{recovery['automation']['retention_policy']['keep_within']}` dense, "
        f"`{recovery['automation']['retention_policy']['keep_daily']}` daily, "
        f"`{recovery['automation']['retention_policy']['keep_weekly']}` weekly, "
        f"`{recovery['automation']['retention_policy']['keep_monthly']}` monthly",
        "- Kaspi API call budget: warning at "
        f"`{manifest['observability']['kaspi_api_daily_budget']['warning_calls']}`, hard alert at "
        f"`{manifest['observability']['kaspi_api_daily_budget']['hard_alert_calls']}` daily calls; "
        f"state `{manifest['observability']['kaspi_api_daily_budget']['enforcement_state']}`",
        "- Runtime-log maintenance: "
        f"`{manifest['observability']['log_maintenance']['activation_state']}`, rotate above "
        f"`{manifest['observability']['log_maintenance']['max_bytes']}` bytes",
        "- Health monitor: "
        f"`{manifest['observability']['health_monitor']['activation_state']}`, every "
        f"`{manifest['observability']['health_monitor']['interval_seconds']}` seconds; "
        "manifest-driven heartbeat, disk, recovery, and API-budget checks",
        "",
        "## Workflow Stages",
        "",
    ]
    lines.extend(f"{index}. `{stage}`" for index, stage in enumerate(manifest["workflow"]["stages"], start=1))
    lines.extend(
        [
            "",
            "## Stage Execution Timeouts",
            "",
            "| Executable stage | Timeout (seconds) |",
            "|---|---:|",
        ]
    )
    for stage, timeout_seconds in manifest["workflow"]["stage_timeouts_seconds"].items():
        lines.append(f"| `{stage}` | {int(timeout_seconds)} |")
    lines.extend(
        [
            "",
            "## Scheduler Cluster",
            "",
            "| Label | Role | Schedule | Entrypoint | Canonical plist |",
            "|---|---|---|---|---|",
        ]
    )
    for scheduler in manifest["schedulers"]:
        args = list(scheduler.get("program_arguments") or [])
        entrypoint = args[1] if len(args) > 1 and str(args[0]).endswith("python") else args[0]
        lines.append(
            f"| `{scheduler['label']}` | {scheduler['role']} | `{_schedule_text(scheduler['schedule'])}` | "
            f"`{entrypoint}` | `{scheduler['source_plist']}` |"
        )
    lines.extend(
        [
            "",
            "## Credential Boundary",
            "",
            "LaunchAgent files contain credential file pointers and non-secret switches only. Secret values live in owner-only files, are never rendered here, and are never included in validator output.",
            "",
            "## Cutover Rule",
            "",
            "M5 shadow success does not authorize a live cutover. The complete scheduler cluster moves atomically only after a separate GREEN packet proves the old host is paused, no lock or active run exists, and exactly one host can advance operational state.",
            "",
        ]
    )
    return "\n".join(lines)


def write_runtime_surfaces(manifest: dict[str, Any], *, project_root: Path) -> list[str]:
    written: list[str] = []
    for scheduler in manifest.get("schedulers") or []:
        target = Path(project_root) / str(scheduler["source_plist"])
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = build_plist_payload(manifest, scheduler, project_root)
        target.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False))
        written.append(str(target))
    recovery = manifest.get("recovery", {}).get("automation") or {}
    recovery_target = Path(project_root) / str(recovery["candidate_plist"])
    recovery_target.parent.mkdir(parents=True, exist_ok=True)
    recovery_target.write_bytes(
        plistlib.dumps(build_recovery_plist_payload(manifest), fmt=plistlib.FMT_XML, sort_keys=False)
    )
    written.append(str(recovery_target))
    retention_target = Path(project_root) / str(recovery["retention_plist"])
    retention_target.parent.mkdir(parents=True, exist_ok=True)
    retention_target.write_bytes(
        plistlib.dumps(
            build_recovery_retention_plist_payload(manifest),
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )
    )
    written.append(str(retention_target))
    log_maintenance = manifest.get("observability", {}).get("log_maintenance") or {}
    log_target = Path(project_root) / str(log_maintenance["candidate_plist"])
    log_target.parent.mkdir(parents=True, exist_ok=True)
    log_target.write_bytes(
        plistlib.dumps(
            build_log_maintenance_plist_payload(manifest),
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )
    )
    written.append(str(log_target))
    health_monitor = manifest.get("observability", {}).get("health_monitor") or {}
    health_target = Path(project_root) / str(health_monitor["candidate_plist"])
    health_target.parent.mkdir(parents=True, exist_ok=True)
    health_target.write_bytes(
        plistlib.dumps(
            build_health_monitor_plist_payload(manifest),
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )
    )
    written.append(str(health_target))
    doc_path = Path(project_root) / str(manifest["generated_doc"])
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_runtime_markdown(manifest), encoding="utf-8")
    written.append(str(doc_path))
    return written


def _field_differences(expected: Any, actual: Any, prefix: str = "") -> list[str]:
    if type(expected) is not type(actual):
        return [prefix or "<root>"]
    if isinstance(expected, dict):
        differences: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in expected or key not in actual:
                differences.append(path)
            else:
                differences.extend(_field_differences(expected[key], actual[key], path))
        return differences
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [prefix or "<root>"]
        differences = []
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            differences.extend(_field_differences(expected_item, actual_item, f"{prefix}[{index}]"))
        return differences
    return [] if expected == actual else [prefix or "<root>"]


def _forbidden_env_names(payload: dict[str, Any], fragments: list[str]) -> list[str]:
    env = payload.get("EnvironmentVariables") or {}
    return sorted(
        key for key in env if any(fragment.upper() in str(key).upper() for fragment in fragments)
    )


def _without_forbidden_env(payload: dict[str, Any], fragments: list[str]) -> dict[str, Any]:
    clean = dict(payload)
    env = dict(clean.get("EnvironmentVariables") or {})
    for key in _forbidden_env_names(clean, fragments):
        env.pop(key, None)
    clean["EnvironmentVariables"] = env
    return clean


def _normalize_plist_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("KeepAlive", False)
    normalized.setdefault("RunAtLoad", False)
    intervals = normalized.get("StartCalendarInterval")
    if isinstance(intervals, list):
        normalized["StartCalendarInterval"] = sorted(
            intervals,
            key=lambda item: (int(item.get("Hour", -1)), int(item.get("Minute", -1))),
        )
    return normalized


def _literal_assignments(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def _time_parts(value: str) -> tuple[int, int]:
    hour, minute = str(value).split(":", 1)
    return int(hour), int(minute)


def _validate_store_roster(
    manifest: dict[str, Any], project_root: Path, errors: list[str]
) -> tuple[list[str], list[str]]:
    import yaml

    expected_active = sorted(str(value) for value in manifest["store_roster"]["active"])
    expected_archived = sorted(str(value) for value in manifest["store_roster"]["archived"])
    for relative in manifest.get("store_sources") or []:
        path = project_root / str(relative)
        if not path.exists():
            errors.append(f"missing store roster source: {relative}")
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        stores = payload.get("stores") or {}
        active: list[str] = []
        archived: list[str] = []
        for code, row in stores.items():
            row = row or {}
            enabled = row.get("active") if "active" in row else row.get("sync_enabled")
            if enabled is True:
                active.append(str(code))
            if enabled is False and str(row.get("lifecycle_status") or "").upper() == "ARCHIVED":
                archived.append(str(code))
        if sorted(active) != expected_active:
            drift = sorted(set(active) ^ set(expected_active))
            errors.append(f"store roster active drift in {relative}: {', '.join(drift)}")
        if sorted(archived) != expected_archived:
            drift = sorted(set(archived) ^ set(expected_archived))
            errors.append(f"store roster archived drift in {relative}: {', '.join(drift)}")
    return expected_active, expected_archived


def validate_daily_shipping_runtime(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    project_root: Path = PROJECT_ROOT,
    installed_dir: Path | None = None,
    check_installed: bool = False,
    check_repo_plists: bool = True,
    check_watch_constants: bool = True,
    check_automation_scope: bool = True,
    check_generated_doc: bool = True,
    check_store_roster: bool = True,
    check_credentials: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    project_root = Path(project_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    runtime_home = _runtime_home(manifest)
    if not runtime_home.is_absolute():
        errors.append("runtime_home must be an absolute path")
    fragments = list(manifest.get("security", {}).get("forbidden_embedded_env_name_fragments") or [])
    schedulers = list(manifest.get("schedulers") or [])
    labels = [str(item.get("label") or "") for item in schedulers]
    if len(labels) != len(set(labels)):
        errors.append("daily shipping scheduler labels are not unique")

    installed_directory = Path(installed_dir or (Path.home() / "Library" / "LaunchAgents"))
    installed_plists_scanned = 0

    for scheduler in schedulers:
        label = str(scheduler.get("label") or "")
        health = scheduler.get("health")
        if not isinstance(health, dict) or not str(health.get("mode") or ""):
            errors.append(f"scheduler missing health policy: {label}")
        else:
            mode = str(health.get("mode") or "")
            schedule = scheduler.get("schedule") or {}
            if mode not in {
                "loaded",
                "loaded_exit_zero",
                "running",
                "interval_log",
                "calendar_log",
            }:
                errors.append(f"scheduler has invalid health mode for {label}: {mode}")
            elif mode == "calendar_log":
                if schedule.get("type") != "calendar":
                    errors.append(f"calendar_log health requires calendar schedule: {label}")
                if int(health.get("grace_minutes") or 0) < 1:
                    errors.append(f"calendar_log health requires positive grace_minutes: {label}")
            elif mode == "interval_log":
                if schedule.get("type") != "interval":
                    errors.append(f"interval_log health requires interval schedule: {label}")
                max_age = int(health.get("max_age_seconds") or 0)
                if max_age < int(schedule.get("seconds") or 0):
                    errors.append(f"interval_log max_age_seconds is too small: {label}")
            elif mode == "running" and schedule.get("type") != "interval":
                errors.append(f"running health requires interval schedule: {label}")
        try:
            expected = build_plist_payload(manifest, scheduler, project_root)
        except (KeyError, ValueError, DailyShippingRuntimeError) as exc:
            errors.append(f"invalid scheduler definition for {label}: {exc}")
            continue
        forbidden = _forbidden_env_names(expected, fragments)
        if forbidden:
            errors.append(f"canonical plist embeds forbidden environment names for {label}: {', '.join(forbidden)}")
        if check_repo_plists:
            relative = Path(str(scheduler["source_plist"]))
            path = project_root / relative
            if not path.exists():
                errors.append(f"missing canonical plist for {label}: {relative}")
            else:
                actual = plistlib.loads(path.read_bytes())
                differences = _field_differences(
                    _normalize_plist_for_compare(expected),
                    _normalize_plist_for_compare(actual),
                )
                if differences:
                    errors.append(f"canonical plist drift for {label}: {', '.join(differences)}")
        if check_installed:
            path = installed_directory / f"{label}.plist"
            if not path.exists():
                errors.append(f"installed plist missing for {label}")
            else:
                actual = plistlib.loads(path.read_bytes())
                forbidden = _forbidden_env_names(actual, fragments)
                if forbidden:
                    errors.append(f"installed plist embeds forbidden environment names for {label}: {', '.join(forbidden)}")
                differences = _field_differences(
                    _normalize_plist_for_compare(expected),
                    _normalize_plist_for_compare(_without_forbidden_env(actual, fragments)),
                )
                if differences:
                    errors.append(f"installed plist drift for {label}: {', '.join(differences)}")

    if check_installed and installed_directory.is_dir():
        for path in sorted(installed_directory.glob("*.plist")):
            installed_plists_scanned += 1
            try:
                payload = plistlib.loads(path.read_bytes())
            except Exception as exc:
                errors.append(f"installed plist unreadable during global credential scan: {path.name}: {exc}")
                continue
            forbidden = _forbidden_env_names(payload, fragments)
            if forbidden:
                label = str(payload.get("Label") or path.stem)
                errors.append(
                    "installed plist globally embeds forbidden environment names for "
                    f"{label}: {', '.join(forbidden)}"
                )

    active_stores = sorted(str(value) for value in manifest.get("store_roster", {}).get("active") or [])
    archived_stores = sorted(str(value) for value in manifest.get("store_roster", {}).get("archived") or [])
    if check_store_roster:
        active_stores, archived_stores = _validate_store_roster(manifest, project_root, errors)

    if check_watch_constants:
        source = project_root / str(manifest["watch"]["constants_source"])
        if not source.exists():
            errors.append(f"missing watch constants source: {manifest['watch']['constants_source']}")
        else:
            assignments = _literal_assignments(source)
            start_hour, _ = _time_parts(manifest["watch"]["start_local"])
            end_hour, end_minute = _time_parts(manifest["watch"]["end_local"])
            auto_hour, auto_minute = _time_parts(manifest["watch"]["auto_probable_local"])
            expected_constants = {
                "EARLY_CLOSEOUT_WATCH_START_HOUR": start_hour,
                "EARLY_CLOSEOUT_WATCH_END_HOUR": end_hour,
                "EARLY_CLOSEOUT_WATCH_END_MINUTE": end_minute,
                "AUTO_PROBABLE_CLOSEOUT_HOUR": auto_hour,
                "AUTO_PROBABLE_CLOSEOUT_MINUTE": auto_minute,
                "READY_DEBOUNCE_SECONDS": int(manifest["watch"]["ready_debounce_seconds"]),
            }
            for name, expected in expected_constants.items():
                if assignments.get(name) != expected:
                    errors.append(f"watch constant drift: {name}")
        interval_schedulers = [
            item for item in schedulers if item.get("label") == "com.example.google-ops-board-closeout-watch"
        ]
        if not interval_schedulers or int(interval_schedulers[0]["schedule"].get("seconds") or 0) != int(
            manifest["watch"]["poll_interval_seconds"]
        ):
            errors.append("watch poll interval drift: StartInterval")

    if check_automation_scope:
        path = project_root / str(manifest["automation_scope_manifest"])
        try:
            automation = json.loads(path.read_text(encoding="utf-8"))
            actual_labels = list(automation["scopes"]["daily-ops"]["labels"])
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"daily-ops automation scope unreadable: {exc}")
        else:
            if actual_labels != labels:
                errors.append("daily-ops automation scope label order or membership drift")

    timeout_source = project_root / str(manifest["workflow"]["timeout_source"])
    if not timeout_source.exists():
        errors.append(f"missing workflow timeout source: {manifest['workflow']['timeout_source']}")
    else:
        timeout_assignments = _literal_assignments(timeout_source)
        expected_timeouts = manifest["workflow"].get("stage_timeouts_seconds") or {}
        actual_timeouts = timeout_assignments.get("STAGE_TIMEOUT_SECONDS")
        if actual_timeouts != expected_timeouts:
            errors.append("workflow stage timeout drift: STAGE_TIMEOUT_SECONDS")
        if not expected_timeouts or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in expected_timeouts.values()
        ):
            errors.append("workflow stage timeouts must be positive integer seconds")

    recovery = manifest.get("recovery", {}).get("automation") or {}
    try:
        recovery_interval = int(recovery["interval_seconds"])
        if recovery_interval != int(manifest["recovery"]["rpo_minutes"]) * 60:
            errors.append("recovery interval does not match the declared RPO")
        for key in ("manager", "method", "candidate_plist", "retention_plist"):
            relative = Path(str(recovery[key]))
            if not (project_root / relative).exists():
                errors.append(f"missing recovery automation surface: {relative}")
        expected_recovery = build_recovery_plist_payload(manifest)
        recovery_plist = project_root / str(recovery["candidate_plist"])
        if recovery_plist.exists():
            actual_recovery = plistlib.loads(recovery_plist.read_bytes())
            differences = _field_differences(
                _normalize_plist_for_compare(expected_recovery),
                _normalize_plist_for_compare(actual_recovery),
            )
            if differences:
                errors.append(f"recovery candidate plist drift: {', '.join(differences)}")
        expected_retention = build_recovery_retention_plist_payload(manifest)
        retention_plist = project_root / str(recovery["retention_plist"])
        if retention_plist.exists():
            actual_retention = plistlib.loads(retention_plist.read_bytes())
            differences = _field_differences(
                _normalize_plist_for_compare(expected_retention),
                _normalize_plist_for_compare(actual_retention),
            )
            if differences:
                errors.append(f"recovery retention plist drift: {', '.join(differences)}")
        if check_installed:
            installed_recovery = installed_directory / f"{recovery['label']}.plist"
            installed_retention = installed_directory / f"{recovery['retention_label']}.plist"
            activation_state = str(recovery.get("activation_state") or "")
            if activation_state == "candidate_not_installed":
                if installed_recovery.exists():
                    errors.append("recovery candidate installed before canonical activation")
                if installed_retention.exists():
                    errors.append(
                        "recovery retention candidate installed before canonical activation"
                    )
            elif activation_state.startswith("active_"):
                if not installed_recovery.exists():
                    errors.append("active recovery scheduler is not installed")
                else:
                    actual_installed = plistlib.loads(installed_recovery.read_bytes())
                    differences = _field_differences(
                        _normalize_plist_for_compare(expected_recovery),
                        _normalize_plist_for_compare(actual_installed),
                    )
                    if differences:
                        errors.append(
                            "installed recovery plist drift: " + ", ".join(differences)
                        )
                if not installed_retention.exists():
                    errors.append("active recovery retention scheduler is not installed")
                else:
                    actual_installed = plistlib.loads(installed_retention.read_bytes())
                    differences = _field_differences(
                        _normalize_plist_for_compare(expected_retention),
                        _normalize_plist_for_compare(actual_installed),
                    )
                    if differences:
                        errors.append(
                            "installed recovery retention plist drift: "
                            + ", ".join(differences)
                        )
    except (KeyError, TypeError, ValueError, DailyShippingRuntimeError) as exc:
        errors.append(f"invalid recovery automation definition: {exc}")

    log_maintenance = manifest.get("observability", {}).get("log_maintenance") or {}
    try:
        for key in ("manager", "candidate_plist"):
            relative = Path(str(log_maintenance[key]))
            if not (project_root / relative).exists():
                errors.append(f"missing log-maintenance surface: {relative}")
        warning_calls = int(manifest["observability"]["kaspi_api_daily_budget"]["warning_calls"])
        hard_calls = int(manifest["observability"]["kaspi_api_daily_budget"]["hard_alert_calls"])
        if warning_calls < 1 or hard_calls <= warning_calls:
            errors.append("Kaspi API warning/hard-alert budgets are invalid")
        if int(log_maintenance["max_bytes"]) < 1:
            errors.append("log-maintenance max_bytes must be positive")
        if int(log_maintenance["keep_archives_per_log"]) < 1:
            errors.append("log-maintenance archive count must be positive")
        expected_log = build_log_maintenance_plist_payload(manifest)
        log_plist = project_root / str(log_maintenance["candidate_plist"])
        if log_plist.exists():
            actual_log = plistlib.loads(log_plist.read_bytes())
            differences = _field_differences(
                _normalize_plist_for_compare(expected_log),
                _normalize_plist_for_compare(actual_log),
            )
            if differences:
                errors.append(f"log-maintenance candidate plist drift: {', '.join(differences)}")
        if check_installed:
            installed_log = installed_directory / f"{log_maintenance['label']}.plist"
            activation_state = str(log_maintenance.get("activation_state") or "")
            if activation_state == "candidate_not_installed" and installed_log.exists():
                errors.append("log-maintenance candidate installed before canonical activation")
            elif activation_state.startswith("active_"):
                if not installed_log.exists():
                    errors.append("active log-maintenance scheduler is not installed")
                else:
                    actual_installed = plistlib.loads(installed_log.read_bytes())
                    differences = _field_differences(
                        _normalize_plist_for_compare(expected_log),
                        _normalize_plist_for_compare(actual_installed),
                    )
                    if differences:
                        errors.append(
                            "installed log-maintenance plist drift: "
                            + ", ".join(differences)
                        )
    except (KeyError, TypeError, ValueError, DailyShippingRuntimeError) as exc:
        errors.append(f"invalid log-maintenance definition: {exc}")

    health_monitor = manifest.get("observability", {}).get("health_monitor") or {}
    try:
        for key in ("manager", "candidate_plist"):
            relative = Path(str(health_monitor[key]))
            if not (project_root / relative).exists():
                errors.append(f"missing health-monitor surface: {relative}")
        interval_seconds = int(health_monitor["interval_seconds"])
        if interval_seconds < 60:
            errors.append("health-monitor interval must be at least 60 seconds")
        recovery_max_age = int(health_monitor["recovery_max_age_seconds"])
        if recovery_max_age < int(manifest["recovery"]["rpo_minutes"]) * 60:
            errors.append("health-monitor recovery freshness is shorter than the declared RPO")
        if int(health_monitor["repeat_alert_seconds"]) < interval_seconds:
            errors.append("health-monitor repeat alert window is shorter than its interval")
        state_root = str(health_monitor["state_root"])
        if not state_root.startswith("${HOME}/Library/Application Support/"):
            errors.append("health-monitor state_root must use owner-only Application Support")
        expected_health = build_health_monitor_plist_payload(manifest)
        health_plist = project_root / str(health_monitor["candidate_plist"])
        if health_plist.exists():
            actual_health = plistlib.loads(health_plist.read_bytes())
            differences = _field_differences(
                _normalize_plist_for_compare(expected_health),
                _normalize_plist_for_compare(actual_health),
            )
            if differences:
                errors.append(f"health-monitor candidate plist drift: {', '.join(differences)}")
        if check_installed:
            installed_health = installed_directory / f"{health_monitor['label']}.plist"
            activation_state = str(health_monitor.get("activation_state") or "")
            if activation_state == "candidate_not_installed" and installed_health.exists():
                errors.append("health-monitor candidate installed before canonical activation")
            elif activation_state.startswith("active_"):
                if not installed_health.exists():
                    errors.append("active health-monitor scheduler is not installed")
                else:
                    actual_installed = plistlib.loads(installed_health.read_bytes())
                    differences = _field_differences(
                        _normalize_plist_for_compare(expected_health),
                        _normalize_plist_for_compare(actual_installed),
                    )
                    if differences:
                        errors.append(
                            "installed health-monitor plist drift: "
                            + ", ".join(differences)
                        )
    except (KeyError, TypeError, ValueError, DailyShippingRuntimeError) as exc:
        errors.append(f"invalid health-monitor definition: {exc}")

    if check_generated_doc:
        path = project_root / str(manifest["generated_doc"])
        if not path.exists():
            errors.append(f"missing generated runtime doc: {manifest['generated_doc']}")
        elif path.read_text(encoding="utf-8") != render_runtime_markdown(manifest):
            errors.append(f"generated runtime doc drift: {manifest['generated_doc']}")

    if check_credentials:
        for item in manifest.get("credential_files") or []:
            runtime_root = Path(str(manifest.get("project_root") or project_root)).expanduser()
            path = Path(
                _expand(
                    str(item["path"]),
                    project_root=runtime_root,
                    runtime_home=runtime_home,
                )
            )
            if not path.exists():
                if item.get("required", False):
                    errors.append(f"required credential file missing: {path}")
                continue
            actual_mode = stat.S_IMODE(path.stat().st_mode)
            max_mode = int(str(item.get("max_mode") or "0600"), 8)
            if actual_mode & ~max_mode:
                errors.append(f"credential file mode exceeds {item.get('max_mode', '0600')}: {path}")

    return {
        "ok": not errors,
        "gate": "GREEN" if not errors else "RED",
        "manifest": str(Path(manifest_path)),
        "project_root": str(project_root),
        "installed_checked": bool(check_installed),
        "installed_plists_scanned": installed_plists_scanned,
        "credential_values_read": False,
        "scheduler_count": len(schedulers),
        "active_stores": active_stores,
        "archived_stores": archived_stores,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and validate the daily shipping runtime contract")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--installed-dir", type=Path, default=Path.home() / "Library" / "LaunchAgents")
    parser.add_argument("--check-installed", action="store_true")
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--write", action="store_true", help="render repo plists and generated documentation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        written = write_runtime_surfaces(manifest, project_root=args.project_root) if args.write else []
        report = validate_daily_shipping_runtime(
            manifest_path=args.manifest,
            project_root=args.project_root,
            installed_dir=args.installed_dir,
            check_installed=args.check_installed,
            check_credentials=args.check_credentials,
        )
        report["written"] = written
    except DailyShippingRuntimeError as exc:
        report = {
            "ok": False,
            "gate": "RED",
            "errors": [str(exc)],
            "warnings": [],
            "credential_values_read": False,
            "written": [],
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        stream = sys.stderr
        print(f"Gate: {report['gate']}", file=stream)
        for error in report.get("errors") or []:
            print(f"ERROR: {error}", file=stream)
        for warning in report.get("warnings") or []:
            print(f"WARN: {warning}", file=stream)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
