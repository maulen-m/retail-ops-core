#!/usr/bin/env python3
"""Scheduler wrapper for operational-stock daily truth.

The launchd plist pins this wrapper to the repo virtualenv. Scheduled runs
always use the fail-closed owner-publication mode; green publication remains a
manual CLI action after live blockers have been cleared and verified.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import os
from pathlib import Path
import stat
import subprocess
import sys

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_RELATIVE = ".venv/bin/python"
VENV_PYTHON = PROJECT_ROOT / VENV_RELATIVE
RUNNER = PROJECT_ROOT / "scripts" / "run_operational_stock_daily_truth.py"
SCHEDULER_ENV_PATH = PROJECT_ROOT / ".env"
SCHEDULER_SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def _ensure_repo_python() -> None:
    if not VENV_PYTHON.exists():
        print(f"ERROR: required scheduler interpreter missing: {VENV_PYTHON}", file=sys.stderr)
        raise SystemExit(2)
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def _load_scheduler_secrets(
    *,
    env_path: Path = SCHEDULER_ENV_PATH,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Load only scheduler-required keys from an owner-only env file."""

    env_path = Path(env_path)
    try:
        env_stat = env_path.lstat()
    except FileNotFoundError:
        return ()

    if stat.S_ISLNK(env_stat.st_mode) or not stat.S_ISREG(env_stat.st_mode):
        raise RuntimeError(f"scheduler env must be a regular non-symlink file: {env_path}")
    if env_stat.st_uid != os.getuid():
        raise RuntimeError(f"scheduler env must be owned by uid {os.getuid()}: {env_path}")
    mode = stat.S_IMODE(env_stat.st_mode)
    if mode != 0o600:
        raise RuntimeError(f"scheduler env must have mode 0600, found {mode:04o}: {env_path}")

    values = dotenv_values(env_path)
    target = os.environ if environ is None else environ
    loaded: list[str] = []
    for key in SCHEDULER_SECRET_KEYS:
        value = values.get(key)
        if value is None or not str(value):
            continue
        target[key] = str(value)
        loaded.append(key)
    return tuple(loaded)


def main() -> int:
    _ensure_repo_python()

    try:
        _load_scheduler_secrets()
    except RuntimeError as exc:
        print(f"ERROR: scheduler secret env rejected: {exc}", file=sys.stderr)
        return 2

    cmd = [str(VENV_PYTHON), str(RUNNER), *sys.argv[1:]]
    if os.environ.get("AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT") == "1":
        print(
            "WARNING: AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT is ignored by the scheduler; "
            "scheduled owner output remains fail-closed.",
            file=sys.stderr,
        )

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
