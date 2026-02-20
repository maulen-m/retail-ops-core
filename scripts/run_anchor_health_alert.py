#!/usr/bin/env python3
"""Run anchor-health checks and optionally alert on failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Callable

from scripts.check_anchor_health import PROJECT_ROOT, check_anchor_health

send_run_failure_alert: Callable[..., bool] | None = None
DEFAULT_STATE_PATH = PROJECT_ROOT / "logs" / "anchor_health_alert_state.json"
DEFAULT_REPEAT_ALERT_SECONDS = 21600


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


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        return {}
    return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")


def _should_send_failure_alert(state: dict, now_ts: float, repeat_alert_seconds: int) -> bool:
    if state.get("last_status") != "FAIL":
        return True
    last_alert_ts = state.get("last_alert_ts")
    if not isinstance(last_alert_ts, (int, float)):
        return True
    return (now_ts - float(last_alert_ts)) >= int(repeat_alert_seconds)


def run_anchor_health_alert(
    *,
    project_root: Path = PROJECT_ROOT,
    send_alert: bool = False,
    state_path: Path = DEFAULT_STATE_PATH,
    repeat_alert_seconds: int = DEFAULT_REPEAT_ALERT_SECONDS,
    now_ts: float | None = None,
) -> tuple[int, str]:
    now = float(now_ts if now_ts is not None else time.time())
    state = _load_state(state_path)
    code, lines = check_anchor_health(project_root=project_root)
    status = "PASS" if code == 0 else "FAIL"
    summary = f"ANCHOR_HEALTH {status}: rc={code}"

    if code != 0 and send_alert:
        if _should_send_failure_alert(state, now, repeat_alert_seconds):
            _send_alert_best_effort(summary=summary, project_root=project_root, lines=lines)
            state["last_alert_ts"] = now
        else:
            summary = f"{summary} (alert suppressed by spam guard)"

    state["last_status"] = status
    state["last_checked_ts"] = now
    state["last_summary"] = summary
    try:
        _save_state(state_path, state)
    except Exception as exc:
        return 1, f"{summary} | state write failed: {exc}"
    return code, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run anchor-health checks and optional failure alert")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--send-alert", action="store_true", help="Send Telegram alert on failure (best effort)")
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="State file used for alert spam guard",
    )
    parser.add_argument(
        "--repeat-alert-seconds",
        type=int,
        default=DEFAULT_REPEAT_ALERT_SECONDS,
        help="Minimum seconds between repeated failure alerts",
    )
    args = parser.parse_args()

    code, summary = run_anchor_health_alert(
        project_root=args.project_root,
        send_alert=bool(args.send_alert),
        state_path=args.state_path,
        repeat_alert_seconds=int(args.repeat_alert_seconds),
    )
    _code, lines = check_anchor_health(project_root=args.project_root)
    for line in lines:
        print(line)
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
