#!/usr/bin/env python3
"""Fast daily shipping enablement and post-cutoff validation helper."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "daily_shipping_enablement"
ALMATY_TZ = ZoneInfo("Asia/Almaty")
CONTROL_ENV_GATE = "ENABLE_BUSINESS_AUTOMATION_CONTROL"
DEFAULT_CUTOFF_HOUR = 17
DEFAULT_CUTOFF_MINUTE = 0
DEFAULT_SETTLE_SECONDS = 180
DEFAULT_LOOKBACK_DAYS = 5


@dataclass
class CommandResult:
    label: str
    command: list[str]
    returncode: int
    stdout_path: str
    stderr_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "command": self.command,
            "returncode": self.returncode,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
        }


Runner = Callable[[list[str], dict[str, str] | None], subprocess.CompletedProcess[str]]


def now_almaty() -> datetime:
    return datetime.now(ALMATY_TZ)


def resolve_target_date(raw: str | None) -> date:
    if not raw or raw == "today":
        return now_almaty().date()
    return datetime.strptime(raw, "%Y-%m-%d").date()


def build_run_dir(output_root: Path, *, target_date: date, action: str) -> Path:
    stamp = now_almaty().strftime("%Y%m%d_%H%M%S")
    return output_root / target_date.isoformat() / f"{stamp}_{action}"


def cutoff_datetime(target_date: date, *, hour: int, minute: int, settle_seconds: int = 0) -> datetime:
    cutoff = datetime.combine(target_date, dt_time(hour, minute), tzinfo=ALMATY_TZ)
    return cutoff + timedelta(seconds=max(int(settle_seconds), 0))


def seconds_until_cutoff(
    *,
    current: datetime,
    target_date: date,
    hour: int,
    minute: int,
    settle_seconds: int,
) -> int:
    wait_until = cutoff_datetime(target_date, hour=hour, minute=minute, settle_seconds=settle_seconds)
    return max(0, int((wait_until - current).total_seconds()))


def default_runner(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(
    *,
    label: str,
    command: list[str],
    run_dir: Path,
    runner: Runner,
    env: dict[str, str] | None = None,
) -> CommandResult:
    result = runner(command, env)
    stdout_path = run_dir / f"{label}.stdout.txt"
    stderr_path = run_dir / f"{label}.stderr.txt"
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    return CommandResult(
        label=label,
        command=command,
        returncode=int(result.returncode),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def python_cmd() -> str:
    return str(PROJECT_ROOT / ".venv" / "bin" / "python")


def manage_cmd(*parts: str) -> list[str]:
    return [python_cmd(), str(PROJECT_ROOT / "scripts" / "manage_business_automation.py"), *parts]


def enable_commands(run_dir: Path, *, apply: bool) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = [
        (
            "status_daily_ops",
            manage_cmd(
                "status",
                "--scope",
                "daily-ops",
                "--output-json",
                str(run_dir / "status_daily_ops.json"),
            ),
        ),
        (
            "resume_daily_ops_dry_run",
            manage_cmd(
                "resume",
                "--scope",
                "daily-ops",
                "--output-json",
                str(run_dir / "resume_daily_ops_dry_run.json"),
            ),
        ),
    ]
    if apply:
        commands.append(
            (
                "resume_daily_ops_apply",
                manage_cmd(
                    "resume",
                    "--scope",
                    "daily-ops",
                    "--apply",
                    "--output-json",
                    str(run_dir / "resume_daily_ops_apply.json"),
                ),
            )
        )
        commands.append(
            (
                "verify_daily_ops_running",
                manage_cmd(
                    "verify",
                    "--scope",
                    "daily-ops",
                    "--expect",
                    "running",
                    "--output-json",
                    str(run_dir / "verify_daily_ops_running.json"),
                ),
            )
        )
    return commands


def run_enable(args: argparse.Namespace, *, runner: Runner = default_runner) -> int:
    target_date = resolve_target_date(args.target_date)
    run_dir = build_run_dir(args.output_root, target_date=target_date, action="enable")
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    results = [
        run_command(label=label, command=command, run_dir=run_dir, runner=runner, env=env)
        for label, command in enable_commands(run_dir, apply=bool(args.apply))
    ]
    cutoff_at = cutoff_datetime(
        target_date,
        hour=args.cutoff_hour,
        minute=args.cutoff_minute,
        settle_seconds=args.settle_seconds,
    )
    ok = all(result.returncode == 0 for result in results)
    report = {
        "ok": ok,
        "action": "enable",
        "apply_requested": bool(args.apply),
        "env_gate": CONTROL_ENV_GATE,
        "env_gate_set": env.get(CONTROL_ENV_GATE) == "1",
        "target_date": target_date.isoformat(),
        "run_dir": str(run_dir),
        "post_cutoff_validation_not_before": cutoff_at.isoformat(),
        "commands": [result.as_dict() for result in results],
        "next_step": (
            "run validate after post_cutoff_validation_not_before"
            if ok
            else "inspect failed command stdout/stderr before retrying"
        ),
    }
    if args.output_json:
        write_json(args.output_json, report)
    write_json(run_dir / "enable_report.json", report)
    print(f"enable: {'OK' if ok else 'BLOCKED'}")
    print(f"evidence: {run_dir}")
    print(f"post_cutoff_validation_not_before: {cutoff_at.isoformat()}")
    return 0 if ok else 1


def validation_commands(run_dir: Path, *, target_date: date, lookback_days: int) -> list[tuple[str, list[str]]]:
    import_status = run_dir / "import_status_postcutoff.json"
    return [
        (
            "import_status_postcutoff",
            [
                python_cmd(),
                str(PROJECT_ROOT / "scripts" / "report_import_status.py"),
                "--date",
                target_date.isoformat(),
                "--since-days",
                str(lookback_days),
                "--json-out",
                str(import_status),
            ],
        ),
        (
            "evaluate_import_postcutoff",
            [
                python_cmd(),
                str(PROJECT_ROOT / "scripts" / "evaluate_import_run_result.py"),
                "--step2-rc",
                "0",
                "--health-json",
                str(import_status),
                "--activeorders-file",
                str(PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "ActiveOrders.xlsx"),
                "--crm-file",
                str(PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"),
                "--target-date",
                target_date.isoformat(),
            ],
        ),
        (
            "google_ops_board_validate",
            [
                python_cmd(),
                str(PROJECT_ROOT / "scripts" / "sync_google_ops_board.py"),
                "--target-date",
                target_date.isoformat(),
                "--lookback-days",
                str(lookback_days),
                "--validate-only",
                "--output-json",
                str(run_dir / "google_ops_board_validate_postcutoff.json"),
            ],
        ),
    ]


def build_no_send_no_autofill_report(*, target_date: date, run_dir: Path) -> dict[str, Any]:
    send_root = PROJECT_ROOT / "excel_ui" / "Kaspi_orders" / "Today" / "MERGED" / "SEND"
    today_prefix = target_date.strftime("%d.%m.%y")
    today_send_dirs = []
    if send_root.exists():
        today_send_dirs = sorted(str(path) for path in send_root.iterdir() if path.is_dir() and path.name.startswith(today_prefix))
    auto_root = PROJECT_ROOT / "exports" / "google_ops_board" / "auto_probable_fill" / target_date.isoformat()
    auto_files = sorted(str(path) for path in auto_root.rglob("*") if path.is_file()) if auto_root.exists() else []
    report = {
        "target_date": target_date.isoformat(),
        "today_send_batch_dir_count": len(today_send_dirs),
        "today_send_batch_dirs": today_send_dirs,
        "auto_probable_fill_file_count": len(auto_files),
        "auto_probable_fill_files": auto_files,
        "premature_telegram_send_detected": bool(today_send_dirs),
        "premature_auto_fill_detected": bool(auto_files),
    }
    write_json(run_dir / "no_send_no_autofill_postcutoff.json", report)
    return report


def run_validate(args: argparse.Namespace, *, runner: Runner = default_runner) -> int:
    target_date = resolve_target_date(args.target_date)
    wait_seconds = seconds_until_cutoff(
        current=now_almaty(),
        target_date=target_date,
        hour=args.cutoff_hour,
        minute=args.cutoff_minute,
        settle_seconds=args.settle_seconds,
    )
    if wait_seconds and not args.wait_until_cutoff:
        run_dir = build_run_dir(args.output_root, target_date=target_date, action="validate_deferred")
        report = {
            "ok": True,
            "action": "validate",
            "status": "DEFER_UNTIL_POST_CUTOFF",
            "target_date": target_date.isoformat(),
            "seconds_until_post_cutoff": wait_seconds,
            "post_cutoff_validation_not_before": cutoff_datetime(
                target_date,
                hour=args.cutoff_hour,
                minute=args.cutoff_minute,
                settle_seconds=args.settle_seconds,
            ).isoformat(),
            "run_dir": str(run_dir),
        }
        if args.output_json:
            write_json(args.output_json, report)
        write_json(run_dir / "validate_deferred_report.json", report)
        print("validate: DEFER_UNTIL_POST_CUTOFF")
        print(f"post_cutoff_validation_not_before: {report['post_cutoff_validation_not_before']}")
        return 0
    if wait_seconds:
        time.sleep(wait_seconds)

    run_dir = build_run_dir(args.output_root, target_date=target_date, action="validate")
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    results = [
        run_command(label=label, command=command, run_dir=run_dir, runner=runner, env=env)
        for label, command in validation_commands(run_dir, target_date=target_date, lookback_days=args.lookback_days)
    ]
    no_send = build_no_send_no_autofill_report(target_date=target_date, run_dir=run_dir)
    ok = all(result.returncode == 0 for result in results)
    if no_send["premature_telegram_send_detected"] or no_send["premature_auto_fill_detected"]:
        ok = False
    report = {
        "ok": ok,
        "action": "validate",
        "status": "POST_CUTOFF_VALIDATED" if ok else "POST_CUTOFF_BLOCKED",
        "target_date": target_date.isoformat(),
        "run_dir": str(run_dir),
        "commands": [result.as_dict() for result in results],
        "no_send_no_autofill": no_send,
    }
    if args.output_json:
        write_json(args.output_json, report)
    write_json(run_dir / "validate_report.json", report)
    print(f"validate: {'OK' if ok else 'BLOCKED'}")
    print(f"evidence: {run_dir}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fast daily shipping enablement helper.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--target-date", default="today")
    parser.add_argument("--cutoff-hour", type=int, default=DEFAULT_CUTOFF_HOUR)
    parser.add_argument("--cutoff-minute", type=int, default=DEFAULT_CUTOFF_MINUTE)
    parser.add_argument("--settle-seconds", type=int, default=DEFAULT_SETTLE_SECONDS)
    parser.add_argument("--output-json", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enable_parser = subparsers.add_parser("enable", help="Resume and verify daily-ops only.")
    enable_parser.add_argument("--apply", action="store_true", help=f"Apply resume; requires {CONTROL_ENV_GATE}=1.")

    validate_parser = subparsers.add_parser("validate", help="Run post-cutoff read-only shipping validation.")
    validate_parser.add_argument("--wait-until-cutoff", action="store_true")
    validate_parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "enable":
        return run_enable(args)
    if args.command == "validate":
        return run_validate(args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
