#!/usr/bin/env python3
"""LaunchAgent entrypoint for Kaspi import schedule."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path("~/Docs/Autonomous_business")
COMMAND_PATH = Path("~/Docs/Autonomous_business/excel_ui/run_full_import.command")
DOTENV_PATH = PROJECT_ROOT / ".env"
RUNTIME_LOG_DIR = PROJECT_ROOT / "runtime_logs"
STDOUT_LOG_PATH = RUNTIME_LOG_DIR / "kaspi_import_stdout.log"
STDERR_LOG_PATH = RUNTIME_LOG_DIR / "kaspi_import_stderr.log"
REPORT_DIR = RUNTIME_LOG_DIR / "import_reports"
POPUP_ENV_KEY = "KASPI_IMPORT_POPUP_TERMINAL"


def _parse_dotenv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key] = value
    return data


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _tail(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return f"[missing] {path}"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _write_run_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    return_code: int,
    command_path: Path,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = finished_at.strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"kaspi_import_report_{stamp}.txt"
    duration_sec = int((finished_at - started_at).total_seconds())
    outcome = "SUCCESS" if return_code == 0 else "FAILED"
    body = [
        "Kaspi Import Scheduled Run Report",
        "================================",
        f"Outcome: {outcome}",
        f"Return code: {return_code}",
        f"Started: {started_at.isoformat(timespec='seconds')}",
        f"Finished: {finished_at.isoformat(timespec='seconds')}",
        f"Duration: {duration_sec}s",
        f"Command: {command_path}",
        "",
        f"--- STDOUT tail ({STDOUT_LOG_PATH}) ---",
        _tail(STDOUT_LOG_PATH),
        "",
        f"--- STDERR tail ({STDERR_LOG_PATH}) ---",
        _tail(STDERR_LOG_PATH),
        "",
    ]
    report_path.write_text("\n".join(body), encoding="utf-8")
    return report_path


def _terminal_report_command(report_path: Path) -> str:
    quoted_report = shlex.quote(str(report_path))
    return (
        "clear; "
        "echo 'Kaspi Import Run Finished'; "
        f"echo \"Report: {str(report_path)}\"; "
        "echo; "
        f"cat {quoted_report}; "
        "echo; "
        "read -n 1 -s -r -p 'Press any key to close this window...'; "
        "exit"
    )


def _show_terminal_popup(report_path: Path) -> None:
    terminal_cmd = _terminal_report_command(report_path)
    applescript_cmd = json.dumps(terminal_cmd)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Terminal" to activate',
            "-e",
            f'tell application "Terminal" to do script {applescript_cmd}',
        ],
        check=False,
    )


def main() -> int:
    project_root = PROJECT_ROOT
    command_path = COMMAND_PATH

    if not command_path.exists():
        print(f"ERROR: missing scheduler command: {command_path}", file=sys.stderr)
        return 78

    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    dotenv = _parse_dotenv(DOTENV_PATH)

    started_at = datetime.now()
    result = subprocess.run(["/bin/bash", str(command_path)], cwd=str(project_root), env=env)
    finished_at = datetime.now()

    report_path = _write_run_report(
        started_at=started_at,
        finished_at=finished_at,
        return_code=int(result.returncode),
        command_path=command_path,
    )
    print(f"Run report: {report_path}")

    popup_value = os.environ.get(POPUP_ENV_KEY)
    if popup_value is None:
        popup_value = dotenv.get(POPUP_ENV_KEY)
    if _is_truthy(popup_value):
        _show_terminal_popup(report_path)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
