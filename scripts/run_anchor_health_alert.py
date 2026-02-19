#!/usr/bin/env python3
"""Run anchor-health checks and optionally alert on failures."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from scripts.check_anchor_health import PROJECT_ROOT, check_anchor_health

send_run_failure_alert: Callable[..., bool] | None = None


def _send_alert_best_effort(*, summary: str, project_root: Path, lines: list[str]) -> None:
    try:
        global send_run_failure_alert
        if send_run_failure_alert is None:
            from core.alerts.error_alerts import send_run_failure_alert as _sender

            send_run_failure_alert = _sender
        details = " | ".join(line for line in lines if line.startswith("ERROR:")) or "see logs"
        send_run_failure_alert(
            error_message=f"{summary}; {details}",
            script_name="run_anchor_health_alert",
            context=f"project_root={project_root}",
        )
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch in tests
        print(f"anchor-health alert failed: {exc}")


def run_anchor_health_alert(
    *,
    project_root: Path = PROJECT_ROOT,
    send_alert: bool = False,
) -> tuple[int, str]:
    code, lines = check_anchor_health(project_root=project_root)
    status = "PASS" if code == 0 else "FAIL"
    summary = f"ANCHOR_HEALTH {status}: rc={code}"
    if code != 0 and send_alert:
        _send_alert_best_effort(summary=summary, project_root=project_root, lines=lines)
    return code, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run anchor-health checks and optional failure alert")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--send-alert", action="store_true", help="Send Telegram alert on failure (best effort)")
    args = parser.parse_args()

    code, lines = check_anchor_health(project_root=args.project_root)
    status = "PASS" if code == 0 else "FAIL"
    summary = f"ANCHOR_HEALTH {status}: rc={code}"
    for line in lines:
        print(line)
    print(summary)
    if code != 0 and bool(args.send_alert):
        _send_alert_best_effort(summary=summary, project_root=args.project_root, lines=lines)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
