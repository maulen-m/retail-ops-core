#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.send_waybills_telegram import run_sender as run_telegram_sender  # noqa: E402
from scripts.send_waybills_whatsapp import (  # noqa: E402
    ALMATY_TZ,
    BROWSER_MODE_LAUNCH,
    DEFAULT_WHATSAPP_CHAT_TITLE,
    SOURCE_CHOICES,
    SOURCE_MERGED,
    TODAY_FOLDER,
)
from scripts.waybill_delivery_completion import delivery_completion_state  # noqa: E402


FALLBACK_AUTO_ZERO_FAIL = "auto-zero-fail"
FALLBACK_MANUAL = "manual"
FALLBACK_DISABLED = "disabled"
FALLBACK_CHOICES = [FALLBACK_AUTO_ZERO_FAIL, FALLBACK_MANUAL, FALLBACK_DISABLED]
LEDGER_COMPLETION_RECHECK_ATTEMPTS = 5
LEDGER_COMPLETION_RECHECK_SECONDS = 1.0


def _now_iso() -> str:
    return datetime.now(ALMATY_TZ).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_whatsapp_fallback(
    *,
    today_folder: Path,
    bundle_source: str,
    expected_target_date: date,
    json_out: Path,
    python_executable: str = sys.executable,
    chat_title: str = DEFAULT_WHATSAPP_CHAT_TITLE,
    browser_mode: str = BROWSER_MODE_LAUNCH,
) -> dict[str, Any]:
    command = [
        python_executable,
        str(PROJECT_ROOT / "scripts" / "send_waybills_whatsapp.py"),
        "--today-folder",
        str(Path(today_folder).expanduser()),
        "--bundle-source",
        bundle_source,
        "--expected-target-date",
        expected_target_date.isoformat(),
        "--chat-title",
        chat_title,
        "--browser-mode",
        browser_mode,
        "--fail-fast",
        "--json-out",
        str(json_out),
    ]
    proc = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "report_path": str(json_out),
        "report": _load_json(json_out),
    }


def _telegram_completion_state_after_sender(
    *,
    today_folder: Path,
    expected_date: date,
    telegram_report: dict[str, Any],
) -> dict[str, Any]:
    completion = delivery_completion_state(
        today_folder=today_folder,
        target_date=expected_date,
    )
    if completion.get("completed"):
        return completion

    confirmed_total = int(telegram_report.get("confirmed_total") or 0)
    total = int(telegram_report.get("total") or 0)
    if not total or confirmed_total < total:
        return completion

    # The sender writes the last ledger state and then returns its summary. On
    # slow file systems, the wrapper can observe the previous ledger state for a
    # moment even though the sender already confirmed every bundle.
    for _attempt in range(LEDGER_COMPLETION_RECHECK_ATTEMPTS):
        time.sleep(LEDGER_COMPLETION_RECHECK_SECONDS)
        completion = delivery_completion_state(
            today_folder=today_folder,
            target_date=expected_date,
        )
        if completion.get("completed"):
            return completion
    return completion


def run_delivery(
    *,
    today_folder: Path = TODAY_FOLDER,
    bundle_source: str = SOURCE_MERGED,
    expected_target_date: date | None = None,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    whatsapp_fallback_policy: str = FALLBACK_AUTO_ZERO_FAIL,
    output_dir: Path | None = None,
    whatsapp_chat_title: str = DEFAULT_WHATSAPP_CHAT_TITLE,
    whatsapp_browser_mode: str = BROWSER_MODE_LAUNCH,
    python_executable: str = sys.executable,
    status_messages: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    today_folder = Path(today_folder).expanduser()
    expected_date = expected_target_date or datetime.now(ALMATY_TZ).date()
    output_root = Path(output_dir or (today_folder / "delivery_reports"))
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    whatsapp_report_path = output_root / f"{timestamp}_whatsapp_fallback_report.json"

    report: dict[str, Any] = {
        "ok": False,
        "primary_channel": "telegram",
        "delivery_channel": "",
        "fallback_policy": whatsapp_fallback_policy,
        "whatsapp_fallback_attempted": False,
        "failure_stage": "",
        "failure_reason": "",
        "today_folder": str(today_folder),
        "bundle_source": bundle_source,
        "expected_target_date": expected_date.isoformat(),
        "started_at": _now_iso(),
        "completed_at": "",
    }

    telegram_report = run_telegram_sender(
        today_folder=today_folder,
        bundle_source=bundle_source,
        expected_target_date=expected_date,
        token=telegram_token,
        chat_id=telegram_chat_id,
        status_messages=status_messages,
        fail_fast=True,
        verbose=verbose,
    )
    report["telegram_report"] = telegram_report
    if telegram_report.get("ok"):
        completion = _telegram_completion_state_after_sender(
            today_folder=today_folder,
            expected_date=expected_date,
            telegram_report=telegram_report,
        )
        report["delivery_completion"] = completion
        if not completion.get("completed") or completion.get("channel") != "telegram":
            report.update(
                {
                    "failure_stage": "telegram_primary",
                    "failure_reason": (
                        "Telegram sender reported OK but delivery ledger is not complete: "
                        f"{completion.get('status')}"
                    ),
                    "completed_at": _now_iso(),
                }
            )
            return report
        report.update(
            {
                "ok": True,
                "delivery_channel": "telegram",
                "completed_at": _now_iso(),
            }
        )
        return report

    confirmed_total = int(telegram_report.get("confirmed_total") or 0)
    sent_this_run = int(telegram_report.get("sent") or 0)
    fallback_allowed = bool(telegram_report.get("fallback_allowed"))
    should_fallback = (
        whatsapp_fallback_policy == FALLBACK_AUTO_ZERO_FAIL
        and fallback_allowed
        and confirmed_total == 0
        and sent_this_run == 0
    )

    if should_fallback:
        report["whatsapp_fallback_attempted"] = True
        whatsapp_report = run_whatsapp_fallback(
            today_folder=today_folder,
            bundle_source=bundle_source,
            expected_target_date=expected_date,
            json_out=whatsapp_report_path,
            python_executable=python_executable,
            chat_title=whatsapp_chat_title,
            browser_mode=whatsapp_browser_mode,
        )
        report["whatsapp_report"] = whatsapp_report
        if whatsapp_report.get("ok"):
            completion = delivery_completion_state(
                today_folder=today_folder,
                target_date=expected_date,
                explicit_delivery_channel="whatsapp",
                explicit_delivery_ok=True,
            )
            report["delivery_completion"] = completion
            if not completion.get("completed") or completion.get("channel") != "whatsapp":
                report.update(
                    {
                        "failure_stage": "whatsapp_fallback",
                        "failure_reason": (
                            "WhatsApp fallback reported OK but delivery ledger is not complete: "
                            f"{completion.get('status')}"
                        ),
                        "completed_at": _now_iso(),
                    }
                )
                return report
            report.update(
                {
                    "ok": True,
                    "delivery_channel": "whatsapp",
                    "completed_at": _now_iso(),
                }
            )
            return report
        report.update(
            {
                "failure_stage": "whatsapp_fallback",
                "failure_reason": str(whatsapp_report.get("stderr") or whatsapp_report.get("stdout") or "WhatsApp fallback failed"),
                "completed_at": _now_iso(),
            }
        )
        return report

    report.update(
        {
            "failure_stage": "telegram_primary",
            "failure_reason": str(telegram_report.get("halt_reason") or telegram_report.get("error") or "Telegram primary failed"),
            "completed_at": _now_iso(),
        }
    )
    return report


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO date {value!r}; expected YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Primary Telegram waybill delivery with WhatsApp fallback")
    parser.add_argument("--today-folder", type=Path, default=TODAY_FOLDER)
    parser.add_argument("--bundle-source", choices=SOURCE_CHOICES, default=SOURCE_MERGED)
    parser.add_argument("--expected-target-date", type=_parse_iso_date, default=None)
    parser.add_argument("--telegram-token", type=str, default=None)
    parser.add_argument("--telegram-chat-id", type=str, default=None)
    parser.add_argument("--whatsapp-fallback-policy", choices=FALLBACK_CHOICES, default=FALLBACK_AUTO_ZERO_FAIL)
    parser.add_argument("--whatsapp-chat-title", type=str, default=DEFAULT_WHATSAPP_CHAT_TITLE)
    parser.add_argument("--whatsapp-browser-mode", type=str, default=BROWSER_MODE_LAUNCH)
    parser.add_argument("--no-status-messages", dest="status_messages", action="store_false", default=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    report = run_delivery(
        today_folder=args.today_folder,
        bundle_source=args.bundle_source,
        expected_target_date=args.expected_target_date or datetime.now(ALMATY_TZ).date(),
        telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat_id,
        whatsapp_fallback_policy=args.whatsapp_fallback_policy,
        output_dir=args.output_dir,
        whatsapp_chat_title=args.whatsapp_chat_title,
        whatsapp_browser_mode=args.whatsapp_browser_mode,
        status_messages=bool(args.status_messages),
        verbose=bool(args.verbose),
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
