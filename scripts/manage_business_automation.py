#!/usr/bin/env python3
"""Pause, verify, and resume repo-owned business LaunchAgents.

The command is dry-run by default. Any launchd mutation requires both --apply and
ENABLE_BUSINESS_AUTOMATION_CONTROL=1.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "business_automation_manifest.json"
DEFAULT_EVIDENCE_ROOT = PROJECT_ROOT / "exports" / "automation_control"
CONTROL_ENV_GATE = "ENABLE_BUSINESS_AUTOMATION_CONTROL"
VERSION = "2026.05.13"

CommandRunner = Callable[[list[str]], dict[str, Any]]


@dataclass(frozen=True)
class LabelEntry:
    label: str
    plist: Path
    group: str
    purpose: str
    risk: tuple[str, ...]


class AutomationControlError(RuntimeError):
    """Expected operator-facing failure."""


def _now_almaty() -> datetime:
    return datetime.now(ZoneInfo("Asia/Almaty"))


def _expand_path(raw: str) -> Path:
    value = raw.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
    return Path(value).expanduser()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    if not path.exists():
        raise AutomationControlError(f"missing automation manifest: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AutomationControlError(f"invalid automation manifest JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AutomationControlError(f"automation manifest must be an object: {path}")
    return payload


def _entries_by_label(manifest: dict[str, Any]) -> dict[str, LabelEntry]:
    entries: dict[str, LabelEntry] = {}
    for raw in manifest.get("labels") or []:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        entries[label] = LabelEntry(
            label=label,
            plist=_expand_path(str(raw.get("plist") or "")),
            group=str(raw.get("group") or "ungrouped"),
            purpose=str(raw.get("purpose") or ""),
            risk=tuple(str(item) for item in (raw.get("risk") or [])),
        )
    return entries


def labels_for_scope(manifest: dict[str, Any], scope: str, only_group: str | None = None) -> list[LabelEntry]:
    scopes = manifest.get("scopes") or {}
    if scope not in scopes:
        available = ", ".join(sorted(scopes))
        raise AutomationControlError(f"unknown scope '{scope}'. Available scopes: {available}")
    scope_payload = scopes[scope]
    requested_labels = list(scope_payload.get("labels") or [])
    by_label = _entries_by_label(manifest)
    missing = [label for label in requested_labels if label not in by_label]
    if missing:
        raise AutomationControlError(f"scope '{scope}' references unknown labels: {', '.join(missing)}")
    entries = [by_label[label] for label in requested_labels]
    if only_group:
        entries = [entry for entry in entries if entry.group == only_group]
    return entries


def _default_runner(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(args, capture_output=True, text=True, check=False, timeout=30)
    return {
        "args": args,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def _run_with_missing_binary_guard(runner: CommandRunner, args: list[str]) -> dict[str, Any]:
    try:
        return runner(args)
    except FileNotFoundError as exc:
        return {
            "args": args,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }


def _parse_launchctl_print(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state ="):
            parsed["state"] = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("last exit code ="):
            parsed["last_exit_code"] = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("runs ="):
            parsed["runs"] = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid ="):
            parsed["pid"] = stripped.split("=", 1)[1].strip()
    return parsed


def launchctl_status(entry: LabelEntry, *, domain: str, runner: CommandRunner) -> dict[str, Any]:
    result = _run_with_missing_binary_guard(runner, ["launchctl", "print", f"{domain}/{entry.label}"])
    loaded = result["returncode"] == 0
    parsed = _parse_launchctl_print(result.get("stdout") or "") if loaded else {}
    return {
        "label": entry.label,
        "group": entry.group,
        "purpose": entry.purpose,
        "plist": str(entry.plist),
        "plist_exists": entry.plist.exists(),
        "loaded": loaded,
        "state": parsed.get("state", "not_loaded" if not loaded else "unknown"),
        "last_exit_code": parsed.get("last_exit_code", ""),
        "runs": parsed.get("runs", ""),
        "pid": parsed.get("pid", ""),
        "print_returncode": result["returncode"],
        "print_stderr": (result.get("stderr") or "").strip(),
        "risk": list(entry.risk),
    }


def collect_label_status(entries: Iterable[LabelEntry], *, domain: str, runner: CommandRunner) -> list[dict[str, Any]]:
    return [launchctl_status(entry, domain=domain, runner=runner) for entry in entries]


def _lsof_path(path: Path, *, runner: CommandRunner) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "holder_count": 0, "holders": []}
    result = _run_with_missing_binary_guard(runner, ["lsof", str(path)])
    holders = []
    if result["returncode"] == 0:
        lines = [line for line in (result.get("stdout") or "").splitlines() if line.strip()]
        holders = lines[1:] if lines and lines[0].startswith("COMMAND") else lines
    return {
        "path": str(path),
        "exists": True,
        "holder_count": len(holders),
        "holders": holders,
        "lsof_returncode": result["returncode"],
    }


def collect_protected_surface_status(manifest: dict[str, Any], *, runner: CommandRunner) -> list[dict[str, Any]]:
    surfaces = []
    for raw in manifest.get("protected_surfaces") or []:
        if not isinstance(raw, dict):
            continue
        path = _expand_path(str(raw.get("path") or ""))
        status = _lsof_path(path, runner=runner)
        sidecar_paths = [_expand_path(str(item)) for item in (raw.get("sidecars") or [])]
        status.update(
            {
                "name": str(raw.get("name") or path.name),
                "sidecars": [
                    {"path": str(sidecar), "exists": sidecar.exists()} for sidecar in sidecar_paths
                ],
            }
        )
        surfaces.append(status)
    return surfaces


def collect_cron_status(*, runner: CommandRunner) -> dict[str, Any]:
    result = _run_with_missing_binary_guard(runner, ["crontab", "-l"])
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    has_entries = bool(stdout.strip()) and result["returncode"] == 0
    no_crontab = result["returncode"] != 0 and "no crontab" in (stdout + stderr).lower()
    return {
        "returncode": result["returncode"],
        "has_entries": has_entries,
        "no_crontab": no_crontab,
        "stdout": stdout,
        "stderr": stderr,
    }


def build_status_report(
    *,
    manifest: dict[str, Any],
    scope: str,
    only_group: str | None,
    domain: str,
    runner: CommandRunner,
) -> dict[str, Any]:
    entries = labels_for_scope(manifest, scope, only_group=only_group)
    labels = collect_label_status(entries, domain=domain, runner=runner)
    loaded_count = sum(1 for row in labels if row["loaded"])
    missing_plist_count = sum(1 for row in labels if not row["plist_exists"])
    return {
        "ok": True,
        "generated_at": _now_almaty().isoformat(),
        "repo": str(PROJECT_ROOT),
        "scope": scope,
        "group": only_group or "",
        "domain": domain,
        "label_count": len(labels),
        "loaded_count": loaded_count,
        "not_loaded_count": len(labels) - loaded_count,
        "missing_plist_count": missing_plist_count,
        "labels": labels,
        "protected_surfaces": collect_protected_surface_status(manifest, runner=runner),
        "cron": collect_cron_status(runner=runner),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_dir(action: str, scope: str, evidence_root: Path) -> Path:
    now = _now_almaty()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    return evidence_root / now.date().isoformat() / f"{stamp}_{action}_{scope}"


def _apply_allowed(apply: bool, environ: dict[str, str]) -> bool:
    return apply and str(environ.get(CONTROL_ENV_GATE) or "").strip() == "1"


def _mutation_gate_report(apply: bool, environ: dict[str, str]) -> dict[str, Any]:
    return {
        "apply_requested": bool(apply),
        "env_gate": CONTROL_ENV_GATE,
        "env_gate_set": str(environ.get(CONTROL_ENV_GATE) or "").strip() == "1",
        "mutation_allowed": _apply_allowed(apply, environ),
    }


def pause_or_resume(
    *,
    action: str,
    manifest: dict[str, Any],
    scope: str,
    only_group: str | None,
    domain: str,
    apply: bool,
    evidence_root: Path,
    runner: CommandRunner,
    environ: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    if action not in {"pause", "resume"}:
        raise AutomationControlError(f"unsupported action: {action}")

    gate = _mutation_gate_report(apply, environ)
    run_dir = _run_dir(action, scope, evidence_root)
    entries = labels_for_scope(manifest, scope, only_group=only_group)
    pre_status = build_status_report(
        manifest=manifest,
        scope=scope,
        only_group=only_group,
        domain=domain,
        runner=runner,
    )
    _write_json(run_dir / "pre_status.json", pre_status)

    operations: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    if apply and not gate["mutation_allowed"]:
        report = {
            "ok": False,
            "action": action,
            "scope": scope,
            "group": only_group or "",
            "run_dir": str(run_dir),
            "gate": gate,
            "failure_reason": f"{CONTROL_ENV_GATE}=1 is required with --apply",
            "pre_status_path": str(run_dir / "pre_status.json"),
            "operations": operations,
            "failures": failures,
        }
        _write_json(run_dir / f"{action}_report.json", report)
        return 2, report

    loaded_by_label = {row["label"]: row for row in pre_status["labels"]}
    for entry in entries:
        current = loaded_by_label.get(entry.label, {})
        if action == "pause":
            command = ["launchctl", "bootout", f"{domain}/{entry.label}"]
            if not current.get("loaded"):
                operations.append(
                    {
                        "label": entry.label,
                        "status": "skipped_not_loaded",
                        "command": command,
                    }
                )
                continue
        else:
            command = ["launchctl", "bootstrap", domain, str(entry.plist)]
            if current.get("loaded"):
                operations.append(
                    {
                        "label": entry.label,
                        "status": "skipped_already_loaded",
                        "command": command,
                    }
                )
                continue
            if not entry.plist.exists():
                failure = {
                    "label": entry.label,
                    "status": "failed_missing_plist",
                    "plist": str(entry.plist),
                    "command": command,
                }
                operations.append(failure)
                failures.append(failure)
                continue

        if not gate["mutation_allowed"]:
            operations.append(
                {
                    "label": entry.label,
                    "status": "dry_run_would_execute",
                    "command": command,
                }
            )
            if action == "resume":
                operations.append(
                    {
                        "label": entry.label,
                        "status": "dry_run_would_enable",
                        "command": ["launchctl", "enable", f"{domain}/{entry.label}"],
                    }
                )
            continue

        result = _run_with_missing_binary_guard(runner, command)
        operation = {
            "label": entry.label,
            "status": "executed",
            "command": command,
            "returncode": result["returncode"],
            "stdout": result.get("stdout") or "",
            "stderr": result.get("stderr") or "",
        }
        operations.append(operation)
        if result["returncode"] != 0:
            failures.append(operation)
            continue
        if action == "resume":
            enable_command = ["launchctl", "enable", f"{domain}/{entry.label}"]
            enable_result = _run_with_missing_binary_guard(runner, enable_command)
            enable_operation = {
                "label": entry.label,
                "status": "executed_enable",
                "command": enable_command,
                "returncode": enable_result["returncode"],
                "stdout": enable_result.get("stdout") or "",
                "stderr": enable_result.get("stderr") or "",
            }
            operations.append(enable_operation)
            # Some labels may not need an explicit enable. Preserve the result without failing.

    post_status = build_status_report(
        manifest=manifest,
        scope=scope,
        only_group=only_group,
        domain=domain,
        runner=runner,
    )
    _write_json(run_dir / "post_status.json", post_status)
    ok = not failures
    report = {
        "ok": ok,
        "action": action,
        "scope": scope,
        "group": only_group or "",
        "run_dir": str(run_dir),
        "gate": gate,
        "pre_status_path": str(run_dir / "pre_status.json"),
        "post_status_path": str(run_dir / "post_status.json"),
        "operations": operations,
        "failures": failures,
    }
    _write_json(run_dir / f"{action}_report.json", report)
    return (0 if ok else 1), report


def verify_state(
    *,
    manifest: dict[str, Any],
    scope: str,
    only_group: str | None,
    domain: str,
    expect: str,
    evidence_root: Path,
    runner: CommandRunner,
) -> tuple[int, dict[str, Any]]:
    status = build_status_report(
        manifest=manifest,
        scope=scope,
        only_group=only_group,
        domain=domain,
        runner=runner,
    )
    labels = status["labels"]
    loaded_count = int(status["loaded_count"])
    quiet_surfaces = all(
        surface.get("holder_count") == 0
        and not any(sidecar.get("exists") for sidecar in surface.get("sidecars", []))
        for surface in status["protected_surfaces"]
    )
    quiet_cron = not bool(status["cron"].get("has_entries"))
    if expect == "paused":
        ok = loaded_count == 0 and quiet_surfaces and quiet_cron
    elif expect == "running":
        ok = loaded_count == len(labels)
    else:
        ok = True
    report = {
        "ok": ok,
        "expect": expect,
        "scope": scope,
        "group": only_group or "",
        "loaded_count": loaded_count,
        "label_count": len(labels),
        "quiet_protected_surfaces": quiet_surfaces,
        "quiet_cron": quiet_cron,
        "status": status,
    }
    run_dir = _run_dir("verify", scope, evidence_root)
    _write_json(run_dir / "verify_report.json", report)
    report["run_dir"] = str(run_dir)
    return (0 if ok else 1), report


def _print_human_summary(report: dict[str, Any], *, quiet: bool) -> None:
    if quiet:
        return
    action = report.get("action") or "verify"
    ok = bool(report.get("ok"))
    status = "OK" if ok else "BLOCKED"
    print(f"{action}: {status}")
    if report.get("scope"):
        print(f"scope: {report['scope']}")
    if report.get("run_dir"):
        print(f"evidence: {report['run_dir']}")
    if report.get("failure_reason"):
        print(f"failure: {report['failure_reason']}", file=sys.stderr)
    failures = report.get("failures") or []
    if failures:
        print(f"failures: {len(failures)}", file=sys.stderr)
        for failure in failures[:8]:
            print(f"- {failure.get('label')}: {failure.get('status')}", file=sys.stderr)
    status_report = report.get("status") or {}
    if status_report:
        print(
            "labels: "
            f"{status_report.get('loaded_count', report.get('loaded_count', 0))}/"
            f"{status_report.get('label_count', report.get('label_count', 0))} loaded"
        )
    elif report.get("post_status_path"):
        print(f"post_status: {report['post_status_path']}")


def _print_status_summary(report: dict[str, Any], *, quiet: bool) -> None:
    if quiet:
        return
    print(f"status: scope={report['scope']} loaded={report['loaded_count']}/{report['label_count']}")
    if report["missing_plist_count"]:
        print(f"missing_plists: {report['missing_plist_count']}")
    for row in report["labels"]:
        marker = "LOADED" if row["loaded"] else "off"
        suffix = f" ({row['state']})" if row.get("state") else ""
        print(f"- {marker} {row['label']}{suffix}")


def build_parser(manifest: dict[str, Any] | None = None) -> argparse.ArgumentParser:
    scopes = sorted((manifest or load_manifest()).get("scopes", {}).keys())
    default_scope = (manifest or load_manifest()).get("default_scope", "daily-ops")

    def add_repeated_global_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)
        target.add_argument("--scope", choices=scopes, default=argparse.SUPPRESS)
        target.add_argument("--group", default=argparse.SUPPRESS, help="Optional manifest group to operate on within the selected scope")
        target.add_argument("--domain", default=argparse.SUPPRESS, help="launchctl domain (default: gui/<uid>)")
        target.add_argument("--evidence-root", type=Path, default=argparse.SUPPRESS)
        target.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Print machine-readable JSON to stdout")
        target.add_argument("--output-json", type=Path, default=argparse.SUPPRESS, help="Write report JSON to this path")
        target.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        description="Pause, verify, and resume repo-owned business LaunchAgents.",
        epilog=(
            "Examples:\n"
            "  scripts/manage_business_automation.py status --scope daily-ops\n"
            "  scripts/manage_business_automation.py pause --scope all-business\n"
            f"  {CONTROL_ENV_GATE}=1 scripts/manage_business_automation.py resume --scope daily-ops --apply\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scope", choices=scopes, default=default_scope)
    parser.add_argument("--group", default=None, help="Optional manifest group to operate on within the selected scope")
    parser.add_argument("--domain", default=f"gui/{os.getuid()}", help="launchctl domain (default: gui/<uid>)")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON to stdout")
    parser.add_argument("--output-json", type=Path, default=None, help="Write report JSON to this path")
    parser.add_argument("-q", "--quiet", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status", help="Read-only launchd/protected-surface status")
    add_repeated_global_flags(status_parser)
    pause_parser = subparsers.add_parser("pause", help="Boot out selected LaunchAgents; dry-run by default")
    add_repeated_global_flags(pause_parser)
    pause_parser.add_argument("--apply", action="store_true", help=f"Actually mutate launchd; also requires {CONTROL_ENV_GATE}=1")
    resume_parser = subparsers.add_parser("resume", help="Bootstrap selected LaunchAgents; dry-run by default")
    add_repeated_global_flags(resume_parser)
    resume_parser.add_argument("--apply", action="store_true", help=f"Actually mutate launchd; also requires {CONTROL_ENV_GATE}=1")
    verify_parser = subparsers.add_parser("verify", help="Verify expected paused/running state")
    add_repeated_global_flags(verify_parser)
    verify_parser.add_argument("--expect", choices=["paused", "running", "any"], default="paused")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: CommandRunner = _default_runner,
    environ: dict[str, str] | None = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ if environ is None else environ)
    manifest_path = DEFAULT_MANIFEST
    if "--manifest" in argv:
        idx = argv.index("--manifest")
        if idx + 1 < len(argv):
            manifest_path = Path(argv[idx + 1])
    manifest = load_manifest(manifest_path)
    parser = build_parser(manifest)
    try:
        args = parser.parse_args(argv)
        manifest = load_manifest(args.manifest)
        if args.command == "status":
            report = build_status_report(
                manifest=manifest,
                scope=args.scope,
                only_group=args.group,
                domain=args.domain,
                runner=runner,
            )
            code = 0
            _print_status_summary(report, quiet=args.quiet or args.json)
        elif args.command in {"pause", "resume"}:
            code, report = pause_or_resume(
                action=args.command,
                manifest=manifest,
                scope=args.scope,
                only_group=args.group,
                domain=args.domain,
                apply=bool(args.apply),
                evidence_root=args.evidence_root,
                runner=runner,
                environ=env,
            )
            _print_human_summary(report, quiet=args.quiet or args.json)
        elif args.command == "verify":
            code, report = verify_state(
                manifest=manifest,
                scope=args.scope,
                only_group=args.group,
                domain=args.domain,
                expect=args.expect,
                evidence_root=args.evidence_root,
                runner=runner,
            )
            _print_human_summary(report, quiet=args.quiet or args.json)
        else:
            raise AutomationControlError(f"unsupported command: {args.command}")
        if args.output_json:
            _write_json(args.output_json, report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return code
    except AutomationControlError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
