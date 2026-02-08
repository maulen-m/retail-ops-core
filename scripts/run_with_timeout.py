#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import selectors
import signal
import subprocess
import sys
import time
from typing import Sequence


def _send_signal_tree(proc: subprocess.Popen[bytes], sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return


def run_command_with_timeout(
    cmd: Sequence[str],
    timeout_sec: int,
    grace_period_sec: int = 15,
) -> int:
    timeout_sec = max(int(timeout_sec), 1)
    grace_period_sec = max(int(grace_period_sec), 1)

    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=0,
    )
    assert proc.stdout is not None

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    start = time.monotonic()
    timed_out = False

    while True:
        elapsed = time.monotonic() - start
        remaining = timeout_sec - elapsed

        if remaining <= 0 and not timed_out:
            timed_out = True
            print(
                f"ERROR: command exceeded timeout ({timeout_sec}s); terminating...",
                file=sys.stderr,
            )
            _send_signal_tree(proc, signal.SIGTERM)

        wait_timeout = 0.25 if timed_out else min(max(remaining, 0.0), 0.25)
        events = selector.select(timeout=wait_timeout)
        for key, _ in events:
            chunk = os.read(key.fileobj.fileno(), 65536)
            if chunk:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            else:
                try:
                    selector.unregister(key.fileobj)
                except Exception:
                    pass

        rc = proc.poll()
        if rc is not None:
            # Drain trailing bytes that may still be buffered in the pipe.
            while True:
                events = selector.select(timeout=0)
                if not events:
                    break
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                    else:
                        try:
                            selector.unregister(key.fileobj)
                        except Exception:
                            pass
            if timed_out:
                return 124
            return rc

        if timed_out:
            # Escalate to SIGKILL after grace period.
            if time.monotonic() - (start + timeout_sec) >= grace_period_sec:
                print(
                    f"ERROR: command did not exit after {grace_period_sec}s grace; killing...",
                    file=sys.stderr,
                )
                _send_signal_tree(proc, signal.SIGKILL)
                proc.wait(timeout=10)
                return 124


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command with a hard wall-clock timeout.")
    parser.add_argument("--timeout", type=int, required=True, help="Wall-clock timeout in seconds.")
    parser.add_argument(
        "--grace-period",
        type=int,
        default=15,
        help="Seconds to wait after SIGTERM before SIGKILL (default: 15).",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run. Prefix with '--' before command arguments.",
    )
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("No command provided.")
    args.command = command
    return args


def main() -> int:
    args = _parse_args()
    return run_command_with_timeout(args.command, args.timeout, args.grace_period)


if __name__ == "__main__":
    raise SystemExit(main())
