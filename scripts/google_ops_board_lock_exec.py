#!/usr/bin/env python3
"""Run a command under the shared Google Ops Board automation lock."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.google_ops_board_automation_common import (  # noqa: E402
    AUTOMATION_LOCK_HELD_ENV,
    GoogleOpsBoardAutomationLock,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire the Google Ops Board automation lock, then exec a command."
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after '--'")
    args = parser.parse_args(argv)

    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after '--'")

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TERM", "dumb")
    env[AUTOMATION_LOCK_HELD_ENV] = "1"

    try:
        with GoogleOpsBoardAutomationLock():
            proc = subprocess.run(command, cwd=str(PROJECT_ROOT), env=env)
            return int(proc.returncode)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
