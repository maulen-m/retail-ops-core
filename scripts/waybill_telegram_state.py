#!/usr/bin/env python3
"""Shared runtime state helpers for the waybill Telegram control bot."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
STATE_FILE = PROJECT_ROOT / "runtime" / "state" / "waybill_telegram_control_bot.json"


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def load_state(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or STATE_FILE)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(state: dict[str, Any], path: Path | None = None) -> None:
    target = Path(path or STATE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def arm_passive_handover_watch(
    *,
    chat_id: str,
    target_date: date,
    source_batch_label: str = "",
    state_path: Path | None = None,
    armed_at: datetime | None = None,
    grace_seconds: int | None = None,
    interval_seconds: int | None = None,
    max_checks: int | None = None,
    lookback_days: int | None = None,
) -> dict[str, Any]:
    """Arm a passive post-bundle check for physical courier handover drift."""
    now = armed_at or datetime.now(ALMATY_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ALMATY_TZ)
    grace = int(grace_seconds if grace_seconds is not None else _env_int("WAYBILL_HANDOVER_PASSIVE_GRACE_SECONDS", 300))
    lookback = int(lookback_days if lookback_days is not None else _env_int("WAYBILL_HANDOVER_LOOKBACK_DAYS", 7))
    final_check_at = datetime.combine(target_date, datetime.min.time(), tzinfo=ALMATY_TZ).replace(hour=20)
    next_check_at = final_check_at if now < final_check_at else now + timedelta(seconds=max(0, grace))

    state = load_state(state_path)
    state["passive_handover_watch"] = {
        "mode": "passive_final_20_00",
        "target_date": target_date.isoformat(),
        "chat_id": str(chat_id),
        "armed_at": now.isoformat(),
        "next_check_at": next_check_at.isoformat(),
        "attempts": 0,
        "interval_seconds": 0,
        "max_checks": 1,
        "lookback_days": max(1, lookback),
        "source_batch_label": str(source_batch_label or ""),
    }
    save_state(state, state_path)
    return {
        "armed": True,
        "state_file": str(Path(state_path or STATE_FILE)),
        "next_check_at": next_check_at.isoformat(),
    }
