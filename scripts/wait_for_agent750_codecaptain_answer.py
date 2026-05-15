#!/usr/bin/env python3
"""Read-only watcher for the Agent750 CodeCaptain answer gate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_agent750_launch_readiness import ReadinessResult  # noqa: E402
from scripts.report_agent750_next_action import build_next_action, run_readiness  # noqa: E402


@dataclass
class WaitResult:
    return_code: int
    payload: dict


def wait_for_readiness(
    *,
    readiness_fn: Callable[[], ReadinessResult] = run_readiness,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    timeout_seconds: float = 0.0,
    interval_seconds: float = 30.0,
) -> WaitResult:
    """Poll the read-only readiness gate until ready or timeout.

    A timeout of 0 performs exactly one check. This helper never imports,
    copies, launches agents, mutates production state, or pings tmux panes.
    """
    timeout = max(0.0, float(timeout_seconds))
    interval = max(0.1, float(interval_seconds))
    start = monotonic_fn()
    poll_count = 0

    while True:
        poll_count += 1
        readiness = readiness_fn()
        payload = build_next_action(readiness)
        payload["poll_count"] = poll_count
        payload["timeout_seconds"] = timeout
        payload["interval_seconds"] = interval
        payload["elapsed_seconds"] = max(0.0, monotonic_fn() - start)
        payload["timed_out"] = False
        payload["watcher_mode"] = "read_only_no_import_no_launch_no_tmux_ping"

        if readiness.ok:
            return WaitResult(return_code=0, payload=payload)
        if timeout == 0:
            return WaitResult(return_code=2, payload=payload)

        elapsed = payload["elapsed_seconds"]
        remaining = timeout - elapsed
        if remaining <= 0:
            payload["timed_out"] = True
            return WaitResult(return_code=2, payload=payload)

        sleep_fn(min(interval, remaining))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only watcher for the Agent750 CodeCaptain answer gate")
    p.add_argument("--timeout-seconds", type=float, default=0.0, help="0 means one check only")
    p.add_argument("--interval-seconds", type=float, default=30.0)
    p.add_argument("--json-only", action="store_true", help="Print only JSON output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = wait_for_readiness(
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    print(json.dumps(result.payload, ensure_ascii=False, indent=2, sort_keys=True))
    return result.return_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
