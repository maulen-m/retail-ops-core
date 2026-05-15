#!/usr/bin/env python3
"""Telegram control-plane fallback for Google Ops Board waybill closeout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.integrations.telegram_bot import get_waybill_telegram_config, send_message  # noqa: E402
from core.paths import data_path  # noqa: E402
from scripts.run_google_ops_board_closeout import build_readiness_report  # noqa: E402
from scripts import returns_pickup_report as returns_pickup_report_mod  # noqa: E402
from scripts.send_waybills_telegram import run_ordered_full_resend, send_final_status_table  # noqa: E402
from scripts.waybill_delivery_completion import (  # noqa: E402
    delivery_completion_state,
    format_delivery_completion_status,
)
from scripts.waybill_handover_check import (  # noqa: E402
    build_waybill_handover_report,
    format_handover_compact_status_message,
    format_handover_status_message,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
STATE_FILE = PROJECT_ROOT / "runtime" / "state" / "waybill_telegram_control_bot.json"
ALLOWED_USERS_FILE = PROJECT_ROOT / "runtime" / "state" / "waybill_telegram_allowed_users.txt"
CLOSEOUT_SCHEDULER_PATH = PROJECT_ROOT / "scripts" / "run_google_ops_board_closeout_scheduler.py"
DB_PATH = data_path("db", "app.db")
READY_DEBOUNCE_SECONDS = 60
HANDOVER_MANUAL_DELAY_SECONDS = 60
HANDOVER_PASSIVE_INTERVAL_SECONDS = int(os.environ.get("WAYBILL_HANDOVER_PASSIVE_INTERVAL_SECONDS", "180"))
HANDOVER_PASSIVE_MAX_CHECKS = int(os.environ.get("WAYBILL_HANDOVER_PASSIVE_MAX_CHECKS", "5"))
HANDOVER_LOOKBACK_DAYS = int(os.environ.get("WAYBILL_HANDOVER_LOOKBACK_DAYS", "7"))
MAX_MSG_LEN = 3500
BOT_ALIAS_TO_COMMAND = {
    "/r": "/returns_pickup",
    "/ret": "/returns_pickup",
    "/p": "/returns_pickup",
    "/h": "/handover_status",
    "/hf": "/handover_full",
    "/hfull": "/handover_full",
    "/hd": "/handover_done",
    "возвраты": "/returns_pickup",
    "передал курьеру": "/handover_done",
    "передача": "/handover_status",
    "полная передача": "/handover_full",
    "проверить передачу": "/handover_status",
    "помощь": "/help",
}


def _now() -> datetime:
    return datetime.now(ALMATY_TZ)


def _today() -> date:
    return _now().date()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _load_state(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or STATE_FILE)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any], path: Path | None = None) -> None:
    target = Path(path or STATE_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_offset() -> int | None:
    state = _load_state()
    try:
        return int(state["offset"]) if state.get("offset") is not None else None
    except Exception:
        return None


def _save_offset(offset: int) -> None:
    state = _load_state()
    state["offset"] = int(offset)
    _save_state(state)


def _allowed_user_ids() -> set[str]:
    result: set[str] = set()
    values = os.getenv("TELEGRAM_WAYBILL_ALLOWED_USER_IDS", "").strip()
    if values:
        result.update(item.strip() for item in values.split(",") if item.strip())
    if ALLOWED_USERS_FILE.exists():
        for raw_line in ALLOWED_USERS_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                result.add(line)
    return result


def _get_updates(token: str, offset: int | None) -> list[dict[str, Any]]:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params: dict[str, Any] = {"timeout": 10, "allowed_updates": json.dumps(["message", "edited_message"])}
    if offset is not None:
        params["offset"] = offset
    try:
        response = requests.get(url, params=params, timeout=15)
        payload = response.json()
        if not payload.get("ok"):
            return []
        return list(payload.get("result") or [])
    except requests.RequestException:
        return []


def _chunk_message(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LEN:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}".strip()
        if len(candidate) > MAX_MSG_LEN and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _send_text(*, token: str, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    chunks = _chunk_message(text)
    for index, chunk in enumerate(chunks):
        send_message(
            token=token,
            chat_id=chat_id,
            text=chunk,
            timeout_seconds=20,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
        )


def _command_name(text: str) -> str:
    first = _clean(text).split()[0] if _clean(text).split() else ""
    if "@" in first:
        first = first.split("@", 1)[0]
    return first.lower()


def _text_to_command(text: str) -> str:
    clean = _clean(text)
    if not clean:
        return ""
    if clean.startswith("/"):
        first = clean.split()[0]
        command = _command_name(first)
        normalized = BOT_ALIAS_TO_COMMAND.get(command, command)
        remainder = clean.split(maxsplit=1)[1] if len(clean.split(maxsplit=1)) == 2 else ""
        return normalized if not remainder else f"{normalized} {remainder}"
    lower = clean.lower()
    alias = BOT_ALIAS_TO_COMMAND.get(lower)
    if alias:
        return alias
    if lower.startswith("забрал "):
        suffix = clean.split(" ", 1)[1]
        store_code = returns_pickup_report_mod.normalize_store_code(suffix)
        if store_code:
            return f"/returns_ack_store {store_code}"
    return ""


def build_waybill_control_readiness(
    *,
    target_date: date | None = None,
    lookback_days: int = 5,
) -> dict[str, Any]:
    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    service_account_json = resolve_service_account_json(contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    return build_readiness_report(
        client=client,
        contract=contract,
        db_path=DB_PATH,
        target_date=target_date or _today(),
        lookback_days=lookback_days,
    )


def _order_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        order_id = _clean(row.get("OrderID") or row.get("order_id"))
        if order_id and order_id not in seen:
            seen.add(order_id)
            result.append(order_id)
    return result


def _ready_gate(readiness: dict[str, Any]) -> tuple[bool, str, list[str]]:
    if not bool(readiness.get("run_control_target_match", True)):
        return False, "BLOCKED_TARGET_DATE", []
    if int(readiness.get("blank_size_count") or 0) > 0:
        return False, "BLOCKED_MISSING_SIZES", _order_ids(list(readiness.get("blank_size_rows") or []))
    if int(readiness.get("invalid_size_count") or 0) > 0:
        return False, "BLOCKED_INVALID_SIZES", _order_ids(list(readiness.get("invalid_size_rows") or []))
    return True, "READY_GREEN", []


def _format_readiness(readiness: dict[str, Any]) -> str:
    green, status, blockers = _ready_gate(readiness)
    lines = [
        "<b>Waybill Closeout Status</b>",
        f"Gate: <code>{status}</code>",
        f"Run_Control READY: <code>{bool(readiness.get('run_control_ready_ok'))}</code>",
        f"Missing sizes: <code>{int(readiness.get('blank_size_count') or 0)}</code>",
        f"Invalid sizes: <code>{int(readiness.get('invalid_size_count') or 0)}</code>",
    ]
    if blockers:
        lines.append("Orders: <code>" + ", ".join(blockers[:30]) + "</code>")
        if len(blockers) > 30:
            lines.append(f"... and {len(blockers) - 30} more")
    if green:
        lines.append("Telegram /ready can start the 60s closeout debounce.")
    return "\n".join(lines)


def _select_run_control_row(client: GoogleOpsBoardClient, contract, target_date: date) -> dict[str, Any] | None:
    headers = contract.tabs["Run_Control"].headers
    rows = extract_rows_with_positions_from_matrix(headers, client.get_tab_values("Run_Control"))
    target_iso = target_date.isoformat()
    for row_info in rows:
        if _clean(row_info["row"].get("target_date")) == target_iso:
            return row_info
    return rows[0] if rows else None


def _update_run_control_ready_value(*, value: str, note: str, target_date: date | None = None) -> None:
    contract = load_ops_board_contract(DEFAULT_CONTRACT_PATH)
    service_account_json = resolve_service_account_json(contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    selected = _select_run_control_row(client, contract, target_date or _today())
    if selected is None:
        return
    headers = contract.tabs["Run_Control"].headers
    row = dict(selected["row"])
    row["ready_for_closeout"] = value
    row["ready_set_by"] = "TELEGRAM_WAYBILL_BOT"
    row["ready_set_at"] = _now().isoformat()
    current_note = _clean(row.get("notes"))
    row["notes"] = note if not current_note else f"{current_note} | {note}"
    client.update_tab_rows(
        "Run_Control",
        headers,
        [{"sheet_row": int(selected["sheet_row"]), "row": row}],
    )


def set_run_control_ready(*, target_date: date | None = None, note: str = "Telegram /ready fallback") -> None:
    _update_run_control_ready_value(value="READY", note=note, target_date=target_date)


def set_run_control_hold(*, target_date: date | None = None, note: str = "Telegram /halt fallback") -> None:
    _update_run_control_ready_value(value="HOLD", note=note, target_date=target_date)


def _arm_pending_ready(*, chat_id: str, user_id: str, now: datetime, target_date: date) -> None:
    state = _load_state()
    state["pending_ready"] = {
        "target_date": target_date.isoformat(),
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "requested_at": now.isoformat(),
    }
    _save_state(state)


def _clear_pending_ready() -> None:
    state = _load_state()
    state.pop("pending_ready", None)
    if state:
        _save_state(state)
        return
    try:
        Path(STATE_FILE).unlink()
    except FileNotFoundError:
        pass


def _process_pending_ready(*, token: str, now: datetime) -> int:
    state = _load_state()
    pending = state.get("pending_ready") or {}
    if not pending:
        return 0
    chat_id = str(pending.get("chat_id") or "")
    target_raw = _clean(pending.get("target_date"))
    requested_raw = _clean(pending.get("requested_at"))
    try:
        target_date = date.fromisoformat(target_raw)
        requested_at = datetime.fromisoformat(requested_raw)
    except ValueError:
        state.pop("pending_ready", None)
        _save_state(state)
        return 0
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=ALMATY_TZ)
    elapsed = int((now - requested_at).total_seconds())
    if elapsed < READY_DEBOUNCE_SECONDS:
        return 0

    readiness = build_waybill_control_readiness(target_date=target_date)
    green, status, blockers = _ready_gate(readiness)
    if not green:
        state.pop("pending_ready", None)
        _save_state(state)
        _send_text(
            token=token,
            chat_id=chat_id,
            text=f"Telegram /ready cancelled after debounce: <code>{status}</code>\nOrders: <code>{', '.join(blockers)}</code>",
        )
        return 0

    try:
        set_run_control_ready(target_date=target_date, note="Telegram /ready debounce passed")
    except Exception as exc:
        state.pop("pending_ready", None)
        _save_state(state)
        _send_text(token=token, chat_id=chat_id, text=f"Telegram /ready failed to set Run_Control READY: <code>{exc}</code>")
        return 1

    _send_text(token=token, chat_id=chat_id, text="Telegram /ready stable for 60s; starting closeout.")
    env = os.environ.copy()
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")
    result = subprocess.run(
        [sys.executable, str(CLOSEOUT_SCHEDULER_PATH), "--resume"],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    state.pop("pending_ready", None)
    _save_state(state)
    if result.returncode != 0:
        _send_text(token=token, chat_id=chat_id, text=f"Closeout scheduler failed with rc=<code>{result.returncode}</code>.")
    return int(result.returncode)


def _parse_state_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed


def _parse_state_date(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _clear_handover_state_key(state: dict[str, Any], key: str) -> None:
    state.pop(key, None)
    if state:
        _save_state(state)
        return
    try:
        Path(STATE_FILE).unlink()
    except FileNotFoundError:
        pass


def _arm_pending_handover(
    *,
    chat_id: str,
    user_id: str,
    now: datetime,
    target_date: date,
    delay_seconds: int = HANDOVER_MANUAL_DELAY_SECONDS,
) -> None:
    state = _load_state()
    next_check_at = now + timedelta(seconds=max(0, int(delay_seconds)))
    state["pending_handover_check"] = {
        "mode": "manual",
        "target_date": target_date.isoformat(),
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "requested_at": now.isoformat(),
        "next_check_at": next_check_at.isoformat(),
        "lookback_days": HANDOVER_LOOKBACK_DAYS,
    }
    _save_state(state)


def _process_single_handover_watch(
    *,
    state: dict[str, Any],
    key: str,
    payload: dict[str, Any],
    token: str,
    default_chat_id: str,
    now: datetime,
) -> bool:
    target_date = _parse_state_date(payload.get("target_date"))
    next_check_at = _parse_state_datetime(payload.get("next_check_at") or payload.get("requested_at"))
    chat_id = _clean(payload.get("chat_id")) or default_chat_id
    if target_date is None or next_check_at is None or not chat_id:
        state.pop(key, None)
        _save_state(state)
        return True
    if key == "passive_handover_watch":
        final_check_at = datetime.combine(target_date, datetime.min.time(), tzinfo=ALMATY_TZ).replace(hour=20)
        if now < final_check_at:
            payload["mode"] = "passive_final_20_00"
            payload["attempts"] = 0
            payload["max_checks"] = 1
            payload["interval_seconds"] = 0
            payload["next_check_at"] = final_check_at.isoformat()
            state[key] = payload
            _save_state(state)
            return False
    if now < next_check_at:
        return False

    lookback_days = int(payload.get("lookback_days") or HANDOVER_LOOKBACK_DAYS)
    try:
        report = build_waybill_handover_report(target_date=target_date, lookback_days=lookback_days, now=now)
        _send_text(token=token, chat_id=chat_id, text=format_handover_compact_status_message(report))
    except Exception as exc:
        _send_text(token=token, chat_id=chat_id, text=f"Physical handover check failed: <code>{exc}</code>")
        report = {"ok": False}

    if key == "pending_handover_check" or key == "passive_handover_watch" or bool(report.get("ok")):
        _clear_handover_state_key(state, key)
        return True

    attempts = int(payload.get("attempts") or 0) + 1
    max_checks = int(payload.get("max_checks") or HANDOVER_PASSIVE_MAX_CHECKS)
    if attempts >= max(1, max_checks):
        state.pop(key, None)
        _save_state(state)
        return True

    interval = int(payload.get("interval_seconds") or HANDOVER_PASSIVE_INTERVAL_SECONDS)
    payload["attempts"] = attempts
    payload["next_check_at"] = (now + timedelta(seconds=max(30, interval))).isoformat()
    state[key] = payload
    _save_state(state)
    return True


def _process_pending_handover(*, token: str, now: datetime, default_chat_id: str) -> int:
    state = _load_state()
    for key in ("pending_handover_check", "passive_handover_watch"):
        payload = state.get(key)
        if not isinstance(payload, dict) or not payload:
            continue
        _process_single_handover_watch(
            state=state,
            key=key,
            payload=dict(payload),
            token=token,
            default_chat_id=default_chat_id,
            now=now,
        )
        state = _load_state()
    return 0


def _handle_command(*, text: str, chat_id: str, user_id: str, token: str, now: datetime) -> None:
    normalized_text = _text_to_command(text) or text
    command = _command_name(normalized_text)
    parts = _clean(normalized_text).split()
    args = parts[1:]
    target_date = now.astimezone(ALMATY_TZ).date()
    if command in {"/start", "/help"}:
        keyboard = returns_pickup_report_mod.build_returns_pickup_reply_markup({"stores": []})
        _send_text(
            token=token,
            chat_id=chat_id,
            text=(
                "<b>Waybill Bot</b>\n"
                "/status — readiness\n"
                "/delivery_status — manifest/ledger delivery counts\n"
                "/ready — start 60s closeout debounce\n"
                "/resume_delivery — resume incomplete delivery\n"
                "/resend_today_ordered confirm — resend full manifest in canonical order\n"
                "/handover_done — employee handed packages to courier; check Kaspi after 60s\n"
                "/handover_status — compact physical courier handover state\n"
                "/hfull — full physical handover audit table\n"
                "/r — returned/cancelled orders back at pickup point\n"
                "Buttons: <code>Передал курьеру</code>, <code>Передача</code>, <code>Возвраты</code>, <code>Забрал OF</code>, <code>Забрал U</code>, <code>Забрал MG</code>\n"
                "/returns_ack_store STORE — hide picked-up store queue\n"
                "/returns_unack ORDER_ID ... — restore orders back to queue\n"
                "/final_table — resend final totals table\n"
                "/halt — cancel pending closeout and set HOLD"
            ),
            reply_markup=keyboard,
        )
        return
    if command == "/status":
        readiness = build_waybill_control_readiness(target_date=target_date)
        _send_text(token=token, chat_id=chat_id, text=_format_readiness(readiness))
        return
    if command == "/delivery_status":
        state = delivery_completion_state(target_date=target_date)
        _send_text(token=token, chat_id=chat_id, text=format_delivery_completion_status(state))
        return
    if command == "/handover_status":
        report = build_waybill_handover_report(target_date=target_date, lookback_days=HANDOVER_LOOKBACK_DAYS, now=now)
        _send_text(token=token, chat_id=chat_id, text=format_handover_compact_status_message(report))
        return
    if command == "/handover_full":
        report = build_waybill_handover_report(target_date=target_date, lookback_days=HANDOVER_LOOKBACK_DAYS, now=now)
        _send_text(token=token, chat_id=chat_id, text=format_handover_status_message(report))
        return
    if command == "/handover_done":
        _arm_pending_handover(chat_id=chat_id, user_id=user_id, now=now, target_date=target_date)
        _send_text(
            token=token,
            chat_id=chat_id,
            text="Physical handover accepted. Waiting 60 seconds, then I will re-check Kaspi Передача.",
        )
        return
    if command == "/returns_pickup":
        snapshot = returns_pickup_report_mod.build_pickup_ready_snapshot(db_path=DB_PATH, as_of=now)
        _send_text(
            token=token,
            chat_id=chat_id,
            text=returns_pickup_report_mod.format_returns_pickup_message(snapshot),
            reply_markup=returns_pickup_report_mod.build_returns_pickup_reply_markup(snapshot),
        )
        return
    if command == "/ready":
        readiness = build_waybill_control_readiness(target_date=target_date)
        green, status, blockers = _ready_gate(readiness)
        if not green:
            _clear_pending_ready()
            _send_text(
                token=token,
                chat_id=chat_id,
                text=f"Telegram /ready blocked: <code>{status}</code>\nOrders: <code>{', '.join(blockers)}</code>",
            )
            return
        try:
            set_run_control_ready(target_date=target_date, note="Telegram /ready fallback armed")
        except Exception as exc:
            _send_text(token=token, chat_id=chat_id, text=f"Telegram /ready failed to set Run_Control READY: <code>{exc}</code>")
            return
        _arm_pending_ready(chat_id=chat_id, user_id=user_id, now=now, target_date=target_date)
        _send_text(token=token, chat_id=chat_id, text="Telegram /ready accepted. Waiting 60 seconds before closeout.")
        return
    if command == "/resume_delivery":
        state = delivery_completion_state(target_date=target_date)
        if state.get("completed"):
            _send_text(token=token, chat_id=chat_id, text=format_delivery_completion_status(state) + "\nDelivery is already complete.")
            return
        readiness = build_waybill_control_readiness(target_date=target_date)
        green, status, blockers = _ready_gate(readiness)
        if not green:
            _send_text(
                token=token,
                chat_id=chat_id,
                text=f"Telegram /resume_delivery blocked: <code>{status}</code>\nOrders: <code>{', '.join(blockers)}</code>",
            )
            return
        _send_text(token=token, chat_id=chat_id, text="Telegram /resume_delivery: resuming delivery through closeout scheduler.")
        env = os.environ.copy()
        env.setdefault("TERM", "dumb")
        env.setdefault("PYTHONUNBUFFERED", "1")
        result = subprocess.run(
            [sys.executable, str(CLOSEOUT_SCHEDULER_PATH), "--resume"],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        if result.returncode != 0:
            _send_text(token=token, chat_id=chat_id, text=f"Delivery resume failed with rc=<code>{result.returncode}</code>.")
        return
    if command == "/resend_today_ordered":
        if not args or args[0].casefold() != "confirm":
            _send_text(
                token=token,
                chat_id=chat_id,
                text=(
                    "Ordered full resend is live and can duplicate documents. "
                    "Use <code>/resend_today_ordered confirm</code> only after checking the current batch."
                ),
            )
            return
        _send_text(token=token, chat_id=chat_id, text="Telegram ordered full resend started. Locking batch and sending in manifest order.")
        result = run_ordered_full_resend(expected_target_date=target_date)
        proof = dict(result.get("ordered_resend_proof") or {})
        if result.get("ok") and proof.get("ok"):
            sent = int(result.get("confirmed_total") or result.get("sent") or 0)
            total = int(result.get("total") or proof.get("expected_count") or 0)
            msg_min = proof.get("message_id_min")
            msg_max = proof.get("message_id_max")
            _send_text(
                token=token,
                chat_id=chat_id,
                text=(
                    "Telegram ordered resend complete.\n"
                    f"Bundles: <code>{sent}/{total}</code>\n"
                    f"Message IDs: <code>{msg_min}..{msg_max}</code>\n"
                    f"Sequence match: <code>{bool(proof.get('sequence_match'))}</code>"
                ),
            )
            return
        issues = proof.get("issues") or result.get("errors") or []
        _send_text(
            token=token,
            chat_id=chat_id,
            text=(
                "Telegram ordered resend failed or sequence proof failed.\n"
                f"Reason: <code>{result.get('halt_reason') or result.get('error') or 'unknown'}</code>\n"
                f"Issues: <code>{json.dumps(issues, ensure_ascii=False)[:1200]}</code>"
            ),
        )
        return
    if command == "/returns_ack_store":
        if not args:
            _send_text(
                token=token,
                chat_id=chat_id,
                text="Usage: <code>/returns_ack_store ACMEWEAR</code> or multiple store codes.",
            )
            return
        invalid = [item for item in args if returns_pickup_report_mod.normalize_store_code(item) is None]
        if invalid:
            _send_text(
                token=token,
                chat_id=chat_id,
                text="Unknown store code(s): <code>" + ", ".join(_clean(item) for item in invalid) + "</code>",
            )
            return
        result = returns_pickup_report_mod.ack_current_pickup_orders_for_stores(
            store_codes=args,
            db_path=DB_PATH,
            acked_by=user_id,
            as_of=now,
        )
        if int(result.get("acked_orders") or 0) <= 0:
            _send_text(token=token, chat_id=chat_id, text="No pickup-ready orders matched those stores.")
            return
        store_lines = [
            f"{item['display_name']}: <code>{item['acked_orders']}</code>"
            for item in list(result.get("stores") or [])
        ]
        _send_text(
            token=token,
            chat_id=chat_id,
            text="Pickup queue acknowledged.\n"
            f"Orders hidden: <code>{int(result.get('acked_orders') or 0)}</code>\n"
            + "\n".join(store_lines),
        )
        return
    if command == "/returns_unack":
        if not args:
            _send_text(
                token=token,
                chat_id=chat_id,
                text="Usage: <code>/returns_unack 123456789 987654321</code>",
            )
            return
        result = returns_pickup_report_mod.unack_pickup_orders(order_ids=args)
        restored = int(result.get("restored_orders") or 0)
        if restored <= 0:
            _send_text(token=token, chat_id=chat_id, text="No acknowledged pickup orders matched those IDs.")
            return
        _send_text(
            token=token,
            chat_id=chat_id,
            text=f"Pickup queue restored for <code>{restored}</code> order(s).",
        )
        return
    if command == "/final_table":
        result = send_final_status_table(expected_target_date=target_date)
        if result.get("final_status_sent"):
            _send_text(
                token=token,
                chat_id=chat_id,
                text=(
                    "Telegram final table sent. "
                    f"message_id=<code>{result.get('final_status_message_id')}</code> "
                    f"bundles=<code>{result.get('confirmed_total')}/{result.get('total')}</code> "
                    f"returns=<code>{bool(result.get('returns_pickup_sent'))}</code>"
                ),
            )
        else:
            _send_text(token=token, chat_id=chat_id, text=f"Telegram final table failed: <code>{result.get('error')}</code>")
        return
    if command == "/halt":
        _clear_pending_ready()
        try:
            set_run_control_hold(target_date=target_date)
        except Exception as exc:
            _send_text(token=token, chat_id=chat_id, text=f"Telegram /halt cleared pending state, but HOLD write failed: <code>{exc}</code>")
            return
        _send_text(token=token, chat_id=chat_id, text="Telegram closeout fallback halted. Run_Control is HOLD.")


def poll_once(*, now: datetime | None = None) -> int:
    _load_env_file()
    try:
        config = get_waybill_telegram_config()
    except Exception as exc:
        print(f"Waybill Telegram control not configured: {exc}", file=sys.stderr)
        return 1

    token = config["token"]
    chat_id = str(config["chat_id"])
    local_now = now or _now()
    pending_rc = _process_pending_ready(token=token, now=local_now)
    if pending_rc != 0:
        return pending_rc
    handover_rc = _process_pending_handover(token=token, now=local_now, default_chat_id=chat_id)
    if handover_rc != 0:
        return handover_rc

    allowed_users = _allowed_user_ids()
    offset = _load_offset()
    updates = _get_updates(token, offset)
    max_update_id = None
    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            max_update_id = max(int(update_id), int(max_update_id or update_id))
        message = update.get("message") or update.get("edited_message") or {}
        text = str(message.get("text") or "")
        if not _text_to_command(text):
            continue
        message_chat_id = str((message.get("chat") or {}).get("id") or "")
        user_id = str((message.get("from") or {}).get("id") or "")
        if message_chat_id != chat_id:
            continue
        if not allowed_users or user_id not in allowed_users:
            _send_text(token=token, chat_id=message_chat_id, text="Waybill bot command denied.")
            continue
        _handle_command(text=text, chat_id=message_chat_id, user_id=user_id, token=token, now=local_now)

    if max_update_id is not None:
        _save_offset(max_update_id + 1)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram waybill control bot poller")
    parser.add_argument("--loop", action="store_true", help="Poll continuously")
    parser.add_argument("--interval", type=int, default=15, help="Loop interval seconds")
    args = parser.parse_args()

    if not args.loop:
        return poll_once()

    while True:
        poll_once()
        time.sleep(max(5, int(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
