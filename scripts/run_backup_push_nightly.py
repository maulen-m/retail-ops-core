#!/usr/bin/env python3
"""Run the existing backup-push helper and warn locally on failure."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.ops_alert_outbox import enqueue_alert  # noqa: E402


def run_backup_push(note: str) -> int:
    helper = PROJECT_ROOT / "scripts" / "backup_push.sh"
    if not helper.is_file():
        returncode = 127
        detail = f"missing helper: {helper}"
    else:
        result = subprocess.run(
            [str(helper), "--note", note],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        returncode = int(result.returncode)
        detail = f"backup_push exit code: {returncode}"
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

    if returncode != 0:
        try:
            enqueued = enqueue_alert(
                title="Nightly Git backup push failed",
                lines=[
                    detail,
                    f"Repository: {PROJECT_ROOT}",
                    "The day-end zero-unpushed SLO is not proven.",
                    "Local-only warning; no external delivery is attempted.",
                ],
                severity="WARN",
                dedup_key="git_governance:nightly_backup_push_failed",
                local_only=True,
            )
            if not enqueued:
                print("WARN: failed to persist backup-push outbox warning", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - defensive scheduler boundary
            print(
                f"WARN: backup-push outbox warning failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    return returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run scripts/backup_push.sh and enqueue a WARN on failure."
    )
    parser.add_argument(
        "--note",
        default="nightly governance backup push",
        help="Required note passed to backup_push.sh.",
    )
    args = parser.parse_args(argv)
    return run_backup_push(str(args.note))


if __name__ == "__main__":
    raise SystemExit(main())
